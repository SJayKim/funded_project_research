"""오케스트레이터: 수집 → 정규화 → 중복제거 → diff → 알림 → 적재.

흐름(spec 아키텍처):
  load(직전 스냅샷) → 4개 어댑터 collect → normalize → dedupe
  → 신규/수정/임박 판정 → 이메일 1건 → upsert + 알림이력 기록 → commit
"""
from __future__ import annotations

import os
import sys
from datetime import date, datetime
from urllib.error import HTTPError, URLError

from . import anthropic_client, classify, diff, extract, notify_email, summarize
from .adapters.base import RawNotice, SourceError, http_get
from .adapters.bizinfo import BizinfoAdapter
from .adapters.iris import IrisAdapter
from .adapters.kstartup import KStartupAdapter
from .adapters.msit import MsitAdapter
from .adapters.nara import NaraAdapter
from .dedupe import dedupe
from .normalize import NoticeRecord, content_basis, normalize
from .status import KST, notice_state, utc_now
from .store import Store

ADAPTERS = [KStartupAdapter, BizinfoAdapter, MsitAdapter, NaraAdapter, IrisAdapter]

# Approach A enrich(2단계): 런당 추출 상한 + 추출 제외 소스 + 원문 코퍼스 경로.
ENRICH_CAP = 100
ENRICH_SKIP_SOURCES = ("nara", "msit")  # nara=입찰, msit=본문0/전부HWP(감사1번)
CORPUS_DIR = "corpus"


def collect_all(store: Store | None = None) -> list[RawNotice]:
    """출처 장애를 격리하고 앞 페이지와 실제 결과를 보존한다."""
    raws: list[RawNotice] = []
    for cls in ADAPTERS:
        attempted = utc_now()
        adapter = None
        rows = []
        kind = ""
        try:
            adapter = cls()
            rows = adapter.collect()
            state = getattr(adapter, "collection_state", "success")
            kind = getattr(adapter, "collection_error", "")
            if state == "success" and not rows:
                state = "empty"
        except Exception as e:
            rows = getattr(adapter, "records", [])
            state = "partial" if rows else "failed"
            if isinstance(e, SourceError):
                kind = str(e)
            elif isinstance(e, HTTPError):
                kind = f"http_{e.code}"
            elif isinstance(e, (URLError, TimeoutError)):
                kind = "network"
            elif isinstance(e, KeyError):
                kind = "configuration"
            else:
                kind = type(e).__name__
        if state in ("partial", "failed"):
            print(f"[warn] {cls.__name__}: {state} ({kind}), 보존 {len(rows)}건", file=sys.stderr)
        raws.extend(rows)
        if store:
            store.record_source(getattr(adapter, "source", getattr(cls, "source", cls.__name__)), state, attempted,
                                utc_now(), len(rows), getattr(adapter, "page_count", 0), kind)
            store.commit()
    return raws


