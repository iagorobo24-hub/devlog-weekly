from datetime import datetime, timezone
from types import SimpleNamespace as NS
import copy
import unittest

from src.strategic_selection import ci_map_for_branches, classify

NAME="iagorobo24-hub/GuiaIA"
SHA="a"*40
TIP="b"*40
STAMP="2026-10-29T16:00:00+00:00"


def inputs():
    selection={"generated_at": STAMP}
    branches={
        "generated_at": STAMP,
        "repos":[{"repo":NAME, "sample_branches":[
            {"branch":"feature/qa", "tip":TIP, "ahead_by":3}]}],
    }
    check={
        "branch":"feature/qa","tip_sha":TIP,"visibility":"public",
        "status":"all_observed_runs_successful","scan_complete":True,
        "all_returned_runs_succeeded":True,
        "branch_tips_checked":1,
        "workflow_runs":[{
            "run_id":123, "head_sha":TIP,
            "url":f"https://github.com/{NAME}/actions/runs/123",
            "status":"completed","conclusion":"success",
            "not_runtime_evidence":True,
        }],
    }
    report={
        "schema":1,"visibility":"public","automatic_publication":False,
        "private_inputs_accessed":False,
        "does_not_verify_all_workflows_or_runtime":True,
        "source_branch_generated_at":STAMP,
        "source_selection_generated_at":STAMP,
        "repos":[{"repo":NAME,"visibility":"public","branch_tips_checked":1,
                  "branches":[check]}],
    }
    return selection,branches,report


class BranchCiIntegrationTests(unittest.TestCase):
    def test_verified_exact_branch_tip_only(self):
        selection,branches,report=inputs()
        checked=ci_map_for_branches(selection,branches,report)
        self.assertEqual(checked[NAME][0]["status"],"all_observed_runs_successful")
        self.assertTrue(checked[NAME][0]["not_main_or_runtime_evidence"])
        self.assertEqual(checked[NAME][0]["sample_run_urls"],[
            f"https://github.com/{NAME}/actions/runs/123"])
        tier, reasons=classify(strategic_priority=5,ci_status="unknown",
                                has_test_path=True,has_draft=True,
                                currently_active=True)
        self.assertEqual(tier,"strategic_high_requires_verification")

    def test_other_sha_or_other_repo_link_refused(self):
        selection,branches,report=inputs()
        bad=report["repos"][0]["branches"][0]["workflow_runs"][0]
        bad["head_sha"]="f"*40
        with self.assertRaisesRegex(ValueError,"Foreign"):
            ci_map_for_branches(selection,branches,report)
        bad["head_sha"]=TIP
        bad["url"]="https://attacker.test/123"
        with self.assertRaisesRegex(ValueError,"Foreign"):
            ci_map_for_branches(selection,branches,report)

    def test_out_of_sync_branch_report_refused(self):
        selection,branches,report=inputs()
        report["source_branch_generated_at"]="old"
        with self.assertRaisesRegex(ValueError,"out of sync"):
            ci_map_for_branches(selection,branches,report)

    def test_false_success_refused(self):
        selection,branches,report=inputs()
        report["repos"][0]["branches"][0]["workflow_runs"][0]["conclusion"]="failure"
        with self.assertRaisesRegex(ValueError,"unsupported"):
            ci_map_for_branches(selection,branches,report)

    def test_missing_or_duplicate_repo_refused(self):
        selection,branches,report=inputs()
        report["repos"]=[]
        with self.assertRaisesRegex(ValueError,"incomplete"):
            ci_map_for_branches(selection,branches,report)
        selection,branches,report=inputs()
        report["repos"].append(copy.deepcopy(report["repos"][0]))
        with self.assertRaisesRegex(ValueError,"Duplicate"):
            ci_map_for_branches(selection,branches,report)

    def test_private_report_refused(self):
        selection,branches,report=inputs()
        report["repos"][0]["visibility"]="private"
        with self.assertRaisesRegex(ValueError,"Private"):
            ci_map_for_branches(selection,branches,report)


if __name__=="__main__":
    unittest.main()
