import unittest
from datetime import datetime, timezone

from src.portfolio_data import load_portfolio
from src.portfolio_release_review import build_review

REPO = "iagorobo24-hub/example"
HEAD = "a" * 40


class ReleasePreviewTests(unittest.TestCase):
    def setUp(self):
        timestamp = "2026-10-29T14:00:00+00:00"
        self.selection = {
            "schema": 1, "visibility": "public", "generated_at": timestamp,
            "ranked": [{"visibility": "public", "repos": [REPO]}],
            "other_active": []}
        self.quality = {
            "schema": 1, "visibility": "public",
            "source_selection_generated_at": timestamp,
            "generated_at": timestamp,
            "records": [{"repo": REPO, "visibility": "public", "head": HEAD,
                         "test_path_present": True,
                         "ci": {"status": "success_at_head"}}]}
        self.strategy = {
            "schema": 1, "visibility": "public",
            "selection_generated_at": timestamp, "automatic_publication": False,
            "private_projects_excluded": True,
            "proposed_slate": [{"repo": REPO, "visibility": "public",
                                "selection_bucket": "ranked",
                                "title": "Example", "ci_status": "success_at_head",
                                "editorial_tier": "candidate_for_manual_review",
                                "publishable": False}],
            "historical_watchlist": []}
        self.drafts = {
            "schema": 1, "visibility": "public", "automatic_publication": False,
            "drafts": [{"repo": REPO, "visibility": "public", "draft_only": True,
                        "publication_allowed": False, "revision": HEAD, "warnings": [],
                        "sources": [{"statement": "Verified file is present in repository",
                                     "url": f"https://github.com/{REPO}/blob/{HEAD}/README.md"}]}]}
        self.portfolio = load_portfolio()

    def report(self):
        return build_review(self.selection, self.quality, self.strategy,
                            self.drafts, self.portfolio,
                            now=datetime(2026, 10, 29, 15, tzinfo=timezone.utc))

    def test_successful_ci_does_not_authorize_publication(self):
        result = self.report()
        self.assertFalse(result["safe_to_replace_public_portfolio"])
        self.assertEqual(len(result["current_portfolio"]), 2)
        self.assertEqual(result["candidates"][0]["blockers"], [
            "independent_runtime_check_missing",
            "authorized_runtime_visuals_missing",
            "explicit_owner_editorial_approval_missing"])

    def test_failure_blocks_and_identifies_ci(self):
        self.quality["records"][0]["ci"]["status"] = "failure_or_cancelled"
        self.strategy["proposed_slate"][0]["ci_status"] = "failure_or_cancelled"
        self.assertIn("ci_failure_needs_diagnosis", self.report()["candidates"][0]["blockers"])

    def test_all_candidates_including_overflow(self):
        self.selection["other_active"] = self.selection.pop("ranked")
        self.selection["ranked"] = []
        self.strategy["proposed_slate"][0]["selection_bucket"] = "other_active"
        self.assertEqual(self.report()["candidates"][0]["selection_bucket"], "other_active")

    def test_stale_or_foreign_claims_never_become_evidence(self):
        self.drafts["drafts"][0]["revision"] = "b" * 40
        self.assertIn("editorial_evidence_stale_or_unverified",
                      self.report()["candidates"][0]["blockers"])
        self.drafts["drafts"][0]["revision"] = HEAD
        self.drafts["drafts"][0]["sources"][0]["url"] = "https://attacker.test/file"
        self.assertIn("editorial_evidence_stale_or_unverified",
                      self.report()["candidates"][0]["blockers"])

    def test_private_quality_or_overflow_rejected(self):
        self.quality["records"][0]["visibility"] = "private"
        with self.assertRaisesRegex(ValueError, "privad"):
            self.report()
        self.quality["records"][0]["visibility"] = "public"
        self.selection["other_active"] = [{"visibility": "private",
                                            "repos": ["iagorobo24-hub/private"]}]
        with self.assertRaisesRegex(ValueError, "privad"):
            self.report()

    def test_missing_quality_or_mismatched_ci_rejected(self):
        self.quality["records"] = []
        with self.assertRaisesRegex(ValueError, "incompleta"):
            self.report()
        self.quality["records"] = [{"repo": REPO, "visibility": "public",
                                    "ci": {"status": "unknown"}}]
        with self.assertRaisesRegex(ValueError, "contradictoria"):
            self.report()

    def test_publication_toggle_blocked(self):
        self.strategy["proposed_slate"][0]["publishable"] = True
        with self.assertRaisesRegex(ValueError, "prematura"):
            self.report()
        self.strategy["proposed_slate"][0]["publishable"] = False
        self.drafts["drafts"][0]["publication_allowed"] = True
        with self.assertRaisesRegex(ValueError, "no autorizada"):
            self.report()

    def test_stale_generation_rejected(self):
        self.strategy["selection_generated_at"] = "old"
        with self.assertRaisesRegex(ValueError, "no coinciden"):
            self.report()

    def test_stale_quality_report_rejected(self):
        self.quality["generated_at"] = "2026-10-20T12:00:00+00:00"
        with self.assertRaisesRegex(ValueError, "obsoleto"):
            self.report()

    def test_future_report_rejected(self):
        self.selection["generated_at"] = "2026-11-01T12:00:00+00:00"
        self.quality["source_selection_generated_at"] = self.selection["generated_at"]
        self.strategy["selection_generated_at"] = self.selection["generated_at"]
        with self.assertRaisesRegex(ValueError, "futuro"):
            self.report()

    def test_private_watchlist_rejected(self):
        self.selection["watchlist"] = [{"visibility": "private"}]
        with self.assertRaisesRegex(ValueError, "contaminado"):
            self.report()

    def test_historical_is_not_an_automatic_replacement(self):
        self.strategy["historical_watchlist"] = [{
            "repo": "iagorobo24-hub/old", "visibility": "public",
            "publishable": False}]
        result = self.report()
        self.assertEqual(result["historical_review_count"], 1)
        self.assertFalse(result["safe_to_replace_public_portfolio"])


if __name__ == "__main__":
    unittest.main()
