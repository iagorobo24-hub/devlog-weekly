"""Isolated visual review must be safe and deterministic."""
import copy
from datetime import datetime, timezone
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from src import render_portfolio_review as mod
from src.portfolio_data import load_portfolio

REPO = "iagorobo24-hub/test-a"
SHA = "a" * 40


class ComparisonSlidesTests(unittest.TestCase):
    def setUp(self):
        self.report = {
            "schema": 1, "visibility": "public", "automatic_publication": False,
            "private_inputs_accessed": False,
            "safe_to_replace_public_portfolio": False,
            "current_portfolio": [
                {"repo": x["repo"], "pinned_revision": x["revision"]}
                for x in load_portfolio()["projects"]
            ],
            "candidates": [
                {"repo": REPO, "title": "Test", "visibility": "public",
                 "approved_for_release": False, "ci_status": "success_at_head",
                 "head": SHA, "source_presence_verified_at_revision": True,
                 "blockers": ["explicit_editorial_approval_missing"]}
            ],
            "selection_generated_at": datetime.now(timezone.utc).isoformat(),
        }
        self.profiles = {
            "visibility": "public", "automatic_publication": False,
            "drafts": [{
                "repo": REPO, "title": "Test", "visibility": "public",
                "draft_only": True, "publication_allowed": False,
                "revision": SHA, "warnings": [],
                "sources": [{"statement": "Documented file and implementation",
                             "url": f"https://github.com/{REPO}/blob/{SHA}/README.md"}]
            }]
        }
        self.data = load_portfolio()

    def build(self):
        return mod.build_review_slides(self.report, self.profiles, self.data,
                                       stamp="Fixed time")

    def test_fixed_input_is_deterministic_and_curated_slides_not_removed(self):
        once = self.build()
        self.assertEqual(once, self.build())
        self.assertEqual(len(once), 15)
        self.assertEqual(once[0]["kind"], "review-intro")
        self.assertEqual(once[-1]["kind"], "close")
        self.assertEqual(len([x for x in once if x["kind"] == "review-candidate"]), 1)
        self.assertEqual(len([x for x in once if x["kind"] == "project"]), 2)
        self.assertTrue(all("NO PUBLICAR" in x["markup"] for x in once))

    def test_ci_link_separates_execution_from_workflow_file(self):
        url = f"https://github.com/{REPO}/actions/runs/98765"
        self.report["candidates"][0]["ci_run_url_at_head"] = url
        self.assertIn(url, self.build()[-2]["markup"])
        self.report["candidates"][0]["ci_run_url_at_head"] = None
        self.assertIn("No se ha demostrado CI correcta", self.build()[-2]["markup"])

    def test_malicious_editorial_title_is_escaped(self):
        self.profiles["drafts"][0]["title"] = "<script>attack()</script>"
        slides = self.build()
        code = slides[-2]["markup"]
        self.assertNotIn("<script>", code)
        self.assertIn("&lt;script&gt;", code)

    def test_private_or_approved_data_must_fail(self):
        self.report["candidates"][0]["visibility"] = "private"
        with self.assertRaises(ValueError):
            self.build()
        self.report["candidates"][0]["visibility"] = "public"
        self.profiles["drafts"][0]["publication_allowed"] = True
        with self.assertRaises(ValueError):
            self.build()
        self.profiles["drafts"][0]["publication_allowed"] = False
        self.report["safe_to_replace_public_portfolio"] = True
        with self.assertRaises(ValueError):
            self.build()

    def test_old_revision_omits_claim_page(self):
        self.profiles["drafts"][0]["revision"] = "b" * 40
        self.assertFalse(any(x["kind"] == "review-candidate" for x in self.build()))

    def test_no_source_audit_omits_claim_page(self):
        self.report["candidates"][0]["source_presence_verified_at_revision"] = False
        self.assertFalse(any(x["kind"] == "review-candidate" for x in self.build()))

    def test_foreign_source_omits_claim_page(self):
        self.profiles["drafts"][0]["sources"][0]["url"] = "https://evil.example/fake"
        self.assertFalse(any(x["kind"] == "review-candidate" for x in self.build()))

    def test_curated_catalog_mismatch_rejected(self):
        self.report["current_portfolio"] = []
        with self.assertRaisesRegex(ValueError, "no coincide"):
            self.build()

    def test_changed_curated_revision_rejected(self):
        self.report["current_portfolio"][0]["pinned_revision"] = "b" * 40
        with self.assertRaisesRegex(ValueError, "no coincide"):
            self.build()

    def test_input_objects_unchanged(self):
        before = copy.deepcopy((self.report, self.profiles, self.data))
        self.build()
        self.assertEqual(before, (self.report, self.profiles, self.data))

    def test_preview_keeps_production_paths_separate(self):
        with TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            with patch.object(mod, "RELEASE_REPORT", tmp/"release.json"), \
                 patch.object(mod, "PROFILE_REPORT", tmp/"profiles.json"), \
                 patch.object(mod, "OUT", tmp), \
                 patch.object(mod, "MD", tmp/"review.md"), \
                 patch.object(mod, "MANIFEST", tmp/"review-manifest.json"):
                (tmp/"release.json").write_text(json.dumps(self.report))
                (tmp/"profiles.json").write_text(json.dumps(self.profiles))
                result = mod.render(stamp="Fixed time", html_output=False)
                self.assertEqual(result["slide_count"], 15)
                self.assertTrue(result["review_only"])
                self.assertFalse(result["automatic_publication"])
                self.assertTrue((tmp/"review.md").is_file())
                self.assertFalse((tmp/"portfolio-v2.pdf").exists())


if __name__ == "__main__":
    unittest.main()
