"""실제 임시 Git 원격과 SQLite로 workflow의 복원 실패 차단을 검증한다."""
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from funded_project_research.normalize import NoticeRecord
from funded_project_research.store import NEW_COLUMNS, Store
from scripts import ci_db

ROOT = Path(__file__).resolve().parents[1]


class TestRestoreDB(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.remote = self.root / "remote.git"
        self.writer = self.root / "writer"
        self.checkout = self.root / "checkout"
        self.writer.mkdir()
        self.git(self.root, "init", "--bare", "--initial-branch=main", str(self.remote))
        self.git(self.writer, "init", "--initial-branch=main")
        self.git(self.writer, "config", "user.name", "DB safety test")
        self.git(self.writer, "config", "user.email", "db-test@example.invalid")
        (self.writer / "README.md").write_text("code baseline\n", encoding="utf-8")
        self.git(self.writer, "add", "README.md")
        self.git(self.writer, "commit", "-m", "code")
        self.git(self.writer, "remote", "add", "origin", str(self.remote))
        self.git(self.writer, "push", "origin", "main")
        self.git(self.writer, "switch", "-c", "data")
        store = Store(str(self.writer / "gov_notices.db"))
        store.upsert(NoticeRecord("kstartup", "1", "보존할 공고", "https://example.invalid/1"),
                     "2026-11-12T09:00:00+09:00")
        store.mark_alert("kstartup:1", "new")
        store.commit()
        store.close()
        self.original = (self.writer / "gov_notices.db").read_bytes()
        self.publish_snapshot(self.original)
        self.git(self.root, "clone", str(self.remote), str(self.checkout))
        self.db = self.checkout / "gov_notices.db"
        self.backup = self.root / "baseline"
        self.output = self.root / "github-output"
        self.marker = self.root / "collector-started"

    def git(self, cwd, *args):
        return subprocess.run(
            ["git", "-c", "commit.gpgsign=false", "-c", "core.hooksPath=/dev/null", *args],
            cwd=cwd, capture_output=True, check=True, text=True,
        ).stdout.strip()

    def publish_snapshot(self, payload):
        (self.writer / "gov_notices.db").write_bytes(payload)
        self.git(self.writer, "add", "gov_notices.db")
        self.git(self.writer, "commit", "--allow-empty", "-m", "snapshot")
        self.git(self.writer, "push", "origin", "data")

    def restore(self, *args):
        env = dict(os.environ, PYTHONPATH=str(ROOT), GITHUB_OUTPUT=str(self.output))
        # GitHub Actions와 같이 복원 단계가 성공했을 때만 다음 단계를 실행한다.
        command = [sys.executable, "-m", "scripts.ci_db", "restore",
                   "--backup-dir", str(self.backup), *args]
        result = subprocess.run(command, cwd=self.checkout, env=env, capture_output=True, text=True)
        if result.returncode == 0:
            self.marker.touch()
        return result

    def assert_blocked(self, *args):
        sentinel = b"existing local DB must survive"
        self.db.write_bytes(sentinel)
        remote_head = self.git(self.remote, "rev-parse", "refs/heads/data")
        result = self.restore(*args)
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertEqual(self.db.read_bytes(), sentinel)
        self.assertFalse(self.marker.exists(), "수집 이후 단계가 실행됨")
        self.assertFalse(self.output.exists())
        self.assertEqual(self.git(self.remote, "rev-parse", "refs/heads/data"), remote_head)
        return result

    def test_restore_preserves_bytes_keys_timestamps_and_alerts(self):
        result = self.restore()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.db.read_bytes(), self.original)
        self.assertEqual((self.backup / "gov_notices.db").read_bytes(), self.original)
        manifest = json.loads((self.backup / "manifest.json").read_text())
        self.assertEqual(manifest["counts"], {"notices": 1, "alerts": 1})
        self.assertEqual(manifest["sha256"], hashlib.sha256(self.original).hexdigest())
        self.assertEqual(manifest["code_sha"], self.git(self.checkout, "rev-parse", "HEAD"))
        self.assertEqual(manifest["data_sha"], self.git(self.remote, "rev-parse", "data"))
        self.assertIn("+00:00", manifest["checked_at"])
        self.assertIn("initialized=false", self.output.read_text())
        with sqlite3.connect(self.db) as conn:
            self.assertEqual(conn.execute("SELECT key, first_seen, last_seen FROM notices").fetchone(),
                             ("kstartup:1", "2026-11-12T09:00:00+09:00", "2026-11-12T09:00:00+09:00"))
            self.assertEqual(conn.execute("SELECT * FROM alerts").fetchall(), [("kstartup:1", "new")])

    def test_missing_branch_requires_explicit_initialization(self):
        self.git(self.writer, "push", "origin", "--delete", "data")
        self.db.write_bytes(self.original)
        result = self.restore()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.db.read_bytes(), self.original)
        self.assertFalse(self.marker.exists())
        self.assertFalse(self.backup.exists())

    def test_initialization_only_when_remote_confirms_branch_absent(self):
        self.git(self.writer, "push", "origin", "--delete", "data")
        result = self.restore("--initialize")
        self.assertEqual(result.returncode, 0, result.stderr)
        manifest = json.loads((self.backup / "manifest.json").read_text())
        self.assertEqual(manifest["counts"], {"notices": 0, "alerts": 0})
        self.assertIsNone(manifest["data_sha"])
        self.assertIn("initialized=true", self.output.read_text())

    def test_initialization_never_replaces_existing_data_branch(self):
        self.assert_blocked("--initialize")

    def test_initialization_never_replaces_local_database(self):
        self.git(self.writer, "push", "origin", "--delete", "data")
        self.db.write_bytes(self.original)
        result = self.restore("--initialize")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.db.read_bytes(), self.original)
        self.assertFalse(self.marker.exists())

    def test_remote_error_is_not_first_run_even_with_initialization(self):
        self.git(self.checkout, "remote", "set-url", "origin", str(self.root / "unavailable.git"))
        for args in [(), ("--initialize",)]:
            with self.subTest(args=args):
                self.assert_blocked(*args)

    def test_fetch_failure_does_not_fall_back_to_stale_remote_ref(self):
        self.db.write_bytes(self.original)
        original_run = subprocess.run

        def fail_fetch(args, **kwargs):
            if args[:2] == ["git", "fetch"]:
                return subprocess.CompletedProcess(args, 128, b"", b"credential must not be printed")
            return original_run(args, **kwargs)

        previous_cwd = Path.cwd()
        try:
            os.chdir(self.checkout)
            with patch("scripts.ci_db.subprocess.run", side_effect=fail_fetch):
                with self.assertRaises(ci_db.SnapshotError) as caught:
                    ci_db.restore_db(self.db, self.backup)
        finally:
            os.chdir(previous_cwd)
        self.assertNotIn("credential", str(caught.exception))
        self.assertEqual(self.db.read_bytes(), self.original)
        self.assertFalse(self.backup.exists())

    def test_missing_blob_blocks_restore(self):
        self.git(self.writer, "rm", "gov_notices.db")
        self.git(self.writer, "commit", "-m", "missing database")
        self.git(self.writer, "push", "origin", "data")
        self.assert_blocked()

    def test_empty_or_corrupt_database_blocks_restore(self):
        for payload in [b"", b"not a SQLite database", self.original[:200]]:
            with self.subTest(size=len(payload)):
                self.publish_snapshot(payload)
                self.assert_blocked()

    def test_missing_tables_or_required_column_blocks_restore(self):
        for sql in ["DROP TABLE notices", "DROP TABLE alerts",
                    "ALTER TABLE notices DROP COLUMN first_seen"]:
            with self.subTest(sql=sql):
                path = self.root / "invalid.db"
                path.write_bytes(self.original)
                with sqlite3.connect(path) as conn:
                    conn.execute(sql)
                self.publish_snapshot(path.read_bytes())
                self.assert_blocked()

    def test_valid_empty_snapshot_is_not_mistaken_for_missing_database(self):
        path = self.root / "empty.db"
        store = Store(str(path))
        store.close()
        self.publish_snapshot(path.read_bytes())
        result = self.restore()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("initialized=false", self.output.read_text())

    def test_missing_primary_key_blocks_restore(self):
        path = self.root / "no-primary-key.db"
        path.write_bytes(self.original)
        with sqlite3.connect(path) as conn:
            conn.executescript("CREATE TABLE copy AS SELECT * FROM alerts; "
                               "DROP TABLE alerts; ALTER TABLE copy RENAME TO alerts;")
        self.publish_snapshot(path.read_bytes())
        self.assert_blocked()

    def test_legacy_snapshot_is_validated_without_migration(self):
        path = self.root / "legacy.db"
        path.write_bytes(self.original)
        with sqlite3.connect(path) as conn:
            for column in NEW_COLUMNS:
                conn.execute(f"ALTER TABLE notices DROP COLUMN {column}")
        legacy = path.read_bytes()
        self.publish_snapshot(legacy)
        result = self.restore()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.db.read_bytes(), legacy)

    def test_backup_failure_preserves_existing_database(self):
        self.backup.mkdir()
        (self.backup / "gov_notices.db").write_bytes(b"prior backup")
        self.assert_blocked()
        self.assertEqual((self.backup / "gov_notices.db").read_bytes(), b"prior backup")

    def test_validate_does_not_create_missing_database(self):
        missing = self.root / "missing.db"
        result = subprocess.run(
            [sys.executable, "-m", "scripts.ci_db", "validate", "--db", str(missing)],
            cwd=ROOT, capture_output=True, text=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(missing.exists())


if __name__ == "__main__":
    unittest.main()
