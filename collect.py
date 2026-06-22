"""오케스트레이터: 수집 → 정규화 → 중복제거 → diff → 알림 → 적재.

흐름(spec 아키텍처):
  load(직전 스냅샷) → 4개 어댑터 collect → normalize → dedupe
  → 신규/수정/임박 판정 → 이메일 1건 → upsert + 알림이력 기록 → commit
"""
from __future__ import annotations

import sys
from datetime import date, datetime

import diff
import notify_email
from adapters.base import RawNotice
from adapters.bizinfo import BizinfoAdapter
from adapters.iris import IrisAdapter
from adapters.kstartup import KStartupAdapter
from adapters.msit import MsitAdapter
from adapters.nara import NaraAdapter
from dedupe import dedupe
from normalize import NoticeRecord, normalize
from store import Store

ADAPTERS = [KStartupAdapter, BizinfoAdapter, MsitAdapter, NaraAdapter, IrisAdapter]


def collect_all() -> list[RawNotice]:
    raws: list[RawNotice] = []
    for cls in ADAPTERS:
        raws += cls().collect()
    return raws


def run(store: Store, current: list[NoticeRecord], today: date, send=True) -> dict:
    """순수 파이프라인(어댑터 제외). 테스트가 current를 직접 주입한다."""
    previous = store.load()

    new = diff.find_new(previous, current)
    modified = diff.find_modified(previous, current)

    # 임박: 마감일 있고 임계(7/3/1) 도달 + 아직 미발송분만.
    imminent = []
    for rec, d in diff.find_imminent(current, today):
        atype = f"imminent:{d}"
        if not store.alert_sent(rec.key, atype):
            imminent.append((rec, d))

    msg = notify_email.build_message(new, imminent, modified)
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


def main() -> None:
    # --no-notify: 첫 실행 시 메일 발송 없이 DB만 시딩(전건이 '신규'로 잡혀 폭주하는 것 방지).
    # run()은 send=False여도 알림이력·레코드를 기록하므로 다음 실행부터 진짜 델타만 알린다.
    send = "--no-notify" not in sys.argv
    store = Store()
    raws = collect_all()
    current = dedupe([normalize(r) for r in raws])
    summary = run(store, current, date.today(), send=send)
    store.close()
    print(f"수집 {len(current)}건 | 신규 {summary['new']} · 수정 {summary['modified']} · "
          f"임박 {summary['imminent']}" + ("" if send else " | --no-notify(메일 생략, DB 시딩)"))


if __name__ == "__main__":
    main()
