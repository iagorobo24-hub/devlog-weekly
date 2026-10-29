import unittest
from copy import deepcopy

from src.strategic_selection import build_public, classify


class StrategicSelectionTests(unittest.TestCase):
    def setUp(self):
        self.cfg = {
            "version": 1, "owner": "iagorobo24-hub",
            "recent_days": 7, "lookback_days": 30, "top_n": 5,
            "max_commits_per_repo": 200, "max_repositories": 100,
            "projects": [{"id":"guiaia","title":"GuiaIA","priority":5,
                          "repos":["iagorobo24-hub/GuiaIA"]},
                         {"id":"tia","title":"TIA","priority":4,
                          "repos":["iagorobo24-hub/TIA"]}]}
        self.sel = {"schema":1, "visibility":"public", "generated_at":"2026-10-29T14:00:00+00:00",
                    "ranked":[{"visibility":"public","title":"GuiaIA","active_7d":True,
                               "activity_score":8, "repos":["iagorobo24-hub/GuiaIA"]},
                              {"visibility":"public","title":"TIA","active_7d":True,
                               "activity_score":12, "repos":["iagorobo24-hub/TIA"]}]}
        self.qual = {"schema":1,"visibility":"public",
                     "source_selection_generated_at":self.sel["generated_at"],
                     "records":[{"repo":"iagorobo24-hub/GuiaIA","visibility":"public",
                                 "ci":{"status":"unknown"},"evidence_score":15,
                                  "test_path_present":True,"head":"b"*40},
                                {"repo":"iagorobo24-hub/TIA","visibility":"public",
                                 "ci":{"status":"success_at_head"},"evidence_score":30,
                                  "test_path_present":True,"head":"a"*40}]}
        self.drafts = {"visibility":"public","drafts":[
             {"repo":"iagorobo24-hub/GuiaIA","visibility":"public",
               "publication_allowed":False,"warnings":["missing_ci"],"revision":"b"*40},
             {"repo":"iagorobo24-hub/TIA","visibility":"public",
               "publication_allowed":False,"warnings":[],"revision":"a"*40}]}

    def test_evidence_ready_outranks_high_priority_without_head_ci(self):
        result=build_public(self.sel,self.qual,self.drafts,self.cfg)
        self.assertEqual(result["proposed_slate"][0]["repo"],"iagorobo24-hub/TIA")
        self.assertEqual(result["proposed_slate"][0]["editorial_tier"],
                         "candidate_for_manual_review")
        self.assertEqual(result["proposed_slate"][1]["editorial_tier"],
                         "strategic_high_requires_verification")
        self.assertTrue(all(not x["publishable"] for x in result["proposed_slate"]))
        self.assertTrue(result["configured_priorities_are_not_owner_approval"])
        self.assertEqual(result["proposed_slate"][0]["priority_basis"],
                         "proposed_public_config_not_owner_confirmed")

    def test_failure_is_blocked_even_with_priority(self):
        self.qual["records"][0]["ci"]["status"]="failure_or_cancelled"
        result=build_public(self.sel,self.qual,self.drafts,self.cfg)
        self.assertEqual(next(x for x in result["proposed_slate"]
                              if x["repo"].endswith("GuiaIA"))["editorial_tier"],
                         "block_until_ci_diagnosis")

    def test_unknown_priority_not_inferred_from_activity(self):
        self.cfg["projects"]=self.cfg["projects"][1:]
        result=build_public(self.sel,self.qual,self.drafts,self.cfg)
        guia=next(x for x in result["proposed_slate"] if x["repo"].endswith("GuiaIA"))
        self.assertIsNone(guia["strategic_priority"])
        self.assertEqual(guia["priority_basis"],"not_defined")

    def test_all_partitions_checked(self):
        self.drafts["drafts"][0]["visibility"]="private"
        with self.assertRaisesRegex(ValueError,"privado"):
            build_public(self.sel,self.qual,self.drafts,self.cfg)

    def test_mismatched_quality_rejected(self):
        self.qual["source_selection_generated_at"]="old"
        with self.assertRaisesRegex(ValueError,"otra revisión"):
            build_public(self.sel,self.qual,self.drafts,self.cfg)


    def test_overflow_is_included_in_strategic_review(self):
        other = {"visibility": "public", "title": "Overflow",
                 "active_7d": True, "activity_score": 6,
                 "repos": ["iagorobo24-hub/overflow"]}
        self.sel["other_active"] = [other]
        self.qual["records"].append({
            "repo": "iagorobo24-hub/overflow", "visibility": "public",
            "ci": {"status": "unknown"}, "evidence_score": 0,
            "test_path_present": False, "head": "c" * 40})
        result = build_public(self.sel, self.qual, self.drafts, self.cfg)
        row = next(r for r in result["proposed_slate"] if r["repo"].endswith("overflow"))
        self.assertEqual(row["selection_bucket"], "other_active")
        self.assertFalse(row["publishable"])
        self.assertTrue(result["all_active_candidates_considered"])

    def test_private_overflow_and_duplicate_rejected(self):
        item = dict(self.sel["ranked"][0])
        item["visibility"] = "private"
        self.sel["other_active"] = [item]
        with self.assertRaisesRegex(ValueError, "privado"):
            build_public(self.sel, self.qual, self.drafts, self.cfg)
        item["visibility"] = "public"
        with self.assertRaisesRegex(ValueError, "repetido"):
            build_public(self.sel, self.qual, self.drafts, self.cfg)




    def test_historical_priority_retained_without_promotion(self):
        self.sel["watchlist"] = [{
            "visibility": "public", "title": "Historic project",
            "repos": ["iagorobo24-hub/TIA"], "spotlight": True,
            "watch_reason": "no_substantive_activity_30d"}]
        self.sel["ranked"] = self.sel["ranked"][:1]
        result = build_public(self.sel, self.qual, self.drafts, self.cfg)
        self.assertEqual([r["repo"] for r in result["historical_watchlist"]],
                         ["iagorobo24-hub/TIA"])
        self.assertFalse(result["historical_watchlist"][0]["publishable"])
        self.assertTrue(result["historical_watchlist"][0]["requires_fresh_evidence"])

    def test_private_watchlist_is_rejected(self):
        self.sel["watchlist"] = [{"visibility": "private", "title": "Secret",
                                  "repos": ["iagorobo24-hub/private"]}]
        with self.assertRaisesRegex(ValueError, "privado"):
            build_public(self.sel, self.qual, self.drafts, self.cfg)


if __name__=="__main__":
    unittest.main()
