from datetime import datetime, timezone
from types import SimpleNamespace as NS
import copy
import unittest
from unittest.mock import Mock

from github.GithubException import GithubException

from src.public_commit_diff_audit import build, classify_path, read_diff

NOW = datetime(2026, 10, 29, 16, tzinfo=timezone.utc)
NAME = "iagorobo24-hub/public"
SHA = "a" * 40
URL = f"https://github.com/{NAME}/commit/{SHA}"


def data():
    return {"schema": 1, "visibility": "public", "generated_at": NOW.isoformat(),
            "source_selection_generated_at": NOW.isoformat(),
            "feature_work_is_not_main_or_ci_evidence": True,
            "private_inputs_accessed": False, "automatic_publication": False,
            "repos": [{
                "repo": NAME, "visibility": "public",
                "not_merged_or_runtime_verified": True,
                "sample_recent_substantive_commits": [{
                    "sha": SHA, "kind": "code", "url": URL,
                    "commit_subject_only": True,
                    "not_merged_or_functionally_verified": True,
                    "subject": "feat: example",
                }],
            }]}


def remote(paths=("src/app.py", "tests/test_app.py")):
    repo = Mock()
    repo.private = False
    repo.full_name = NAME
    repo.get_commit.return_value = NS(sha=SHA,
        files=[NS(filename=p) for p in paths])
    gh = Mock()
    gh.get_repo.return_value = repo
    return gh, repo


class PublicDiffTests(unittest.TestCase):
    def test_classifies_files_not_subjects(self):
        self.assertEqual(classify_path("src/main.py"), "code")
        self.assertEqual(classify_path("tests/unit/test_app.py"), "tests")
        self.assertEqual(classify_path("src/widget.spec.ts"), "tests")
        self.assertEqual(classify_path("docs/README.md"), "docs")
        self.assertEqual(classify_path("assets/a.png"), "other")

    def test_actual_code_and_tests_are_counted_without_names(self):
        gh, repo = remote()
        item = build(data(), gh, now=NOW)["repos"][0]["audited"][0]
        self.assertEqual(item["counts"], {"code": 1, "tests": 1, "docs": 0, "other": 0})
        self.assertTrue(item["matching_declared_kind"])
        self.assertEqual(item["status"], "code_or_test_files_present")
        self.assertNotIn("src/app.py", str(item))
        self.assertTrue(item["not_test_execution_or_functional_validation"])
        repo.get_commit.assert_called_once_with(SHA)

    def test_docs_only_cannot_prove_code(self):
        gh, _ = remote(("docs/README.md",))
        item = build(data(), gh, now=NOW)["repos"][0]["audited"][0]
        self.assertFalse(item["matching_declared_kind"])
        self.assertEqual(item["status"], "only_docs_or_other_paths")

    def test_test_subject_without_test_paths_is_not_test_proof(self):
        gh, _ = remote(("src/app.py",))
        report = data()
        report["repos"][0]["sample_recent_substantive_commits"][0]["kind"] = "test"
        item = build(report, gh, now=NOW)["repos"][0]["audited"][0]
        self.assertFalse(item["matching_declared_kind"])

    def test_truncated_diff_is_not_complete(self):
        gh, repo = remote(("src/a.py", "src/b.py"))
        item = read_diff(repo, SHA, "code", max_files=1)
        self.assertEqual(item["status"], "incomplete_file_list")
        self.assertFalse(item["scan_complete"])

    def test_mismatched_sha_does_not_pass(self):
        gh, repo = remote()
        repo.get_commit.return_value.sha = "b" * 40
        item = build(data(), gh, now=NOW)["repos"][0]["audited"][0]
        self.assertEqual(item["status"], "commit_sha_mismatch")
        self.assertFalse(item["scan_complete"])

    def test_unavailable_is_not_missing_or_success(self):
        gh, repo = remote()
        repo.get_commit.side_effect = GithubException(403, {"message": "rate limited"})
        item = build(data(), gh, now=NOW)["repos"][0]["audited"][0]
        self.assertEqual(item["status"], "unavailable")
        self.assertFalse(item["matching_declared_kind"])

    def test_private_rejected_before_reading_commit(self):
        gh, repo = remote()
        repo.private = True
        with self.assertRaisesRegex(ValueError, "Private"):
            build(data(), gh, now=NOW)
        repo.get_commit.assert_not_called()

    def test_foreign_or_duplicate_commit_rejected(self):
        gh, _ = remote()
        report = data()
        report["repos"][0]["sample_recent_substantive_commits"][0]["url"] = "https://attacker.example/commit"
        with self.assertRaisesRegex(ValueError, "Unsafe"):
            build(report, gh, now=NOW)
        report = data()
        report["repos"][0]["sample_recent_substantive_commits"] *= 2
        with self.assertRaisesRegex(ValueError, "Unsafe"):
            build(report, gh, now=NOW)

    def test_private_and_stale_reports_rejected(self):
        gh, _ = remote()
        report = data()
        report["visibility"] = "private"
        with self.assertRaisesRegex(ValueError, "public"):
            build(report, gh, now=NOW)
        report = data()
        with self.assertRaisesRegex(ValueError, "Stale"):
            build(report, gh, now=NOW.replace(day=31))
        gh.get_repo.assert_not_called()

    def test_no_remote_reads_if_no_commits_to_audit(self):
        gh, _ = remote()
        report = data()
        report["repos"][0]["sample_recent_substantive_commits"] = []
        value = build(report, gh, now=NOW)
        self.assertEqual(value["repos"][0]["sampled"], 0)
        gh.get_repo.assert_not_called()


if __name__ == "__main__":
    unittest.main()
