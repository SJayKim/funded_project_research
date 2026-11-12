"""화면의 날짜·검색·링크 규칙과 정적 배포 파일을 검증한다."""
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from funded_project_research import serve
from funded_project_research.store import Store


class TestDashboard(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "Node is required for the browser logic tests")
    def test_browser_rules(self):
        result = subprocess.run(
            ["node", "--test", str(Path(__file__).with_name("dashboard_logic.cjs"))],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_missing_database_is_not_created(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "missing.db"
            with self.assertRaises(sqlite3.OperationalError):
                serve.fetch_notices(str(path))
            self.assertFalse(path.exists())

    def test_static_build_includes_local_font_and_license(self):
        with tempfile.TemporaryDirectory() as temp:
            db = Path(temp) / "snapshot.db"
            Store(str(db)).close()
            before = db.read_bytes()
            output = Path(temp) / "site" / "index.html"
            with patch.object(serve, "DB_PATH", str(db)), patch.object(sys, "argv", ["serve", "--build", str(output)]):
                serve.main()
            self.assertEqual(db.read_bytes(), before)
            html = output.read_text()
            self.assertIn("assets/pretendard/PretendardVariable.woff2", html)
            font = output.parent / "assets" / "pretendard" / "PretendardVariable.woff2"
            self.assertEqual(font.read_bytes()[:4], b"wOF2")
            self.assertIn("SIL OPEN FONT LICENSE", (font.parent / "LICENSE.txt").read_text())

    def test_embedded_data_cannot_end_script(self):
        html = serve.render_page([{"title": '</script><img src=x onerror="alert(1)">', "category": '<svg onload="alert(1)">'}])
        self.assertEqual(html.count("</script>"), 1)
        self.assertIn(r"<\/script>", html)


if __name__ == "__main__":
    unittest.main()
