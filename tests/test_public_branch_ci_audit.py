from datetime import datetime, timedelta, timezone
from types import SimpleNamespace as NS
import copy
import unittest
from unittest.mock import Mock

from src.public_branch_ci_audit import build, inspect_runs

NOW = datetime(2026, 10, 29, 17, tzinfo=timezone.utc)
NAME = "iagorobo24-hub/public"
SHA = "a"*40
TIP = "b"*40


def branch_report():
    return {
        "schema": 1, "visibility": "public",
        "generated_at": NOW.isoformat(),
        "source_selection_generated_at": NOW.isoformat(),
        "automatic_publication": False,
        "private_inputs_accessed": False,
        "feature_work_is_not_main_or_ci_evidence": True,
        "repos": [{"repo": NAME, "visibility": "public",
                   "not_merged_or_runtime_verified": True,
                   "counts_unique_ahead_of_default": {"code_7d": 3, "tests_7d": 2},
                   "sample_branches": [{"branch": "feature/x", "tip": TIP}]}],
    }


def client(outcomes=("success", "success")):
    repo = Mock()
    repo.private = False
    repo.full_name = NAME
    runs = [NS(id=i+1, head_sha=TIP, name=f"workflow {i}",
               event="push", status="completed", conclusion=o)
            for i,o in enumerate(outcomes)]
    repo.get_workflow_runs.return_value = runs
    gh = Mock()
    gh.get_repo.return_value = repo
    return gh,repo


class BranchCiTests(unittest.TestCase):
    def test_exact_sha_and_two_workflows_success(self):
        gh, repo = client()
        row = build(branch_report(), gh, now=NOW)["repos"][0]["branches"][0]
        repo.get_workflow_runs.assert_called_once_with(head_sha=TIP)
        self.assertEqual(row["status"], "all_observed_runs_successful")
        self.assertEqual(row["observed_workflow_count"], 2)
        self.assertTrue(row["all_returned_runs_succeeded"])
        self.assertTrue(row["workflow_coverage_not_proven"])
        self.assertEqual(row["workflow_runs"][0]["url"],
                         f"https://github.com/{NAME}/actions/runs/1")

    def test_any_failure_gates_observed_result(self):
        gh, _ = client(("success", "failure"))
        row = build(branch_report(), gh, now=NOW)["repos"][0]["branches"][0]
        self.assertEqual(row["status"], "observed_failure_or_cancelled")
        self.assertFalse(row["all_returned_runs_succeeded"])

    def test_missing_runs_not_success(self):
        gh, _ = client(())
        row = build(branch_report(), gh, now=NOW)["repos"][0]["branches"][0]
        self.assertEqual(row["status"], "no_runs_found")
        self.assertFalse(row["all_returned_runs_succeeded"])

    def test_wrong_sha_rejected_not_attributed_to_tip(self):
        gh, repo = client()
        repo.get_workflow_runs.return_value[0].head_sha = SHA
        with self.assertRaisesRegex(ValueError, "another SHA"):
            build(branch_report(), gh, now=NOW)

    def test_truncated_runs_never_complete(self):
        gh, repo = client(("success", "success"))
        row = inspect_runs(repo, TIP, limit=1)
        self.assertEqual(row["status"], "incomplete")
        self.assertFalse(row["scan_complete"])
        self.assertFalse(row["all_returned_runs_succeeded"])

    def test_private_repo_refused_before_run_lookup(self):
        gh,repo=client()
        repo.private=True
        with self.assertRaisesRegex(ValueError, "Private repository"):
            build(branch_report(), gh, now=NOW)
        repo.get_workflow_runs.assert_not_called()

    def test_stale_or_private_report_fails_before_api(self):
        gh,_=client()
        r=branch_report()
        r["generated_at"]=(NOW-timedelta(days=3)).isoformat()
        with self.assertRaisesRegex(ValueError, "Stale"):
            build(r,gh,now=NOW)
        r=branch_report()
        r["repos"][0]["visibility"]="private"
        with self.assertRaisesRegex(ValueError, "Private branch"):
            build(r,gh,now=NOW)
        gh.get_repo.assert_not_called()

    def test_no_active_work_avoids_external_queries(self):
        gh,_=client()
        r=branch_report()
        r["repos"][0]["counts_unique_ahead_of_default"]={"code_7d":0,"tests_7d":0}
        out=build(r,gh,now=NOW)
        self.assertEqual(out["repos"][0]["branch_tips_checked"],0)
        gh.get_repo.assert_not_called()

    def test_foreign_or_duplicate_tip_rejected(self):
        gh,_=client()
        r=branch_report()
        r["repos"][0]["sample_branches"] *= 2
        with self.assertRaisesRegex(ValueError, "duplicate"):
            build(r,gh,now=NOW)
        gh.get_repo.assert_not_called()

    def test_report_provenance_no_promotion(self):
        gh,_=client()
        result=build(branch_report(),gh,now=NOW)
        self.assertFalse(result["automatic_publication"])
        self.assertFalse(result["private_inputs_accessed"])
        self.assertTrue(result["does_not_verify_all_workflows_or_runtime"])
        self.assertEqual(result["source_branch_generated_at"],NOW.isoformat())


if __name__=="__main__":
    unittest.main()
