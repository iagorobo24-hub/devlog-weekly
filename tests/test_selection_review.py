import unittest

from src.selection_review import build_review


class SelectionReviewTests(unittest.TestCase):
    def setUp(self):
        self.editorial = {"projects": [{"repo": "iagorobo24-hub/awesome-tia-portal"},
                                       {"repo": "iagorobo24-hub/proyecto-pfc-iago-duran"}]}
        self.selection = {
            "schema": 1, "visibility": "public", "generated_at": "2026-10-29T12:00:00+00:00",
            "ranked": [
                {"id": "GuiaIA", "title": "GuiaIA", "score": 41.2, "active_7d": True,
                 "visibility": "public", "repos": ["iagorobo24-hub/GuiaIA"]},
                {"id": "TIA", "title": "Awesome", "score": 14.0, "active_7d": False,
                 "visibility": "public", "repos": ["iagorobo24-hub/awesome-tia-portal"]},
            ],
        }

    def test_recommend_missing_project_without_autopublish(self):
        result = build_review(self.selection, self.editorial)
        self.assertFalse(result["automatic_publication"])
        self.assertEqual(result["recommended"][0]["decision"], "prepare_evidence_profile")
        self.assertEqual(result["recommended"][1]["decision"], "review_existing_profile")
        self.assertEqual(result["showcase_not_in_top_candidates"],
                         ["iagorobo24-hub/proyecto-pfc-iago-duran"])
        self.assertTrue(all(not p["automatic_publication"] for p in result["recommended"]))

    def test_rejects_private_or_mixed_candidate(self):
        self.selection["ranked"][0]["visibility"] = "private"
        with self.assertRaisesRegex(ValueError, "privado"):
            build_review(self.selection, self.editorial)
        self.selection["visibility"] = "private-local"
        with self.assertRaisesRegex(ValueError, "públicos"):
            build_review(self.selection, self.editorial)


    def test_overflow_receives_editorial_review(self):
        self.selection["other_active"] = [{
            "id": "overflow", "title": "Overflow", "score": 5.0,
            "active_7d": False, "visibility": "public",
            "repos": ["iagorobo24-hub/overflow"]}]
        report = build_review(self.selection, self.editorial)
        self.assertEqual(len(report["recommended"]), 3)
        self.assertEqual(report["recommended"][2]["selection_bucket"], "other_active")
        self.assertEqual(report["recommended"][2]["decision"], "prepare_evidence_profile")
        self.assertFalse(report["recommended"][2]["automatic_publication"])



if __name__ == "__main__":
    unittest.main()
