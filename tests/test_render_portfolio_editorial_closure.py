"""Editorial selection closure: stable public-only content, not publication."""
from copy import deepcopy
import unittest
import yaml

from src.portfolio_data import load_portfolio
from src.render_portfolio_editorial_closure import (
    SELECTION, build_slides, validate, validate_evidence_feed,
)

REPOS = (
    "iagorobo24-hub/T-IA-Portal-RocaRoibas",
    "iagorobo24-hub/proyecto-pfc-iago-duran",
    "iagorobo24-hub/GuiaIA",
    "iagorobo24-hub/awesome-tia-portal",
    "iagorobo24-hub/atm10sky-es-es-localization",
    "iagorobo24-hub/AUTOMATON",
)


def fixture():
    selection = yaml.safe_load(SELECTION.read_text(encoding="utf-8"))
    portfolio = load_portfolio()
    statuses = {
        REPOS[0]: "success_at_head", REPOS[2]: "unknown",
        REPOS[3]: "unknown", REPOS[4]: "unknown",
        REPOS[5]: "failure_or_cancelled",
    }
    present = {x["repo"]: x["revision"]
               for key in ("main_cases", "supporting_cases", "excluded_cases")
               for x in selection[key]}
    report = {
        "visibility": "public", "automatic_publication": False,
        "safe_to_replace_public_portfolio": False,
        "private_inputs_accessed": False,
        "current_portfolio": [
            {"repo": p["repo"], "pinned_revision": p["revision"]}
            for p in portfolio["projects"]],
        "candidates": [
            {"repo": repo, "visibility": "public", "approved_for_release": False,
             "head": present[repo], "ci_status": status,
             "source_presence_verified_at_revision": True}
            for repo, status in statuses.items()
        ]
    }
    return selection, report, portfolio


