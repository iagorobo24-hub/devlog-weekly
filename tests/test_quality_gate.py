"""Read-only quality gate inputs can be validated without a PDF parser."""
import json
import tempfile
import unittest
from pathlib import Path

from src.portfolio_data import load_portfolio
from src.quality_gate import validate_manifest
from src.render_portfolio_v2 import build_slides


class QualityGateTests(unittest.TestCase):
    def test_rejects_missing_or_wrong_revision(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)/"manifest.json"
            data = load_portfolio()
            expected = {x["repo"]: x["revision"] for x in data["projects"]}
            slides = build_slides(data)
            sample = {"schema": 2, "published_to_drive": False,
                      "project_revisions": expected, "slides":
                      [{"index":i,"narration":s["narration"]} for i,s in enumerate(slides,1)]}
            p.write_text(json.dumps(sample))
            self.assertEqual(len(validate_manifest(p,expected)),len(slides))
            with self.assertRaisesRegex(ValueError, "revisiones"):
                validate_manifest(p,{"unknown":"bad"})
            sample["slides"][2]["index"] = 42
            p.write_text(json.dumps(sample))
            with self.assertRaisesRegex(ValueError,"consecutivos"):
                validate_manifest(p,expected)

    def test_rejects_manifests_claiming_publication(self):
        data=load_portfolio()
        expected={x["repo"]:x["revision"] for x in data["projects"]}
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/"manifest.json"
            p.write_text(json.dumps({"schema":2, "project_revisions": expected,
                                      "slides":[{"index":1,"narration":"hello"}],
                                      "published_to_drive":True}))
            with self.assertRaisesRegex(ValueError,"publicado"):
                validate_manifest(p,expected)


if __name__ == "__main__":
    unittest.main()
