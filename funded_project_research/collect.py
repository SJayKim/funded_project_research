"""오케스트레이터: 수집 → 정규화 → 중복제거 → diff → 알림 → 적재.

흐름(spec 아키텍처):
  load(직전 스냅샷) → 4개 어댑터 collect → normalize → dedupe
  → 신규/수정/임박 판정 → 이메일 1건 → upsert + 알림이력 기록 → commit
"""
from __future__ import annotations

import os
import sys
from datetime import date, datetime
from urllib.error import URLError

from . import classify, diff, extract, notify_email, summarize
from .adapters.base import RawNotice, http_get
from .adapters.bizinfo import BizinfoAdapter
from .adapters.iris import IrisAdapter
from .adapters.kstartup import KStartupAdapter
from .adapters.msit import MsitAdapter
from .adapters.nara import NaraAdapter
from .dedupe import dedupe
from .normalize import NoticeRecord, deadline_date, normalize
from .store import Store

ADAPTERS = [KStartupAdapter, BizinfoAdapter, MsitAdapter, NaraAdapter, IrisAdapter]

# Approach A enrich(2단계): 런당 추출 상한 + 추출 제외 소스 + 원문 코퍼스 경로.
ENRICH_CAP = 100
ENRICH_SKIP_SOURCES = ("nara", "msit")  # nara=입찰, msit=본문0/전부HWP(감사1번)
CORPUS_DIR = "corpus"


def collect_all() -> list[RawNotice]:
    # 어댑터별 격리: 한 소스 실패가 전체 실행을 죽이지 않게 건너뛰고 나머지 진행.
    # 해외 CI IP는 일부 정부서버(www.iris.go.kr·www.bizinfo.go.kr)를 지오차단 —
    # 국내선 정상이나 CI선 timeout(실측 IRIS 2026-06-23, bizinfo 2026-07-01).
    # 도달 실패(URLError)는 예상된 격리라 [info], 그 외는 실제 실패라 [warn].
    raws: list[RawNotice] = []
    for cls in ADAPTERS:
        try:
            raws += cls().collect()
        except URLError as e:
            print(f"[info] {cls.__name__} CI 미도달(지오차단 추정), 격리 스킵: {e}", file=sys.stderr)
        except Exception as e:
            print(f"[warn] {cls.__name__} 수집 실패, 건너뜀: {e}", file=sys.stderr)
    return raws


def run(store: Store, current: list[NoticeRecord], today: date, send=True) -> dict:
    """순수 파이프라인(어댑터 제외). 테스트가 current를 직접 주입한다."""
    previous = store.load()

    # 전건 카테고리/기술여부 결정(결정적 키워드 매칭).
    for rec in current:
        rec.category, rec.is_tech = classify.classify(rec)

    new = diff.find_new(previous, current)
    modified = diff.find_modified(previous, current)

    # 임박: 마감일 있고 임계(7/3/1) 도달 + 아직 미발송분만.
    imminent = []
    for rec, d in diff.find_imminent(current, today):
        atype = f"imminent:{d}"
        if not store.alert_sent(rec.key, atype):
            imminent.append((rec, d))

    # 요약: 신규∩기술∩미캐시만 LLM 호출(비용 통제). 시딩(send=False)엔 생략.
    to_sum = [r for r in new if r.is_tech == "1" and not r.summary] if send else []
    summaries = summarize.summarize(to_sum)
    for r in current:
        if r.key in summaries:
            r.summary = summaries[r.key]
        elif not r.summary and (p := previous.get(r.key)) and p.summary:
            r.summary = p.summary  # 기존 레코드 요약 유지(upsert가 ""로 덮지 않게)

    # 기존 추출필드(enrich 결과) 유지: enrich는 run() 다음 단계라 current엔 항상 공란.
    # 안 살리면 upsert가 재수집된 공고의 추출값을 ""로 덮어 유실(summary와 동일 이슈).
    for r in current:
        if (p := previous.get(r.key)):
            for f in ("funding_amount", "eligibility", "required_docs",
                      "key_dates", "extracted_from", "extraction_status"):
                if not getattr(r, f):
                    setattr(r, f, getattr(p, f))

    # 메일은 기술 공고만(DB엔 전건 저장).
    new_t = [r for r in new if r.is_tech == "1"]
    imm_t = [(r, d) for r, d in imminent if r.is_tech == "1"]
    mod_t = [m for m in modified if m.record.is_tech == "1"]

    msg = notify_email.build_message(new_t, imm_t, mod_t)
    if msg and send:
        notify_email.send(*msg)

    # 발송했으면(또는 send=False여도 적재는 진행) 알림 이력·레코드 기록.
    now_iso = datetime.now().isoformat(timespec="seconds")
    for rec in new:
        store.mark_alert(rec.key, "new")
    for m in modified:
        store.mark_alert(m.record.key, "modified")
    for rec, d in imminent:
        store.mark_alert(rec.key, f"imminent:{d}")
    for rec in current:
        store.upsert(rec, now_iso)
    store.commit()

    return {"new": len(new), "modified": len(modified), "imminent": len(imminent)}


