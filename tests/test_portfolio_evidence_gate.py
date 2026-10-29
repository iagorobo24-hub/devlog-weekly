"""Public evidence gate tests: source presence never approves runtime or image use."""
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace as NS
from unittest.mock import Mock
import copy
import unittest
import yaml

from src.portfolio_data import load_portfolio
from src.portfolio_evidence_gate import (
    SOURCE, SELECTION, validate_inventory, path_ok, build, render_md,
)

NOW = datetime(2026, 10, 29, 20, tzinfo=timezone.utc)


def fixture():
    spec = yaml.safe_load(SOURCE.read_text(encoding="utf-8"))
    editorial = yaml.safe_load(SELECTION.read_text(encoding="utf-8"))
    projects = editorial["main_cases"] + editorial["supporting_cases"]
    published = load_portfolio()
    release = {
        "visibility": "public", "automatic_publication": False,
        "safe_to_replace_public_portfolio": False,
        "private_inputs_accessed": False,
        "selection_generated_at": NOW.isoformat(),
        "current_portfolio": [{"repo": p["repo"], "pinned_revision": p["revision"]}
                              for p in published["projects"]],
        "candidates": [
            {"repo": p["repo"], "head": p["revision"], "visibility": "public",
             "approved_for_release": False}
            for p in projects if p["repo"] != "iagorobo24-hub/proyecto-pfc-iago-duran",
        ],
    }
    return spec, editorial, release, published


def mock_github(spec):
    client = Mock()
    seen = {}
    for item in spec["projects"]:
        r = Mock()
        r.private = False
        r.default_branch = "main"
        r.get_branch.return_value.commit.sha = item["revision"]
        r.get_contents.return_value = NS(
            type="file", size=25000, sha="b" * 40)
        name = item["repo"]
        verdict = ("failure" if name.endswith("proyecto-pfc-iago-duran")
                   else "success" if name.endswith("GuiaIA")
                   or name.endswith("T-IA-Portal-RocaRoibas") else None)
        if verdict is None:
            r.get_workflow_runs.return_value = []
        else:
            r.get_workflow_runs.return_value = [NS(
                id=42, head_sha=item["revision"], head_branch="main",
                event="push", created_at=NOW-timedelta(hours=3),
                conclusion=verdict,
                html_url=f"https://github.com/{name}/actions/runs/42",
            )]
        seen[name] = r
    client.get_repo.side_effect = lambda name: seen[name]
    return client, seen


