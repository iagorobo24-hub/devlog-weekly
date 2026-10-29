import unittest
from src.selection_review import build_review


class QualityReviewTests(unittest.TestCase):
    def setUp(self):
        self.selection = {
            "schema":1, "visibility":"public", "generated_at":"2026-10-29T14:00:00+00:00",
            "ranked":[{"id":"guiaia","title":"GuiaIA","visibility":"public",
                       "active_7d":True, "score":47,"repos":["owner/GuiaIA"]}]
        }
        self.editorial = {"projects":[]}
        self.quality = {
            "schema":1,"visibility":"public",
            "source_selection_generated_at":self.selection["generated_at"],
            "records":[{"repo":"owner/GuiaIA","visibility":"public",
                        "readiness":"insufficient_current_ci_evidence",
                        "evidence_score":15, "head":"a"*40,
                        "ci":{"status":"unknown"}}],
        }

    def test_quality_remains_not_auto_promotion(self):
        x=build_review(self.selection,self.editorial,self.quality)
        p=x["recommended"][0]
        self.assertTrue(x["quality_evidence_considered"])
        self.assertFalse(p["automatic_publication"])
        self.assertEqual(p["quality_checks"][0]["evidence_score"],15)
        self.assertFalse(p["quality_checks"][0]["ci_at_current_head"])
        self.assertTrue(p["requires_visual_and_functional_evidence"])

    def test_rejects_mismatched_snapshot(self):
        self.quality["source_selection_generated_at"]="old"
        with self.assertRaisesRegex(ValueError,"desactualizado"):
            build_review(self.selection,self.editorial,self.quality)

    def test_rejects_private_quality_injection(self):
        self.quality["records"][0]["visibility"]="private"
        with self.assertRaisesRegex(ValueError,"privada"):
            build_review(self.selection,self.editorial,self.quality)


if __name__=="__main__":
    unittest.main()
