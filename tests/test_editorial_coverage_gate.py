"""Coverage from synchronized public inputs must not imply deployment."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import unittest

from src.editorial_coverage_gate import build, markdown

NOW = datetime(2026, 10, 29, 18, tzinfo=timezone.utc)
STAMP = NOW.isoformat()
REPOS = ("iagorobo24-hub/GuiaIA", "iagorobo24-hub/AUTOMATON")
SHA = "a" * 40
GATES = ["independent_runtime_check_missing",
         "authorized_runtime_visuals_missing",
         "explicit_owner_editorial_approval_missing"]


def reports():
    selection = {
        "schema": 1, "visibility": "public", "generated_at": STAMP,
        "ranked": [{"visibility": "public", "repos": [REPOS[0]]}],
        "other_active": [{"visibility": "public", "repos": [REPOS[1]]}],
    }
    quality = {
        "schema": 1, "visibility": "public",
        "generated_at": STAMP, "source_selection_generated_at": STAMP,
        "records": [
            {"repo": REPOS[0], "visibility": "public", "head": SHA,
             "ci": {"status": "unknown"}},
            {"repo": REPOS[1], "visibility": "public", "head": SHA,
             "ci": {"status": "failure_or_cancelled"}},
        ],
    }
    strategy = {
        "schema": 1, "visibility": "public", "automatic_publication": False,
        "selection_generated_at": STAMP,
        "proposed_slate": [
            {"repo": name, "visibility": "public", "publishable": False,
             "selection_bucket": "ranked" if i == 0 else "other_active",
             "ci_status": "unknown" if i == 0 else "failure_or_cancelled",
             "editorial_tier": "strategic_high_requires_verification"}
            for i, name in enumerate(REPOS)],
    }
    drafts = {
        "schema": 1, "visibility": "public", "automatic_publication": False,
        "drafts": [
            {"repo": name, "visibility": "public", "revision": SHA,
             "draft_only": True, "publication_allowed": False}
            for name in REPOS],
    }
    sources = {
        "schema": 1, "visibility": "public",
        "automatic_publication": False, "no_private_data": True,
        "not_functionality_validation": True,
        "source_selection_generated_at": STAMP,
        "source_quality_generated_at": STAMP,
        "probes": [
            {"repo": name, "visibility": "public", "revision": SHA,
             "quality_head_matches_revision": True,
             "all_sources_exist_at_pinned_revision": True,
             "sources": [{"status": "present"}]}
            for name in REPOS],
    }
    release = {
        "schema": 1, "visibility": "public",
        "selection_generated_at": STAMP,
        "automatic_publication": False,
        "safe_to_replace_public_portfolio": False,
        "private_inputs_accessed": False,
        "current_portfolio": [
            {"repo": "iagorobo24-hub/published", "visibility": "public",
             "pinned_revision": SHA, "replacement_automatically_allowed": False}],
        "candidates": [
            {"repo": name, "visibility": "public",
             "selection_bucket": "ranked" if i == 0 else "other_active",
             "ci_status": "unknown" if i == 0 else "failure_or_cancelled",
             "approved_for_release": False,
             "source_presence_verified_at_revision": True,
             "blockers": list(GATES),
             "feature_branch_ci": []}
            for i, name in enumerate(REPOS)],
    }
    return dict(selection=selection, quality=quality, strategy=strategy,
                drafts=drafts, sources=sources, release=release)


class EditorialCoverageTests(unittest.TestCase):
    def test_all_drafts_and_paths_counted_without_approvals(self):
        r = build(**reports(), now=NOW)
        self.assertEqual(r["active_candidate_count"], 2)
        self.assertEqual(r["current_draft_count"], 2)
        self.assertEqual(r["source_verified_candidate_count"], 2)
        self.assertEqual(r["publication_approved_count"], 0)
        self.assertTrue(r["source_paths_are_not_functional_proof"])
        self.assertFalse(r["automatic_publication"])
        self.assertTrue(all(not x["approved_for_release"] for x in r["candidates"]))

    def test_missing_draft_is_visible_and_never_promoted(self):
        data = reports()
        data["drafts"]["drafts"].pop()
        data["sources"]["probes"].pop()
        data["release"]["candidates"][1]["source_presence_verified_at_revision"] = False
        r = build(**data, now=NOW)
        self.assertEqual(r["missing_draft_count"], 1)
        self.assertEqual(r["source_verified_candidate_count"], 1)
        self.assertFalse(r["candidates"][1]["has_draft"])

    def test_stale_revision_cannot_count_as_current(self):
        data = reports()
        data["quality"]["records"][0]["head"] = "b" * 40
        data["sources"]["probes"][0]["quality_head_matches_revision"] = False
        data["sources"]["probes"][0]["all_sources_exist_at_pinned_revision"] = False
        data["release"]["candidates"][0]["source_presence_verified_at_revision"] = False
        r = build(**data, now=NOW)
        self.assertEqual(r["current_draft_count"], 1)
        self.assertFalse(r["candidates"][0]["source_paths_present_at_head"])

    def test_source_audit_and_release_mismatch_rejected(self):
        data = reports()
        data["release"]["candidates"][0]["source_presence_verified_at_revision"] = False
        with self.assertRaisesRegex(ValueError, "discrepan"):
            build(**data, now=NOW)

    def test_private_sources_or_release_rejected(self):
        data = reports()
        data["sources"]["probes"][0]["visibility"] = "private"
        with self.assertRaisesRegex(ValueError, "privada"):
            build(**data, now=NOW)
        data = reports()
        data["release"]["private_inputs_accessed"] = True
        with self.assertRaisesRegex(ValueError, "privada"):
            build(**data, now=NOW)

    def test_missing_owner_gate_is_rejected(self):
        data = reports()
        data["release"]["candidates"][0]["blockers"].remove(
            "explicit_owner_editorial_approval_missing")
        with self.assertRaisesRegex(ValueError, "Puertas"):
            build(**data, now=NOW)

    def test_no_publish_flag_can_pass(self):
        data = reports()
        data["strategy"]["proposed_slate"][1]["publishable"] = True
        with self.assertRaisesRegex(ValueError, "promocionado"):
            build(**data, now=NOW)
        data = reports()
        data["release"]["safe_to_replace_public_portfolio"] = True
        with self.assertRaisesRegex(ValueError, "automática"):
            build(**data, now=NOW)

    def test_wrong_ci_state_or_bucket_cannot_cross_reference(self):
        data = reports()
        data["strategy"]["proposed_slate"][0]["ci_status"] = "success_at_head"
        with self.assertRaisesRegex(ValueError, "contradictorio"):
            build(**data, now=NOW)
        data = reports()
        data["release"]["candidates"][0]["selection_bucket"] = "other_active"
        with self.assertRaisesRegex(ValueError, "contradictorio"):
            build(**data, now=NOW)

    def test_future_stale_or_mixed_snapshots_fail(self):
        data = reports()
        with self.assertRaisesRegex(ValueError, "obsoleta"):
            build(**data, now=NOW + timedelta(days=3))
        with self.assertRaisesRegex(ValueError, "futura"):
            build(**data, now=NOW - timedelta(days=1))
        data["strategy"]["selection_generated_at"] = "older"
        with self.assertRaisesRegex(ValueError, "desincronizados"):
            build(**data, now=NOW)

    def test_markdown_is_internal_and_displays_failures(self):
        r = build(**reports(), now=NOW)
        md = markdown(r)
        self.assertIn("NO PUBLICAR", md)
        self.assertIn("failure_or_cancelled", md)
        self.assertIn("iagorobo24-hub/GuiaIA", md)
        self.assertIn("Portfolio Maestro", md)
        self.assertNotIn("aprobado para publicar", md.lower())
        with self.assertRaisesRegex(ValueError, "no seguro"):
            markdown(dict(r, automatic_publication=True))


if __name__ == "__main__":
    unittest.main()