def _save_corpus(rec: NoticeRecord, body: str) -> None:
    """추출 원문을 corpus/<source>/<source_id>.txt로 보존(commit DB 밖, .gitignore)."""
    d = os.path.join(CORPUS_DIR, rec.source)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, f"{rec.source_id}.txt"), "w", encoding="utf-8") as f:
        f.write(body)


def enrich(store: Store, cap: int = ENRICH_CAP) -> dict:
    """2단계: 신규∩기술 미추출 공고의 상세HTML 본문에서 4필드 추출(base commit 이후).

    게이트 = is_tech=="1" ∩ extraction_status=="" ∩ source∉(nara,msit) ∩ url ∩ 미마감(deadline 없거나 ≥오늘).
    상한 cap 초과분은 이월(다음 런). 공고별 try/except로 1건 실패가 전체 안 죽임.
    fetch 예외는 status 미기록 → 다음 런 재시도(일시적 timeout 실측 2026-06-25).
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return {"enriched": 0, "dropped": 0, "skipped_no_key": True}

    today = date.today()
    targets = [r for r in store.load().values()
               if r.is_tech == "1" and r.extraction_status == ""
               and r.source not in ENRICH_SKIP_SOURCES and r.url
               and (deadline_date(r) is None or deadline_date(r) >= today)]  # 마감 공고는 제외(신청 불가, 추출 낭비)
    dropped = max(0, len(targets) - cap)
    if dropped:
        print(f"[enrich] 대상 {len(targets)}건 중 {cap}건 처리, {dropped}건 이월", file=sys.stderr)

    now_iso = datetime.now().isoformat(timespec="seconds")
    enriched = 0
    for rec in targets[:cap]:
        try:
            body = extract.html_to_text(http_get(rec.url, timeout=20))
            _save_corpus(rec, body)
            vals, status = extract.extract_verified(body, api_key)  # 추출+substring검증+강등
            for f, v in vals.items():
                setattr(rec, f, v)
            rec.extraction_status = status
            rec.extracted_from = rec.url if status != "failed" else ""
            store.upsert(rec, now_iso)
            enriched += 1
        except Exception as e:  # fetch/저장 실패: status 미기록 → 다음 런 재시도
            print(f"[enrich] {rec.key} 추출 실패, 건너뜀: {e}", file=sys.stderr)
    store.commit()
    return {"enriched": enriched, "dropped": dropped}


def main() -> None:
    # --no-notify: 첫 실행 시 메일 발송 없이 DB만 시딩(전건이 '신규'로 잡혀 폭주하는 것 방지).
    # run()은 send=False여도 알림이력·레코드를 기록하므로 다음 실행부터 진짜 델타만 알린다.
    send = "--no-notify" not in sys.argv
    store = Store()
    raws = collect_all()
    current = dedupe([normalize(r) for r in raws])
    summary = run(store, current, date.today(), send=send)
    # base 스냅샷 확정 후 2단계 추출(별도 트랜잭션. 터져도 일일 스냅샷·메일 안전).
    enr = enrich(store)
    store.close()
    extra = "" if send else " | --no-notify(메일 생략, DB 시딩)"
    if enr.get("skipped_no_key"):
        extra += " | enrich 생략(API 키 없음)"
    else:
        extra += f" | 추출 {enr['enriched']}" + (f"(이월 {enr['dropped']})" if enr['dropped'] else "")
    print(f"수집 {len(current)}건 | 신규 {summary['new']} · 수정 {summary['modified']} · "
          f"임박 {summary['imminent']}" + extra)


if __name__ == "__main__":
    main()