class StablePublicCurationTests(unittest.TestCase):
    def test_stable_selection_has_three_main_two_support_and_one_excluded(self):
        a, b, c = fixture()
        primary, supporting, excluded, _ = validate(a, b, c)
        self.assertEqual([x["repo"] for x in primary], list(REPOS[:3]))
        self.assertEqual([x["repo"] for x in supporting], list(REPOS[3:5]))
        self.assertEqual([x["repo"] for x in excluded], list(REPOS[5:]))
        self.assertTrue(a["policy"]["evaluate_recent_commits_as_secondary"])
        self.assertFalse(a["policy"]["automatic_publication"])

    def test_proposal_is_nine_pages_explaining_value_not_commit_count(self):
        slides = build_slides(*fixture(), stamp="corte fijo")
        self.assertEqual(len(slides), 9)
        self.assertEqual(sum(x["kind"] == "closure-main" for x in slides), 3)
        self.assertEqual(sum(x["kind"] == "closure-supporting" for x in slides), 2)
        self.assertEqual(sum(x["kind"] == "closure-exclusions" for x in slides), 1)
        self.assertTrue(all("NO PUBLICAR" in x["markup"] for x in slides))
        joined = "".join(x["markup"] for x in slides)
        self.assertIn("PFC Tools", joined)
        self.assertIn("GuiaIA", joined)
        self.assertIn("AUTOMATON", joined)
        self.assertIn("44 scripts", joined)
        self.assertIn("6.462", joined)
        self.assertIn("no acompañante jugable", joined)

    def test_snapshot_is_deterministic_and_does_not_change_portfolio(self):
        inputs = fixture()
        before = deepcopy(inputs)
        self.assertEqual(build_slides(*inputs, stamp="fijo"),
                         build_slides(*inputs, stamp="fijo"))
        self.assertEqual(inputs, before)
        self.assertEqual(len(inputs[2]["projects"]), 2)

    def test_readiness_is_not_inferred_from_present_source_files(self):
        a, b, c = fixture()
        b["candidates"][0]["source_presence_verified_at_revision"] = False
        with self.assertRaisesRegex(ValueError, "auditoría"):
            build_slides(a, b, c)

    def test_stale_main_revision_fails_closed(self):
        a, b, c = fixture()
        b["candidates"][0]["head"] = "b" * 40
        with self.assertRaisesRegex(ValueError, "desactualizada"):
            validate(a, b, c)

    def test_forged_candidate_evidence_path_rejected(self):
        a, b, c = fixture()
        a["main_cases"][0]["evidence"][0]["source_path"] = "docs/inventado.md"
        with self.assertRaisesRegex(ValueError, "ruta incluida"):
            validate(a, b, c)

    def test_private_repo_or_automatic_release_rejected(self):
        a, b, c = fixture()
        a["supporting_cases"][0]["repo"] = "private-secret/repo"
        with self.assertRaisesRegex(ValueError, "no pública"):
            validate(a, b, c)
        a, b, c = fixture()
        a["policy"]["automatic_publication"] = True
        with self.assertRaisesRegex(ValueError, "Controles editoriales"):
            validate(a, b, c)

    def test_automaton_cannot_be_unblocked_by_writing(self):
        a, b, c = fixture()
        b["candidates"][-1]["ci_status"] = "success_at_head"
        with self.assertRaisesRegex(ValueError, "fallo CI"):
            validate(a, b, c)

    def test_publication_flip_and_current_portfolio_drift_rejected(self):
        a, b, c = fixture()
        b["candidates"][0]["approved_for_release"] = True
        with self.assertRaisesRegex(ValueError, "aprobado"):
            validate(a, b, c)
        a, b, c = fixture()
        b["current_portfolio"][0]["pinned_revision"] = "b" * 40
        with self.assertRaisesRegex(ValueError, "no coincide"):
            validate(a, b, c)

    def test_reconciled_ci_updates_guia_and_pfc_without_runtime_promotion(self):
        a, b, c = fixture()
        feed = {
            "schema": 1, "visibility": "public",
            "automatic_publication": False,
            "safe_to_replace_public_portfolio": False,
            "public_projects_only": True, "private_sources_inspected": False,
            "ci_reports_consistent": True, "ci_report_disagreements": [],
            "source_selection_generated_at": b.get("selection_generated_at"),
            "cases": [
                {"repo": p["repo"], "revision": p["revision"], "visibility": "public",
                 "head_matches_revision": True, "ready_for_publication": False,
                 "owner_permission_confirmed": False,
                 "independent_runtime_validated": False,
                 "ci": {"status": ("failure_or_cancelled" if p["repo"] == REPOS[1]
                                   else "success_at_head" if p["repo"] in REPOS[:1]+REPOS[2:3]
                                   else "unknown"),
                        "run_url": ("https://github.com/" + p["repo"] +
                                    "/actions/runs/42" if p["repo"] in REPOS[:3] else None)}}
                for p in a["main_cases"] + a["supporting_cases"]
            ],
        }
        labels = build_slides(a, b, c, evidence=feed, stamp="fijo")
        self.assertIn("CI de push en HEAD correcta", labels[4]["markup"])
        self.assertIn("CI de push en HEAD fallida", labels[3]["markup"])
        self.assertIn("actions/runs/42", labels[4]["markup"])
        self.assertTrue(all("NO PUBLICAR" in x["markup"] for x in labels))
        bad = deepcopy(feed)
        bad["ci_reports_consistent"] = False
        with self.assertRaisesRegex(ValueError, "no reconciliada"):
            validate_evidence_feed(bad, a, b)
        bad = deepcopy(feed)
        bad["cases"][0]["ci"]["run_url"] = "https://evil.example/run/42"
        with self.assertRaisesRegex(ValueError, "ajeno"):
            validate_evidence_feed(bad, a, b)

    def test_evidence_rejects_stale_head_and_missing_case(self):
        a, b, _ = fixture()
        payload = {"schema": 1, "visibility": "public", "automatic_publication": False,
                   "safe_to_replace_public_portfolio": False,
                   "public_projects_only": True, "private_sources_inspected": False,
                   "ci_reports_consistent": True, "ci_report_disagreements": [],
                   "source_selection_generated_at": b.get("selection_generated_at"),
                   "cases": []}
        with self.assertRaisesRegex(ValueError, "incompleta"):
            validate_evidence_feed(payload, a, b)

    def test_html_prose_escaped_in_output(self):
        a, b, c = fixture()
        a["main_cases"][0]["title"] = "<script>attack()</script>"
        with self.assertRaisesRegex(ValueError, "Narrativa"):
            validate(a, b, c)
        a, b, c = fixture()
        b["candidates"][0]["title"] = "<script>alert(1)</script>"
        result = build_slides(a, b, c, stamp="fijo")
        self.assertNotIn("<script>", "".join(x["markup"] for x in result))


if __name__ == "__main__":
    unittest.main()
