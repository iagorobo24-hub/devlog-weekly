"""Regresiones de cronología histórica y protección de información."""
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock

from src import backfill


class HistoryTests(unittest.TestCase):
    def test_eight_weeks_and_first_partial(self):
        start = backfill.parse_utc("2026-08-31T14:38:32.972001+00:00")
        end = backfill.parse_utc("2026-10-26T00:00:00+00:00")
        weeks = backfill.week_windows(start, end)
        self.assertEqual(len(weeks), 8)
        self.assertEqual(weeks[0]["week"], "2026-W36")
        self.assertTrue(weeks[0]["partial"])
        self.assertEqual(weeks[-1]["week"], "2026-W43")
        self.assertFalse(weeks[-1]["partial"])

    def test_exclusive_end_and_inclusive_start(self):
        start = backfill.parse_utc("2026-09-07T00:00:00Z")
        end = backfill.parse_utc("2026-09-14T00:00:00Z")
        self.assertTrue(backfill.in_window("2026-09-07T00:00:00Z", start, end))
        self.assertFalse(backfill.in_window("2026-09-14T00:00:00Z", start, end))

    def test_requires_timezone(self):
        with self.assertRaisesRegex(ValueError, "zona"):
            backfill.parse_utc("2026-09-07T00:00:00")

    def test_rejects_private_before_fetch(self):
        gh = Mock()
        gh.get_repo.return_value.private = True
        now = datetime.now(timezone.utc)
        with self.assertRaisesRegex(RuntimeError, "privado prohibido"):
            backfill.collect_public_repos(gh, now, now, {"repos": [{"name": "x/priv"}]})
        gh.get_repo.return_value.get_commits.assert_not_called()

    def test_markdown_and_manifest_only(self):
        start = backfill.parse_utc("2026-09-07T00:00:00Z")
        end = backfill.parse_utc("2026-09-14T00:00:00Z")
        repos = [{"name": "x/repo", "commits": [
            {"sha": "abc123456789", "date": "2026-09-08T10:00:00Z", "message": "<script>alert(1)</script>"},
            {"sha": "def123456789", "date": "2026-09-14T00:00:00Z", "message": "fuera"}
        ], "issues_closed": [], "prs_closed": []}]
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            result = backfill.write_backfill(start, end, repos, folder, 5)
            doc = (folder / "2026-W37.md").read_text()
            self.assertIn("abc1234567", doc)
            self.assertNotIn("def1234567", doc)
            self.assertIn("&lt;script&gt;", doc)
            self.assertEqual(result[0]["repos"][0]["commits"], 1)
            self.assertTrue((folder / "manifest.json").is_file())
            self.assertFalse((folder / "state").exists())

    def test_truncation_reports_exact_count(self):
        start = backfill.parse_utc("2026-09-07T00:00:00Z")
        end = backfill.parse_utc("2026-09-14T00:00:00Z")
        repo = {"name": "x/repo", "commits": [
            {"sha": f"{n:040x}", "date": "2026-09-08T10:00:00Z", "message": f"commit {n}"}
            for n in range(4)
        ], "issues_closed": [], "prs_closed": []}
        markdown, _ = backfill.summarize_week(
            backfill.week_windows(start, end)[0], [repo], 2)
        self.assertIn("Commits verificables · 1/2", markdown)
        self.assertIn("Commits verificables · 2/2", markdown)
        for n in range(4):
            self.assertIn(f"{n:010x}", markdown)


if __name__ == "__main__":
    unittest.main()
