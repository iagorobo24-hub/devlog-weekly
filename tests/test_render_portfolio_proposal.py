"""Proposed visual narrative cannot replace current portfolio or invent proof."""
import copy
import unittest

from src.portfolio_data import load_portfolio
from src.render_portfolio_proposal import build_slides, priority_index

SHA = "a" * 40
REPOS = [
    "iagorobo24-hub/GuiaIA",
    "iagorobo24-hub/T-IA-Portal-RocaRoibas",
    "iagorobo24-hub/awesome-tia-portal",
    "iagorobo24-hub/atm10sky-es-es-localization",
    "iagorobo24-hub/AUTOMATON",
]


def fixture():
    portfolio = load_portfolio()
    candidates = []
    drafts = []
    for index, repo in enumerate(REPOS):
        ci = "failure_or_cancelled" if index == 4 else ("success_at_head" if index == 1 else "unknown")
        candidates.append({
            "repo": repo, "head": SHA,
            "title": ["GuiaIA", "TIA", "Awesome", "ATM10", "AUTOMATON"][index],
            "visibility": "public", "approved_for_release": False,
            "ci_status": ci, "source_presence_verified_at_revision": True,
            "unmerged_code_7d": 3 if index == 0 else 0, "unmerged_tests_7d": 2 if index == 0 else 0,
            "blockers": ["explicit_owner_editorial_approval_missing"],
            "ci_run_url_at_head": (f"https://github.com/{repo}/actions/runs/42"
                                   if index == 1 else None),
        })
        drafts.append({
            "repo": repo, "revision": SHA, "title": "Ficha " + str(index),
            "visibility": "public", "draft_only": True,
            "publication_allowed": False,
            "pitch": "Fuente documentada, todavía sin demostración completa.",
            "limitations": ["No se ha verificado su ejecución real."],
            "sources": [{"statement": "Documento público fijo con material de referencia.",
                         "url": f"https://github.com/{repo}/blob/{SHA}/README.md"}],
        })
    report = {
        "visibility": "public", "automatic_publication": False,
        "safe_to_replace_public_portfolio": False, "private_inputs_accessed": False,
        "current_portfolio": [
            {"repo": p["repo"], "pinned_revision": p["revision"]}
            for p in portfolio["projects"]],
        "candidates": candidates,
    }
    profiles = {"visibility": "public", "automatic_publication": False, "drafts": drafts}
    priorities = {REPOS[0]: 5, REPOS[1]: 4, REPOS[2]: 2}
    return report, profiles, portfolio, priorities


class ProposalTests(unittest.TestCase):
    def build(self):
        return build_slides(*fixture(), stamp="Corte fijo")

    def test_eight_pages_and_two_prioritized_without_any_promotion(self):
        pages = self.build()
        kinds = [x["kind"] for x in pages]
        self.assertEqual(len(pages), 8)
        self.assertEqual(kinds.count("proposal-featured"), 2)
        self.assertEqual(kinds.count("proposal-supporting"), 1)
        self.assertEqual(kinds.count("proposal-blocked"), 1)
        self.assertEqual(kinds.count("proposal-existing"), 1)
        self.assertTrue(all("NO PUBLICAR" in x["markup"] for x in pages))
        focus = [p for p in pages if p["kind"] == "proposal-featured"]
        self.assertEqual([x["repo"] for x in focus], REPOS[:2])
        self.assertIn("CI de la rama principal sin confirmar", focus[0]["markup"])
        self.assertIn("Ejecución CI al HEAD", focus[1]["markup"])
        self.assertIn("AUTOMATON", next(p["markup"] for p in pages
                                      if p["kind"] == "proposal-blocked"))

    def test_proposal_does_not_change_catalog_or_inputs(self):
        args = fixture()
        before = copy.deepcopy(args)
        self.assertEqual(self.build(), self.build())
        build_slides(*args)
        self.assertEqual(before, args)
        self.assertEqual(len([p for p in args[2]["projects"]]), 2)

    def test_missing_pinned_source_does_not_appear_as_verified(self):
        args = list(fixture())
        args[0]["candidates"][0]["source_presence_verified_at_revision"] = False
        pages = build_slides(*args)
        focus = next(p for p in pages if p["kind"] == "proposal-featured")
        self.assertIn("Sin referencias auditadas", focus["markup"])
        self.assertNotIn("Documento público fijo", focus["markup"])

    def test_foreign_source_and_ci_links_rejected(self):
        args = list(fixture())
        args[1]["drafts"][0]["sources"][0]["url"] = "https://attacker.test/README"
        with self.assertRaisesRegex(ValueError, "versionadas"):
            build_slides(*args)
        args = list(fixture())
        args[0]["candidates"][1]["ci_run_url_at_head"] = "https://fake.test/run"
        with self.assertRaisesRegex(ValueError, "ajeno"):
            build_slides(*args)

    def test_approved_candidate_and_incorrect_curated_catalog_rejected(self):
        args = list(fixture())
        args[0]["candidates"][0]["approved_for_release"] = True
        with self.assertRaises(ValueError):
            build_slides(*args)
        args = list(fixture())
        args[0]["current_portfolio"] = []
        with self.assertRaisesRegex(ValueError, "no coincide"):
            build_slides(*args)

    def test_hostile_title_escaped(self):
        args = list(fixture())
        args[1]["drafts"][0]["title"] = "<script>alert(1)</script>"
        rendered = build_slides(*args)
        joined = "".join(x["markup"] for x in rendered)
        self.assertIn("&lt;script&gt;", joined)
        self.assertNotIn("<script>", joined)

    def test_priority_map_is_provisional_and_validated(self):
        cfg = {"version": 1, "owner": "iagorobo24-hub", "recent_days": 7,
               "lookback_days": 30, "max_commits_per_repo": 200,
               "max_repositories": 100, "top_n": 5,
               "projects": [
                   {"id": "guiaia", "title": "GuiaIA", "priority": 5,
                    "repos": [REPOS[0]]}]}
        self.assertEqual(priority_index(cfg)[REPOS[0]], 5)
        args = list(fixture())
        args[3][REPOS[0]] = 9
        with self.assertRaisesRegex(ValueError, "Prioridades"):
            build_slides(*args)


if __name__ == "__main__":
    unittest.main()
