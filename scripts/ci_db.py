"""Actions DB 복원/검증. 실패하면 수집 전에 중단하며 기존 파일을 보존한다.

저장된 스냅샷은 읽기 전용으로 검사한다. Store의 마이그레이션은 수집기 몫이다.
"""
from __future__ import annotations

import argparse
from dataclasses import fields
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile

from funded_project_research.normalize import NoticeRecord
from funded_project_research.store import NEW_COLUMNS, Store


class SnapshotError(RuntimeError):
    pass


def _git(*args, stdout=subprocess.PIPE, allowed=(0,)):
    result = subprocess.run(["git", *args], stdout=stdout, stderr=subprocess.PIPE)
    if result.returncode not in allowed:
        # 원격 URL/인증 정보가 포함될 수 있는 git stderr는 출력하지 않는다.
        raise SnapshotError(f"git {args[0]} 실패 (exit {result.returncode}); 복원을 중단합니다.")
    return result


def inspect_db(path: Path) -> dict:
    if not path.is_file() or path.stat().st_size == 0:
        raise SnapshotError("DB 파일이 없거나 비어 있습니다.")
    conn = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    try:
        if conn.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
            raise SnapshotError("SQLite 무결성 검사 실패.")
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not {"notices", "alerts"} <= tables:
            raise SnapshotError("필수 테이블 notices/alerts가 없습니다.")
        # 기존 Store가 추가할 수 있는 파생 컬럼의 부재만 허용한다.
        required = {
            "notices": ({f.name for f in fields(NoticeRecord)} - set(NEW_COLUMNS))
                       | {"key", "first_seen", "last_seen"},
            "alerts": {"key", "alert_type"},
        }
        for table, columns in required.items():
            info = conn.execute(f"PRAGMA table_info({table})").fetchall()
            if not columns <= {row[1] for row in info}:
                raise SnapshotError(f"{table} 필수 컬럼이 없습니다.")
            expected_pk = {"key": 1} if table == "notices" else {"key": 1, "alert_type": 2}
            if {row[1]: row[5] for row in info if row[5]} != expected_pk:
                raise SnapshotError(f"{table} 기본 키가 올바르지 않습니다.")
        counts = {table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                  for table in required}
    finally:
        conn.close()
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    return {"integrity_check": "ok", "counts": counts, "sha256": digest}


def restore_db(db: Path, backup_dir: Path, initialize: bool = False) -> dict:
    code_sha = _git("rev-parse", "HEAD").stdout.decode().strip()
    remote = _git("ls-remote", "--exit-code", "--heads", "origin", "refs/heads/data", allowed=(0, 2))
    missing = remote.returncode == 2
    if missing and not initialize:
        raise SnapshotError("data 브랜치가 없습니다. 최초 실행은 initialize_db를 명시해야 합니다.")
    if initialize and (not missing or db.exists()):
        raise SnapshotError("초기화는 data 브랜치와 로컬 DB가 모두 없을 때만 허용합니다.")

    data_sha = None
    if not missing:
        _git("fetch", "--no-tags", "origin", "refs/heads/data:refs/remotes/origin/data")
        data_sha = _git("rev-parse", "--verify", "refs/remotes/origin/data").stdout.decode().strip()

    # 대상 파일과 같은 파일시스템에서 검증한 뒤 원자적으로 교체한다.
    with tempfile.TemporaryDirectory(prefix=".db-restore-", dir=db.resolve().parent) as temp:
        candidate = Path(temp) / "gov_notices.db"
        if missing:
            store = Store(str(candidate))
            store.close()
        else:
            with candidate.open("wb") as stream:
                _git("show", f"{data_sha}:gov_notices.db", stdout=stream)
        manifest = {
            **inspect_db(candidate),
            "code_sha": code_sha,
            "data_sha": data_sha,
            "initialized": missing,
            "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        # 같은 경로의 이전 백업을 덮지 않는다. 백업 실패 시 수집도 금지한다.
        backup_dir.mkdir(parents=True, exist_ok=False)
        shutil.copyfile(candidate, backup_dir / "gov_notices.db")
        (backup_dir / "manifest.json").write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8",
        )
        candidate.replace(db)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    restore = subparsers.add_parser("restore")
    restore.add_argument("--db", type=Path, default=Path("gov_notices.db"))
    restore.add_argument("--backup-dir", type=Path, required=True)
    restore.add_argument("--initialize", action="store_true")
    validate = subparsers.add_parser("validate")
    validate.add_argument("--db", type=Path, default=Path("gov_notices.db"))
    args = parser.parse_args()
    try:
        if args.command == "restore":
            result = restore_db(args.db, args.backup_dir, args.initialize)
            if output := os.environ.get("GITHUB_OUTPUT"):
                with open(output, "a", encoding="utf-8") as stream:
                    stream.write(f"initialized={str(result['initialized']).lower()}\n")
                    stream.write(f"data_sha={result['data_sha'] or ''}\n")
        else:
            result = inspect_db(args.db)
    except (SnapshotError, sqlite3.Error, OSError) as exc:
        # OS/SQLite 예외는 경로나 원문을 출력하지 않고 종류만 남긴다.
        detail = str(exc) if isinstance(exc, SnapshotError) else type(exc).__name__
        print(f"DB 안전 검사 실패: {detail}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
