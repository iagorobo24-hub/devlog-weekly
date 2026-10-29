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
        self.assertEqual(len(slides), 2 + 3 * len(self.data["projects"])
                         + sum(len(p["walkthroughs"]) for p in self.data["projects"]) + 1)
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
            self.assertIn(p["demo_url"], source)
            for link in p["evidence"]:
                self.assertIn(link["url"], source)
        self.assertNotIn("Evolución descrita por IA", source)

    def test_recent_verified_events_are_optional_and_not_ia_claims(self):
        import json
        from src.portfolio_data import recent_activity
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)/"summaries.json"
            project = self.data["projects"][0]
            sha = "a"*40
            p.write_text(json.dumps({"repos": [{
                "name": project["repo"], "trivial": False,
                "titular": "IA: ejecución desplegada y perfecta",
                "verified_sources": [
                    {"kind":"commit", "id":sha[:10], "title":"docs: update",
                     "url":project["repo_url"]+"/commit/"+sha, "date":"2026-10-29"},
                    {"kind":"commit", "id":"bad", "title":"fake",
                     "url":"https://attacker.example/commit/"+sha, "date":"2026-10-29"}]}]}))
            activity=recent_activity(self.data["projects"], p)
            self.assertEqual(len(activity),1)
            self.assertEqual(len(activity[0]["events"]),1)
            pages=build_slides(self.data,activity)
            self.assertEqual(len(pages), 13)
            md=render_markdown(pages)
            self.assertIn("/commit/"+sha,md)
            self.assertNotIn("ejecución desplegada y perfecta",md)
            self.assertNotIn("attacker.example",md)

    def test_recent_commit_warns_without_mutating_curated_claims(self):
        import json
        from src.portfolio_data import revision_alerts
        data = self.data
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp)/"collected.json"
            f.write_text(json.dumps({"repos":[{
                "name":data["projects"][0]["repo"],
                "commits":[{"sha":"b"*40,"message":"feat: change"}]}]}))
            warnings = revision_alerts(data["projects"],f)
            self.assertEqual(len(warnings),1)
            self.assertEqual(warnings[0]["snapshot"],data["projects"][0]["revision"][:10])
            self.assertEqual(data["projects"][0]["revision"],
                             "656213a21eed2646ff85ee0e330e6e1747bbc2d5")
            slides=build_slides(data,drift=warnings)
            self.assertEqual(len(slides),13)
            self.assertEqual(slides[-2]["kind"],"drift")
            self.assertIn(warnings[0]["url"],slides[-2]["markup"])

    def test_focus_images_preserve_real_resolution(self):
        from struct import unpack
        root = Path(__file__).resolve().parent.parent
        project = self.data["projects"][1]
        for field in ("detail_image", "second_image"):
            data = (root / project[field]).read_bytes()
            self.assertEqual(data[:8], bytes.fromhex("89504e470d0a1a0a"))
            width, height = unpack(">II", data[16:24])
            self.assertGreaterEqual(width, 650)
            self.assertGreaterEqual(height, 600)

    def test_tia_evidence_is_editorial_not_tiny_plcsim_screenshot(self):
        tia = self.data["projects"][0]
        self.assertEqual(tia["detail_image"], "assets/portfolio/tia-alarm-evidence.svg")
        self.assertTrue(tia["asset_sources"]["detail_image"].endswith("evidencia-plcsim-2026-10-21.json"))
        self.assertIn("lecturas parciales", tia["detail_caption"])
        graphic = (Path(__file__).resolve().parent.parent / tia["detail_image"]).read_text()
        for expected in ("65/65", "pasos satisfactorios", "cuatro casos", "CPU virtual"):
            self.assertIn(expected, graphic)

    def test_each_walkthrough_has_a_real_figure_and_pinned_link(self):
        slides = build_slides(self.data)
        for project in self.data["projects"]:
            walkthroughs = [s for s in slides if s["repo"] == project["repo"]
                            and s["kind"] == "walkthrough"]
            self.assertEqual(len(walkthroughs), len(project["walkthroughs"]))
            for slide, walk in zip(walkthroughs, project["walkthroughs"]):
                self.assertIn('class="pf-shot pf-walk-shot"', slide["markup"])
                self.assertIn(walk["source"], slide["markup"])
                for step in walk["steps"]:
                    self.assertIn(step, slide["markup"])

    def test_author_and_generation_dates_are_distinct(self):
        slides = build_slides(self.data, generation_stamp="29/10/2026 07:30 UTC")
        self.assertIn(self.data["author"], slides[0]["markup"])
        self.assertIn("GENERADO 29/10/2026 07:30 UTC", slides[0]["markup"])
        self.assertIn(self.data["edition"], slides[0]["markup"])

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
                self.assertEqual(len(slides), 12)
                self.assertTrue(markdown_path.is_file())
                self.assertTrue((out/"manifest.json").is_file())
                self.assertIn('"published_to_drive": false', (out/"manifest.json").read_text())


if __name__ == "__main__":
    unittest.main()
