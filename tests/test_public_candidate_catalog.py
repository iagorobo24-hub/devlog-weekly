"""Complete public editorial coverage without automatic promotion or runtime claims.

The test does not reach GitHub. External source existence is verified by the
separate public candidate-source audit against immutable commit SHAs.
"""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import unittest

import yaml

from src.candidate_profiles import CANDIDATES, validate
from src.portfolio_data import load_portfolio
from src.render_portfolio_review import build_review_slides

PINNED = {
    "tia-rocaroibas": ("iagorobo24-hub/T-IA-Portal-RocaRoibas",
                       "5bb5397297724e2c3a4c1c7e67b4132368f12516"),
    "guiaia": ("iagorobo24-hub/GuiaIA",
               "060497ccb56bb0a2e9b5e488c84256e51bfbf2ef"),
    "atm10sky-es-es-localization": ("iagorobo24-hub/atm10sky-es-es-localization",
                                     "1e0c648aafbf0204de1eaa2a191bcb7faf13b8c1"),
    "automaton": ("iagorobo24-hub/AUTOMATON",
                   "710179ba1d4de55c6ed3a81776d1521ad9581d09"),
    "awesome-tia-portal": ("iagorobo24-hub/awesome-tia-portal",
                            "656213a21eed2646ff85ee0e330e6e1747bbc2d5"),
}
GATES = ("independent_functional_check_required",
         "runtime_evidence_required",
         "explicit_editorial_approval_required")


def profiles():
    return {
        p.stem: yaml.safe_load(p.read_text(encoding="utf-8"))
        for p in sorted(CANDIDATES.glob("*.yml"))
    }


def synthetic_quality(profile, *, passed=False):
    return {
        "repo": profile["repo"], "visibility": "public",
        "head": profile["revision"],
        "readiness": "ci_head_passed_tests_exist" if passed else "requires_verification",
        "ci": {"status": "success_at_head" if passed else "unknown"},
    }


class PublicCandidateCatalogTests(unittest.TestCase):
    def test_all_five_known_active_public_cases_have_unique_pinned_drafts(self):
        found = profiles()
        self.assertEqual(set(found), set(PINNED))
        self.assertEqual(len({p["repo"] for p in found.values()}), 5)
        for key, (repo, revision) in PINNED.items():
            with self.subTest(candidate=key):
                profile = found[key]
                self.assertEqual(profile["repo"], repo)
                self.assertEqual(profile["revision"], revision)
                self.assertEqual(profile["visibility"], "public")
                self.assertEqual(profile["editorial_status"], "draft_only")
                self.assertEqual(profile["version"], 1)
                self.assertTrue(all(profile["publication_gate"][name] is True
                                    for name in GATES))

    def test_three_new_profiles_claim_only_pinned_document_or_file_sources(self):
        found = profiles()
        for key in ("atm10sky-es-es-localization", "automaton",
                    "awesome-tia-portal"):
            with self.subTest(candidate=key):
                profile = found[key]
                review = validate(profile, synthetic_quality(profile))
                self.assertFalse(review["publication_allowed"])
                self.assertTrue(review["draft_only"])
                self.assertIn("head_ci_or_test_evidence_incomplete", review["warnings"])
                self.assertEqual(len(review["sources"]), 3)
                self.assertTrue(profile["limitations"])
                for source in review["sources"]:
                    self.assertIn(source["evidence_kind"],
                                  ("documented", "repository_file"))
                    self.assertTrue(source["url"].startswith(
                        "https://github.com/" + profile["repo"] +
                        "/blob/" + profile["revision"] + "/"))
                    self.assertFalse(source["is_independently_verified"])
                self.assertEqual(profile.get("images"), [])

    def test_failure_or_unknown_ci_does_not_promote_new_drafts(self):
        for key in ("automaton", "atm10sky-es-es-localization",
                    "awesome-tia-portal"):
            profile = profiles()[key]
            quality = synthetic_quality(profile)
            if key == "automaton":
                quality["ci"]["status"] = "failure_or_cancelled"
            review = validate(profile, quality)
            self.assertFalse(review["publication_allowed"])
            self.assertNotIn("ci_at_head",
                             [s["evidence_kind"] for s in review["sources"]])

    def test_all_five_fit_separate_review_deck_without_touching_curated_cases(self):
        found = profiles()
        portfolio = load_portfolio()
        before = deepcopy(portfolio)
        drafts = [validate(p, synthetic_quality(p, passed=k == "tia-rocaroibas"))
                  for k, p in sorted(found.items())]
        report = {
            "schema": 1, "visibility": "public",
            "automatic_publication": False,
            "private_inputs_accessed": False,
            "safe_to_replace_public_portfolio": False,
            "current_portfolio": [
                {"repo": p["repo"], "pinned_revision": p["revision"]}
                for p in portfolio["projects"]
            ],
            "candidates": [
                {
                    "repo": p["repo"], "title": p["title"],
                    "visibility": "public", "head": p["revision"],
                    "source_presence_verified_at_revision": True,
                    "approved_for_release": False, "ci_status": "unknown",
                    "blockers": ["explicit_editorial_approval_missing"],
                }
                for p in found.values()
            ],
        }
        review = build_review_slides(
            report, {"visibility": "public", "automatic_publication": False,
                     "drafts": drafts}, portfolio, stamp="Catalog QA fixed")
        self.assertEqual(len([p for p in review if p["kind"] == "review-candidate"]), 5)
        self.assertEqual(len([p for p in review if p["kind"] == "project"]), 2)
        self.assertEqual(len(review), 19)
        self.assertTrue(all("NO PUBLICAR" in p["markup"] for p in review))
        self.assertEqual(before, portfolio)

    def test_stale_candidate_revision_does_not_create_false_claim_page(self):
        found = profiles()
        portfolio = load_portfolio()
        drafts = [validate(p, synthetic_quality(p)) for p in found.values()]
        report = {
            "visibility": "public", "automatic_publication": False,
            "private_inputs_accessed": False,
            "safe_to_replace_public_portfolio": False,
            "current_portfolio": [{"repo": p["repo"],
                                   "pinned_revision": p["revision"]}
                                  for p in portfolio["projects"]],
            "candidates": [{
                "repo": p["repo"], "title": p["title"],
                "visibility": "public", "head": p["revision"],
                "source_presence_verified_at_revision": True,
                "approved_for_release": False,
                "blockers": ["independent_runtime_check_missing"],
            } for p in found.values()],
        }
        target = next(x for x in drafts
                      if x["repo"] == "iagorobo24-hub/AUTOMATON")
        target["revision"] = "f"*40
        review = build_review_slides(
            report, {"visibility": "public", "automatic_publication": False,
                     "drafts": drafts}, portfolio, stamp="Catalog QA fixed")
        self.assertEqual(len([p for p in review if p["kind"] == "review-candidate"]), 4)


if __name__ == "__main__":
    unittest.main()