class EvidenceInventoryTests(unittest.TestCase):
    def test_inventory_matches_stable_editorial_and_is_not_approved(self):
        source, editorial, release, portfolio = fixture()
        items = validate_inventory(source, editorial, release, portfolio)
        self.assertEqual(len(items), 5)
        self.assertEqual([p["role"] for p in items],
                         ["main", "main", "main", "supporting", "supporting"])
        self.assertEqual(sum(len(p["visuals"]) for p in items), 8)
        self.assertTrue(all(not x["approved_for_public_use"]
                            for p in items for x in p["visuals"]))

    def test_report_separates_ci_file_presence_runtime_and_permissions(self):
        spec, editorial, release, portfolio = fixture()
        gh, repos = mock_github(spec)
        result = build(spec, editorial, release, portfolio, gh, now=NOW)
        cases = {x["repo"]: x for x in result["cases"]}
        self.assertEqual(cases["iagorobo24-hub/GuiaIA"]["ci"]["status"], "success_at_head")
        self.assertEqual(cases["iagorobo24-hub/proyecto-pfc-iago-duran"]["ci"]["status"],
                         "failure_or_cancelled")
        self.assertEqual(len(result["cases"]), 5)
        self.assertTrue(all(p["head_matches_revision"] for p in result["cases"]))
        self.assertTrue(all(p["claim"]["status"] == "present_at_revision"
                            for p in result["cases"]))
        self.assertFalse(result["all_visuals_approved"])
        self.assertTrue(all(not p["ready_for_publication"] for p in result["cases"]))
        self.assertTrue(all(not v["visual_content_inspected"]
                            for p in result["cases"] for v in p["visuals"]))
        for name, repo in repos.items():
            repo.get_workflow_runs.assert_called_once_with(
                event="push", branch="main",
                head_sha=next(x["revision"] for x in spec["projects"]
                              if x["repo"] == name))
        self.assertIn("GuiaIA", render_md(result))
        self.assertIn("failure_or_cancelled", render_md(result))

    def test_private_repo_rejected_before_any_content_or_ci_access(self):
        a, b, c, d = fixture()
        gh, repos = mock_github(a)
        repos[a["projects"][0]["repo"]].private = True
        with self.assertRaisesRegex(ValueError, "Private repository"):
            build(a, b, c, d, gh, now=NOW)
        repos[a["projects"][0]["repo"]].get_branch.assert_not_called()
        repos[a["projects"][0]["repo"]].get_contents.assert_not_called()
        repos[a["projects"][0]["repo"]].get_workflow_runs.assert_not_called()

    def test_old_head_cannot_use_visuals_as_current(self):
        a, b, c, d = fixture()
        gh, repos = mock_github(a)
        repo = repos[a["projects"][0]["repo"]]
        repo.get_branch.return_value.commit.sha = "c" * 40
        result = build(a, b, c, d, gh, now=NOW)
        first = result["cases"][0]
        self.assertFalse(first["head_matches_revision"])
        self.assertEqual(first["visuals"][0]["status"], "revision_outdated")
        repo.get_contents.assert_not_called()
        repo.get_workflow_runs.assert_not_called()

    def test_override_approval_without_explicit_review_fails(self):
        a, b, c, d = fixture()
        a["owner_image_use_approval"] = True
        with self.assertRaisesRegex(ValueError, "publicación"):
            validate_inventory(a, b, c, d)
        a, b, c, d = fixture()
        a["projects"][0]["visuals"][0]["approved_for_public_use"] = True
        with self.assertRaisesRegex(ValueError, "Imagen no segura"):
            validate_inventory(a, b, c, d)

    def test_tampered_evidence_and_unexpected_candidate_fail(self):
        a, b, c, d = fixture()
        a["projects"][0]["revision"] = "a" * 40
        with self.assertRaisesRegex(ValueError, "Snapshot"):
            validate_inventory(a, b, c, d)
        a, b, c, d = fixture()
        a["projects"][0]["repo"] = "other-owner/private"
        with self.assertRaisesRegex(ValueError, "Inventario no coincide"):
            validate_inventory(a, b, c, d)
        a, b, c, d = fixture()
        c["candidates"][0]["approved_for_release"] = True
        with self.assertRaisesRegex(ValueError, "Preflight"):
            validate_inventory(a, b, c, d)

    def test_path_sanitization(self):
        self.assertTrue(path_ok("screenshots/real.png"))
        self.assertFalse(path_ok("../private.jpg"))
        self.assertFalse(path_ok("screenshots/../other.jpg"))
        self.assertFalse(path_ok("https://bad.example/evil.png"))
        self.assertFalse(path_ok("path with spaces.png"))

    def test_missing_image_is_not_silently_approved(self):
        a,b,c,d=fixture()
        gh,repos=mock_github(a)
        name=a["projects"][0]["repo"]
        first_repo=repos[name]
        def contents(path, ref):
            if path.endswith(".svg"):
                from github.GithubException import GithubException
                raise GithubException(404, {"message":"Not Found"}, None)
            return NS(type="file",size=20,sha="d"*40)
        first_repo.get_contents.side_effect=contents
        r=build(a,b,c,d,gh,now=NOW)
        self.assertEqual(r["cases"][0]["visuals"][0]["status"], "missing")
        self.assertFalse(r["cases"][0]["ready_for_publication"])


if __name__ == "__main__":
    unittest.main()
