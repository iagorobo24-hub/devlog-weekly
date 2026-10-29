import tempfile
import unittest
from pathlib import Path
from src import render_video_v2 as video


class PortfolioVideoContracts(unittest.TestCase):
    def test_numbered_images_reject_missing_or_duplicates(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            for n in ("slide.001.png", "slide.003.png"):
                (p/n).write_bytes(b"x")
            with self.assertRaisesRegex(ValueError, "incompleta"):
                video.numbered_images(p)

    def test_sort_numeric_images(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)
            for n in range(1,12):
                (p/f"slide.{n:03}.png").write_bytes(b"x")
            self.assertEqual(len(video.numbered_images(p)),11)
            self.assertEqual(video.numbered_images(p)[9].name,"slide.010.png")

    def test_spoken_text_and_subtitles_remove_duplicate_punctuation(self):
        dirty = "documentadas.; Contratos UDT. recurso.. dato...; otro. "
        clean = video.clean_narration(dirty)
        self.assertNotIn(".;", clean)
        self.assertNotIn("..", clean)
        captions = video.build_subtitles([dirty], [8.0])
        self.assertNotIn(".;", captions)
        self.assertNotIn("..", captions)

    def test_subtitle_timing(self):
        text=video.build_subtitles(["hola mundo, una prueba completa",
                                    "otro texto algo más largo"],[3.4,2.1])
        self.assertIn("00:00:00,000 -->",text)
        self.assertIn("00:00:03,400 -->",text)
        self.assertTrue(text.endswith("\n"))

    def test_subtitle_mismatched_lengths_rejected(self):
        with self.assertRaisesRegex(ValueError,"desincronización"):
            video.build_subtitles(["one"],[1,2])


if __name__ == "__main__":
    unittest.main()
