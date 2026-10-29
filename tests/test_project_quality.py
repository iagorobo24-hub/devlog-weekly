from datetime import datetime, timedelta, timezone
import unittest
from unittest.mock import Mock, patch

from src.project_quality import assess_head_ci, evaluate_quality, repo_facts, public_quality_report
from src import audit_project_quality

NOW = datetime(2026, 10, 29, 14, tzinfo=timezone.utc)
SHA = "a" * 40


def run(*, sha=SHA, branch="main", event="push", status="success", offset=2, rid=3):
    return {
        "id": rid, "head_sha": sha, "head_branch": branch, "event": event,
        "conclusion": status,
        "created_at": (NOW - timedelta(hours=offset)).isoformat(),
        "url": "https://github.com/owner/repo/actions/runs/3",
    }


class QualityContracts(unittest.TestCase):
    def test_only_default_branch_head_counts(self):
        q = assess_head_ci(head=SHA, branch="main", now=NOW, runs=[
            run(sha="b"*40),
            run(branch="feature/new"),
            run(event="pull_request"),
            run(offset=32*24),
        ])
        self.assertEqual(q["status"], "unknown")
        self.assertEqual(q["run_count_at_head"], 0)

    def test_real_head_pass_is_distinct_from_old_success(self):
        data = evaluate_quality({
            "visibility": "public", "repo": "owner/repo", "head": SHA,
            "default_branch": "main", "readme": True, "test_paths": True,
            "workflows": True, "runs": [run()]}, now=NOW)
        self.assertEqual(data["readiness"], "ci_head_passed_tests_exist")
        self.assertEqual(data["evidence_score"], 30)
        self.assertTrue(data["not_product_validation"])
        data["ci"] = assess_head_ci(head=SHA, branch="main", now=NOW,
                                   runs=[run(sha="b"*40)])
        self.assertEqual(data["ci"]["status"], "unknown")

    def test_failed_head_not_hidden_by_successful_head(self):
        q=assess_head_ci(head=SHA, branch="main", now=NOW,
                         runs=[run(status="success",rid=1),
                               run(status="failure",rid=2)])
        self.assertEqual(q["status"], "failure_or_cancelled")

    def test_pending_not_treated_as_pass(self):
        q=assess_head_ci(head=SHA, branch="main", now=NOW,
                         runs=[run(status=None), run(status="success")])
        self.assertEqual(q["status"], "pending")

    def test_ci_failure_needs_review(self):
        d=evaluate_quality({
            "visibility": "public", "repo": "owner/repo", "head": SHA,
            "default_branch": "main", "readme": True, "test_paths": True,
            "workflows": True, "runs": [run(status="failure")]}, now=NOW)
        self.assertEqual(d["readiness"], "ci_failure_needs_review")
        self.assertLess(d["evidence_score"], 30)

    def test_no_private_repo_read_before_guard(self):
        g=Mock()
        r=g.get_repo.return_value
        r.private=True
        with self.assertRaisesRegex(ValueError,"private repo blocked"):
            repo_facts(g,"owner/private")
        r.get_branch.assert_not_called()
        r.get_contents.assert_not_called()
        r.get_workflow_runs.assert_not_called()

    def test_nested_tests_detected_at_pinned_head(self):
        from types import SimpleNamespace as NS
        g=Mock()
        repo=g.get_repo.return_value
        repo.private=False
        repo.archived=False
        repo.default_branch="master"
        repo.get_branch.return_value.commit.sha=SHA
        repo.get_contents.side_effect=[
            [NS(path="README.md",name="README.md",type="file"),
             NS(path="30-tools",name="30-tools",type="dir")],
            [NS(path="30-tools/tests",name="tests",type="dir")],
            [NS(name="ci.yml",type="file")]
        ]
        repo.get_workflow_runs.return_value=[]
        facts=repo_facts(g,"owner/repo")
        self.assertTrue(facts["test_paths"])
        self.assertEqual(repo.get_contents.call_args_list[1].args[0],"30-tools")
        self.assertEqual(repo.get_contents.call_args_list[1].kwargs["ref"],SHA)

    def test_public_quality_report_rejects_private_candidate(self):
        s={"visibility":"public","schema":1,
           "ranked":[{"visibility":"private","repos":["owner/private"]}]}
        with self.assertRaisesRegex(ValueError,"private candidate"):
            public_quality_report(Mock(),s,now=NOW)

    def test_stale_source_selection_rejected(self):
        selection={"schema":1,"visibility":"public","generated_at":
                   (NOW-timedelta(days=4)).isoformat(),"ranked":[]}
        with self.assertRaisesRegex(ValueError, "obsoleta"):
            audit_project_quality.run(now=NOW,selector=selection,github_client=Mock())


if __name__ == "__main__":
    unittest.main()
