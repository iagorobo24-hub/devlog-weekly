"""Master PDF and narrated-video contracts: page preservation and one-to-one alignment."""
import unittest
from pathlib import Path
from src import render_master


class TestPortfolioQuality(unittest.TestCase):
    def test_long_narrative_keeps_all_words(self):
        words = [f"marker{i:03d}" for i in range(190)]
        entries = [{"name": "sample/long-project", "pitch": "Demo",
                    "narrativa": " ".join(words), "sources": []}]
        slides = render_master.build_slides(entries)
        self.assertEqual(len(slides), 3)
        for word in words:
            self.assertEqual(sum(word in s["body"].split() for s in slides), 1)
        self.assertEqual(slides[0]["part"], 1)
        self.assertEqual(slides[2]["total"], 3)

    def test_pages_are_balanced_without_orphan_fragments(self):
        entries = [{"name": "sample/repo", "pitch": "Demo",
                    "narrativa": " ".join(f"item{i:03d}" for i in range(143)), "sources": []}]
        slides = render_master.build_slides(entries)
        self.assertEqual(len(slides), 2)
        lengths = [len(slide["body"].split()) for slide in slides]
        self.assertEqual(sum(lengths), 143)
        self.assertLessEqual(max(lengths) - min(lengths), 1)
        self.assertTrue(all(length <= 80 for length in lengths))

    def test_real_sources_only_and_separate_slide(self):
        items = [{"name": "sample/project", "pitch": "Demo", "narrativa": "Avance.",
                  "sources": [
                      {"id": "abcdef1234", "title": "Test", "date": "2026-10-27",
                       "url": "https://github.com/sample/project/commit/" + "a"*40},
                      {"id": "bad", "title": "Outside", "date": "2026-10-27",
                       "url": "https://example.com/unsafe"},
                  ]}]
        slides = render_master.build_slides(items)
        self.assertEqual(len(slides), 2)
        self.assertEqual(slides[-1]["kind"], "sources")
        md = render_master.render_markdown(items)
        self.assertIn("https://github.com/sample/project/commit/", md)
        self.assertNotIn("example.com", md)
        self.assertIn("no acredita por sí misma", md)

    def test_template_consistent_with_slide_count(self):
        entries = [{"name": "example/project", "pitch": "",
                    "narrativa": " ".join(["hello"] * 150), "sources": []}]
        slides = render_master.build_slides(entries)
        markdown = render_master.render_markdown(entries)
        self.assertEqual(markdown.count("<!-- _class: portfolio -->"), len(slides))
        self.assertEqual(len(slides), 2)
        # Marp needs an empty line before every slide delimiter. A count of
        # Jinja slide entries alone does not verify actual slide boundaries.
        self.assertEqual(markdown.count("\n\n---\n\n"), len(slides))

    def test_video_sorting_is_numeric_after_ten_pages(self):
        import tempfile
        from unittest.mock import patch
        from src import render_video
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            for ix in (2, 1, 10, 12, 3):
                (folder / f"slide.{ix}.png").write_bytes(b"not an actual PNG")
            with patch.object(render_video, "WORK_DIR", folder):
                with patch.object(render_video, "require_tool", return_value="marp"):
                    with patch.object(render_video.subprocess, "run"):
                        items = render_video.export_slide_images()
        self.assertEqual([p.name for p in items],
                         ["slide.1.png", "slide.2.png", "slide.3.png",
                          "slide.10.png", "slide.12.png"])

    def test_video_uses_one_narration_per_actual_slide(self):
        import argparse
        import tempfile
        from unittest.mock import patch
        from src import render_video
        entries = [{"name": "sample/demo", "pitch": "Demo",
                    "narrativa": " ".join(["progreso"] * 190),
                    "sources": [{"id": "a"*10, "title": "Fix",
                                 "date": "2026-10-29",
                                 "url": "https://github.com/sample/demo/commit/" + "a"*40}]}]
        slides = render_master.build_slides(entries)
        narration = []
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            md = folder / "portfolio.md"
            md.write_text(render_master.render_markdown(entries))
            images = [folder / f"slide.{i}.png" for i in range(1, len(slides) + 2)]
            for path in images:
                path.write_bytes(b"placeholder")
            with patch.object(render_video, "parse_args",
                              return_value=argparse.Namespace(force=True, voice="es-ES-AlvaroNeural")):
                with patch.object(render_video, "load_showcase_repos", return_value=[{"name": "sample/demo"}]):
                    with patch.object(render_video, "load_portfolio_entries", return_value=entries):
                        with patch.object(render_video, "PORTFOLIO_MD_PATH", md):
                            with patch.object(render_video, "WORK_DIR", folder / "clips"):
                                with patch.object(render_video, "require_tool", return_value="mocked"):
                                    with patch.object(render_video, "export_slide_images", return_value=images):
                                        with patch.object(render_video, "synthesize_audio",
                                                          side_effect=lambda text, *args: narration.append(text)):
                                            with patch.object(render_video, "build_segment"):
                                                with patch.object(render_video, "concat_segments") as concatenator:
                                                    render_video.main()
                                                    concatenator.assert_called_once()
                                                    self.assertEqual(len(concatenator.call_args.args[0]), len(images))
        self.assertEqual(len(narration), len(slides) + 1)
        self.assertTrue(narration[0].startswith("Portfolio"))
        self.assertEqual(narration[1:], [slide["narration"] for slide in slides])

    def test_blocks_untrusted_repo_names(self):
        with self.assertRaisesRegex(ValueError, "invalid GitHub repository"):
            render_master.build_slides([{"name": "sample/evil) [inject](https://unsafe.test",
                                        "narrativa": "Some text", "sources": []}])


if __name__ == "__main__":
    unittest.main()
