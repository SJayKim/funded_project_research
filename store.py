"""SQLite 영속. DB 자체가 직전 수집 스냅샷 역할(diff 비교 기준).

`data` 브랜치 checkout/commit은 collect.yml(Actions)에서 git으로 처리한다.
여기서는 파일 경로만 다룬다.
"""
from __future__ import annotations

import sqlite3
from dataclasses import asdict, fields

from normalize import NoticeRecord

DEFAULT_DB = "gov_notices.db"

_COLS = [f.name for f in fields(NoticeRecord)]

# 구 DB(data 브랜치)엔 없던 컬럼. 마이그레이션으로 ALTER 추가한다.
NEW_COLUMNS = ("category", "summary", "is_tech")


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

    def mark_alert(self, key: str, alert_type: str) -> None:
        self.conn.execute(
            "INSERT OR IGNORE INTO alerts (key, alert_type) VALUES (?, ?)",
            (key, alert_type),
        )

    def commit(self) -> None:
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()
