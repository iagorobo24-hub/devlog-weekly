"""Contract tests for the editorial portfolio, source provenance and slide planning."""
import tempfile
import unittest
from pathlib import Path

import yaml

from src.portfolio_data import load_portfolio, valid_link
from src.render_portfolio_v2 import build_slides, render_markdown, write_preview


class EditorialPortfolioTests(unittest.TestCase):
    def setUp(self):
        self.data = load_portfolio()

    def test_every_project_is_pinned_and_illustrated(self):
        self.assertEqual(len(self.data["projects"]), 2)
        for p in self.data["projects"]:
            self.assertEqual(len(p["revision"]), 40)
            self.assertGreaterEqual(len(p["evidence"]), 3)
            for image in p["asset_sources"]:
                self.assertTrue((Path(__file__).resolve().parent.parent / p[image]).is_file())

    def test_semantic_pages_not_word_fragments(self):
        slides = build_slides(self.data)
        self.assertEqual(len(slides), 2 + 3 * len(self.data["projects"]) + 1)
        self.assertEqual([s["kind"] for s in slides[:2]], ["cover", "overview"])
        for p in self.data["projects"]:
            for kind in ("project", "capabilities", "evidence"):
                self.assertEqual(len([s for s in slides if s["repo"] == p["repo"] and s["kind"] == kind]), 1)
        self.assertTrue(all(s["narration"].strip() for s in slides))

    def test_real_public_evidence_only_and_no_legacy_narrative(self):
        slides = build_slides(self.data)
        source = render_markdown(slides)
        self.assertEqual(source.count("<!-- _class: pf-"), len(slides))
        self.assertEqual(source.count("\n---\n"), len(slides))
        for p in self.data["projects"]:
            self.assertIn(p["title"], source)
            self.assertIn(p["status_detail"], source)
            for link in p["evidence"]:
                self.assertIn(link["url"], source)
        self.assertNotIn("Evolución descrita por IA", source)

    def test_disallow_html_in_editorial_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = yaml.safe_load(yaml.safe_dump(self.data))
            bad["projects"][0]["problem"] = "<script>alert(1)</script>"
            path = Path(tmp) / "projects.yml"
            path.write_text(yaml.safe_dump(bad, allow_unicode=True))
            with self.assertRaisesRegex(ValueError, "HTML"):
                load_portfolio(path)

    def test_links_do_not_escape_project_revision(self):
        p = self.data["projects"][0]
        self.assertFalse(valid_link("https://example.com/a", p["repo"], p["revision"]))
        self.assertFalse(valid_link("https://github.com/"+p["repo"]+"/blob/main/README.md", p["repo"], p["revision"]))
        self.assertFalse(valid_link("http://github.com/"+p["repo"], p["repo"], p["revision"]))
        self.assertTrue(valid_link(p["status_source"], p["repo"], p["revision"]))

    def test_schema_rejects_duplicate_projects(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = yaml.safe_load(yaml.safe_dump(self.data))
            bad["projects"].append(bad["projects"][0].copy())
            path = Path(tmp)/"projects.yml"
            path.write_text(yaml.safe_dump(bad, allow_unicode=True))
            with self.assertRaisesRegex(ValueError,"duplicado"):
                load_portfolio(path)

    def test_preview_writes_manifest_without_pdf_or_state(self):
        from unittest.mock import patch
        from src import render_portfolio_v2 as renderer
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            with patch.object(renderer,"MD_PATH",out/"preview.md"),patch.object(renderer,"MANIFEST_PATH",out/"manifest.json"):
                slides, markdown_path = write_preview(pdf=False)
                self.assertEqual(len(slides), 9)
                self.assertTrue(markdown_path.is_file())
                self.assertTrue((out/"manifest.json").is_file())
                self.assertIn('"published_to_drive": false', (out/"manifest.json").read_text())


if __name__ == "__main__":
    unittest.main()
