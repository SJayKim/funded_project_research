"""SQLite 영속. DB 자체가 직전 수집 스냅샷 역할(diff 비교 기준).

`data` 브랜치 checkout/commit은 collect.yml(Actions)에서 git으로 처리한다.
여기서는 파일 경로만 다룬다.
"""
from __future__ import annotations

import sqlite3
from dataclasses import asdict, fields

from .normalize import NoticeRecord

DEFAULT_DB = "gov_notices.db"

_COLS = [f.name for f in fields(NoticeRecord)]

# 구 DB(data 브랜치)엔 없던 컬럼. 마이그레이션으로 ALTER 추가한다.
NEW_COLUMNS = (
    "category", "summary", "is_tech",
    # Approach A 추출 6필드
    "funding_amount", "eligibility", "required_docs",
    "key_dates", "extracted_from", "extraction_status",
    "deadline_raw", "starts_at", "published_at", "source_checked_at",
    "verified_at", "verified_deadline", "verification_status",
    "summary_basis", "extraction_basis", "extracted_at",
)


class Store:
    def __init__(self, path: str = DEFAULT_DB):
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        cols = ", ".join(f"{c} TEXT" for c in _COLS)
        self.conn.executescript(
            f"""
            CREATE TABLE IF NOT EXISTS notices (
                key TEXT PRIMARY KEY,
                {cols},
                first_seen TEXT,
                last_seen TEXT
            );
            CREATE TABLE IF NOT EXISTS alerts (
                key TEXT,
                alert_type TEXT,
                PRIMARY KEY (key, alert_type)
            );
            CREATE TABLE IF NOT EXISTS source_health (
                source TEXT PRIMARY KEY, state TEXT, attempted_at TEXT,
                completed_at TEXT, last_success TEXT, count INTEGER,
                pages INTEGER, error_kind TEXT
            );
            CREATE TABLE IF NOT EXISTS verifications (
                key TEXT, checked_at TEXT, url TEXT, content_hash TEXT,
                old_deadline TEXT, new_deadline TEXT, evidence TEXT,
                PRIMARY KEY (key, content_hash, new_deadline)
            );
            CREATE TABLE IF NOT EXISTS recheck_attempts (
                key TEXT PRIMARY KEY, checked_at TEXT, result TEXT, reason TEXT
            );
            CREATE TABLE IF NOT EXISTS reliability_checks (
                run_id TEXT PRIMARY KEY, checked_at TEXT, report_json TEXT
            );
            """
        )
        self._migrate()
        self.conn.commit()

    def _migrate(self) -> None:
        """없는 새 컬럼만 ALTER ADD. fresh DB엔 이미 존재 → skip. 멱등."""
        existing = {row["name"] for row in self.conn.execute("PRAGMA table_info(notices)")}
        for col in NEW_COLUMNS:
            if col not in existing:
                self.conn.execute(f"ALTER TABLE notices ADD COLUMN {col} TEXT")

    def load(self) -> dict[str, NoticeRecord]:
        """기존 적재 레코드(직전 스냅샷)를 key->NoticeRecord로."""
        out: dict[str, NoticeRecord] = {}
        for row in self.conn.execute(f"SELECT {', '.join(_COLS)} FROM notices"):
            rec = NoticeRecord(**{c: (row[c] or "") for c in _COLS})  # ALTER NULL→"" 보정
            out[rec.key] = rec
        return out

    def upsert(self, rec: NoticeRecord, now: str) -> None:
        d = asdict(rec)
        placeholders = ", ".join("?" for _ in _COLS)
        update = ", ".join(f"{c}=excluded.{c}" for c in _COLS if c not in ("source", "source_id"))
        self.conn.execute(
            f"""
            INSERT INTO notices (key, {', '.join(_COLS)}, first_seen, last_seen)
            VALUES (?, {placeholders}, ?, ?)
            ON CONFLICT(key) DO UPDATE SET {update}, last_seen=excluded.last_seen
            """,
            [rec.key] + [d[c] for c in _COLS] + [now, now],
        )

    def alert_sent(self, key: str, alert_type: str) -> bool:
        cur = self.conn.execute(
            "SELECT 1 FROM alerts WHERE key=? AND alert_type=?", (key, alert_type)
        )
        return cur.fetchone() is not None

    def update_extraction(self, rec: NoticeRecord) -> None:
        columns = ("funding_amount", "eligibility", "required_docs", "key_dates",
                   "extracted_from", "extraction_status", "extraction_basis", "extracted_at")
        self.conn.execute(f"UPDATE notices SET {', '.join(c + '=?' for c in columns)} WHERE key=?",
                          [getattr(rec, c) for c in columns] + [rec.key])

    def record_source(self, source: str, state: str, attempted: str, completed: str,
                      count: int, pages: int, error_kind: str) -> None:
        self.conn.execute("""
            INSERT INTO source_health VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source) DO UPDATE SET state=excluded.state,
            attempted_at=excluded.attempted_at, completed_at=excluded.completed_at,
            last_success=CASE WHEN excluded.state IN ('success', 'empty')
                THEN excluded.last_success ELSE source_health.last_success END,
            count=excluded.count, pages=excluded.pages, error_kind=excluded.error_kind
        """, (source, state, attempted, completed,
              completed if state in ("success", "empty") else "", count, pages, error_kind))

    def source_health(self) -> list[dict]:
        return [dict(r) for r in self.conn.execute("SELECT * FROM source_health ORDER BY source")]

    def mark_alert(self, key: str, alert_type: str) -> None:
        self.conn.execute(
            "INSERT OR IGNORE INTO alerts (key, alert_type) VALUES (?, ?)",
            (key, alert_type),
        )

    def commit(self) -> None:
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()
