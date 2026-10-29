from datetime import datetime, timedelta, timezone
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock

from src.public_branch_activity import build, probe, _names

NOW = datetime(2026, 10, 29, 15, tzinfo=timezone.utc)
NAME = "iagorobo24-hub/public"
SHA = "f" * 40


def cm(n, days, message):
    return NS(sha=f"{n:040x}",
              commit=NS(committer=NS(date=NOW - timedelta(days=days)),
                        author=None, message=message))


def branch(name, num):
    return NS(name=name, commit=NS(sha=f"{num:040x}"))


def fake():
    r = Mock()
    r.private = False
    r.full_name = NAME
    r.default_branch = "main"
    r.get_branch.return_value.commit.sha = SHA
    r.get_branches.return_value = [branch("main", 50), branch("feature/a", 51),
                                   branch("feature/b", 52)]
    def comparison(base, head):
        data = {"feature/a": [cm(1, 1, "feat: capability"),
                              cm(2, 2, "test: regression")],
                "feature/b": [cm(1, 1, "feat: capability"),
                              cm(3, 3, "docs: instructions")]}
        return NS(ahead_by=len(data[head]), commits=data[head])
    r.compare.side_effect = comparison
    gh = Mock()
    gh.get_repo.return_value = r
    return gh, r


def selection():
    return {"schema": 1, "visibility": "public", "generated_at": NOW.isoformat(),
            "recent_days": 7, "lookback_days": 30,
            "ranked": [{"repos": [NAME], "visibility": "public"}],
            "other_active": [], "watchlist": []}


class BranchActivityTests(unittest.TestCase):
    def test_shared_feature_commits_deduped(self):
        gh, repo = fake()
        row = probe(gh, NAME, now=NOW, recent_days=7, lookback_days=30)
        self.assertEqual(row["counts_unique_ahead_of_default"]["code_7d"], 1)
        self.assertEqual(row["counts_unique_ahead_of_default"]["tests_7d"], 1)
        self.assertEqual(row["counts_unique_ahead_of_default"]["docs_30d"], 1)
        self.assertEqual(row["observed_unique_sha_count_in_window"], 3)
        self.assertTrue(row["scan_complete"])
        self.assertEqual(row["observed_ahead_sum_not_unique"], 4)
        self.assertTrue(row["not_merged_or_runtime_verified"])
        repo.compare.assert_any_call("main", "feature/a")

    def test_privacy_check_before_inspecting_branches(self):
        gh, repo = fake()
        repo.private = True
        with self.assertRaisesRegex(ValueError, "Private"):
            probe(gh, NAME, now=NOW, recent_days=7, lookback_days=30)
        repo.get_branches.assert_not_called()
        repo.compare.assert_not_called()

    def test_stale_public_selection_rejected(self):
        gh, _ = fake()
        s = selection()
        s["generated_at"] = (NOW - timedelta(days=3)).isoformat()
        with self.assertRaisesRegex(ValueError, "stale"):
            build(s, gh, now=NOW)

    def test_private_and_duplicate_selection_rejected_before_api(self):
        gh, _ = fake()
        s = selection()
        s["watchlist"] = [{"visibility": "private",
                           "repos": ["iagorobo24-hub/private"]}]
        with self.assertRaisesRegex(ValueError, "Private"):
            build(s, gh, now=NOW)
        gh.get_repo.assert_not_called()
        s["watchlist"] = [{"visibility": "public", "repos": [NAME]}]
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            build(s, gh, now=NOW)

    def test_branch_cap_visible_and_not_exhaustive(self):
        gh, r = fake()
        row = probe(gh, NAME, now=NOW, recent_days=7,
                    lookback_days=30, branch_limit=2)
        self.assertFalse(row["scan_complete"])
        self.assertEqual(row["branch_scanned"], 1)

    def test_compare_cap_visible_and_not_fabricated_success(self):
        gh, r = fake()
        row = probe(gh, NAME, now=NOW, recent_days=7,
                    lookback_days=30, commit_limit=1)
        self.assertFalse(row["scan_complete"])
        self.assertLessEqual(row["observed_unique_sha_count_in_window"], 2)

    def test_zero_ahead_branches_ignored(self):
        gh, r = fake()
        r.compare.side_effect = None
        r.compare.return_value = NS(ahead_by=0, commits=[])
        row = probe(gh, NAME, now=NOW, recent_days=7, lookback_days=30)
        self.assertEqual(row["observed_unique_sha_count_in_window"], 0)
        self.assertTrue(row["scan_complete"])

    def test_older_or_future_commits_not_counted(self):
        gh, r = fake()
        r.compare.side_effect = None
        r.compare.return_value = NS(ahead_by=2, commits=[
            cm(4, 40, "feat: stale"),
            cm(5, -1, "feat: future")])
        row = probe(gh, NAME, now=NOW, recent_days=7, lookback_days=30)
        self.assertEqual(row["counts_unique_ahead_of_default"]["code_30d"], 0)

    def test_public_report_keeps_provenance_and_no_publication(self):
        gh, r = fake()
        result = build(selection(), gh, now=NOW)
        self.assertEqual(result["visibility"], "public")
        self.assertTrue(result["feature_work_is_not_main_or_ci_evidence"])
        self.assertFalse(result["automatic_publication"])
        self.assertFalse(result["private_inputs_accessed"])
        self.assertEqual(len(result["repos"]), 1)


if __name__ == "__main__":
    unittest.main()