def run(store: Store, current: list[NoticeRecord], today: date, send=True) -> dict:
    """순수 파이프라인(어댑터 제외). 테스트가 current를 직접 주입한다."""
    previous = store.load()
    now_iso = utc_now()

    # 전건 카테고리/기술여부 결정(결정적 키워드 매칭).
    for rec in current:
        rec.category, rec.is_tech = classify.classify(rec)
        rec.source_checked_at = now_iso
        prev = previous.get(rec.key)
        if prev and prev.verified_at:
            rec.verified_at, rec.verified_deadline = prev.verified_at, prev.verified_deadline
            if rec.deadline and (rec.deadline == prev.verified_deadline or
                                 len(rec.deadline) == 10 and rec.deadline == prev.verified_deadline[:10]):
                rec.deadline = prev.verified_deadline
                if rec.starts_at and len(rec.starts_at) == 10 and rec.starts_at == prev.starts_at[:10]:
                    rec.starts_at = prev.starts_at
                rec.verification_status = "confirmed"
            else:
                rec.verification_status = "conflict"

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
        elif not r.summary and (p := previous.get(r.key)) and p.summary and p.summary_basis == content_basis(r):
            r.summary = p.summary
        elif r.is_tech == "1":
            r.summary = summarize._fallback(r)
        if r.summary:
            r.summary_basis = content_basis(r)

    # 기존 추출필드(enrich 결과) 유지: enrich는 run() 다음 단계라 current엔 항상 공란.
    # 안 살리면 upsert가 재수집된 공고의 추출값을 ""로 덮어 유실(summary와 동일 이슈).
    for r in current:
        if (p := previous.get(r.key)):
            for f in ("funding_amount", "eligibility", "required_docs",
                      "key_dates", "extracted_from", "extraction_status", "extraction_basis", "extracted_at"):
                if not getattr(r, f):
                    setattr(r, f, getattr(p, f))
            if r.extraction_status and r.extraction_basis != content_basis(r):
                r.extraction_status = "stale"

    # 메일은 기술 공고만(DB엔 전건 저장).
    new_t = [r for r in new if r.is_tech == "1"]
    imm_t = [(r, d) for r, d in imminent if r.is_tech == "1"]
    mod_t = [m for m in modified if m.record.is_tech == "1"]

    msg = notify_email.build_message(new_t, imm_t, mod_t)
    if msg and send:
        notify_email.send(*msg)

    # 발송했으면(또는 send=False여도 적재는 진행) 알림 이력·레코드 기록.
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
    if not anthropic_client.llm_enabled():
        # em dash 등 cp949 밖 문자는 로컬 Windows 콘솔에서 UnicodeEncodeError — 로그는 cp949-safe로.
        print("[info] LLM off (LLM_ENABLED) - enrich 스킵")
        return {"enriched": 0, "dropped": 0, "skipped_llm_off": True}
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return {"enriched": 0, "dropped": 0, "skipped_no_key": True}

    today = datetime.now(KST)
    targets = [r for r in store.load().values()
               if r.is_tech == "1" and r.extraction_status in ("", "stale")
               and r.source not in ENRICH_SKIP_SOURCES and r.url
               and notice_state(r, today, require_fresh=False) not in ("closed", "conflict")]
    dropped = max(0, len(targets) - cap)
    if dropped:
        print(f"[enrich] 대상 {len(targets)}건 중 {cap}건 처리, {dropped}건 이월", file=sys.stderr)

    now_iso = utc_now()
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
            rec.extraction_basis = content_basis(rec)
            rec.extracted_at = now_iso
            store.update_extraction(rec)
            enriched += 1
        except Exception as e:  # 인증값이 포함될 수 있는 예외 전문은 로그에 남기지 않는다.
            print(f"[enrich] {rec.key} 추출 실패 ({type(e).__name__})", file=sys.stderr)
    store.commit()
    return {"enriched": enriched, "dropped": dropped}


def main() -> None:
    # --no-notify: 첫 실행 시 메일 발송 없이 DB만 시딩(전건이 '신규'로 잡혀 폭주하는 것 방지).
    # run()은 send=False여도 알림이력·레코드를 기록하므로 다음 실행부터 진짜 델타만 알린다.
    send = "--no-notify" not in sys.argv
    store = Store()
    raws = collect_all(store)
    if "--health-only" in sys.argv:
        # 운영 접근 점검만 수행한다. 시딩과 달리 공고·알림 이력을 갱신하지 않는다.
        unhealthy = any(s["state"] in ("partial", "failed") for s in store.source_health())
        store.close()
        print(f"출처 점검 {len(raws)}건 응답 | 공고·알림 이력 변경 없음 | 메일·LLM 호출 없음")
        if unhealthy:
            raise SystemExit(2)
        return
    current = dedupe([normalize(r) for r in raws])
    summary = run(store, current, datetime.now(KST), send=send)
    # base 스냅샷 확정 후 2단계 추출(별도 트랜잭션. 터져도 일일 스냅샷·메일 안전).
    enr = enrich(store)
    unhealthy = any(s["state"] in ("partial", "failed") for s in store.source_health())
    store.close()
    extra = "" if send else " | --no-notify(메일 생략, DB 시딩)"
    if enr.get("skipped_no_key"):
        extra += " | enrich 생략(API 키 없음)"
    else:
        extra += f" | 추출 {enr['enriched']}" + (f"(이월 {enr['dropped']})" if enr['dropped'] else "")
    print(f"수집 {len(current)}건 | 신규 {summary['new']} · 수정 {summary['modified']} · "
          f"임박 {summary['imminent']}" + extra)
    if unhealthy:
        raise SystemExit(2)  # workflow는 DB·장애 상태를 배포한 다음 실패로 표시한다.


if __name__ == "__main__":
    main()
