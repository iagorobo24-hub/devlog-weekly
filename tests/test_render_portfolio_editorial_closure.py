"""Editorial selection closure: stable public-only content, not publication."""
from copy import deepcopy
import unittest
import yaml

from src.portfolio_data import load_portfolio
from src.render_portfolio_editorial_closure import (
    SELECTION, build_slides, validate,
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
        self.assertEqual([x["repo"] for x in primary], REPOS[:3])
        self.assertEqual([x["repo"] for x in supporting], REPOS[3:5])
        self.assertEqual([x["repo"] for x in excluded], REPOS[5:])
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
