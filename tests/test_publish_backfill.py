"""Protección de carpetas y no sobrescritura del archivo histórico."""
import json
import tempfile
import unittest
from pathlib import Path

from src import publish_backfill


class HistoryPublishTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.manifest = {"source": "public-github-metadata", "model": None,
                         "state_modified": False, "drive_uploaded": False,
                         "weeks": [{"week": "2026-W36"}, {"week": "2026-W37"}]}

    def write(self):
        (self.folder / "manifest.json").write_text(json.dumps(self.manifest))
        for week in ("2026-W36", "2026-W37"):
            for ext in (".md", ".pdf"):
                (self.folder / (week + ext)).write_text("contenido")

    def test_distinct_target_and_all_files(self):
        self.write()
        plan = publish_backfill.make_upload_plan(self.folder, "gdrive")
        self.assertEqual(len(plan), 5)
        self.assertTrue(all("Portfolio/historico-verificable/2026-W36__2026-W37/" in dest
                            for _, dest in plan))
        self.assertTrue(all("Portfolio/semanal/" not in dest and
                            "Portfolio/master/" not in dest for _, dest in plan))

    def test_missing_pdf_blocks_entire_plan(self):
        self.write()
        (self.folder / "2026-W37.pdf").unlink()
        with self.assertRaisesRegex(ValueError, "ausente"):
            publish_backfill.make_upload_plan(self.folder, "gdrive")

    def test_rejects_nonpublic_manifest(self):
        self.write()
        self.manifest["source"] = "private"
        (self.folder / "manifest.json").write_text(json.dumps(self.manifest))
        with self.assertRaisesRegex(ValueError, "públicos"):
            publish_backfill.make_upload_plan(self.folder, "gdrive")

    def test_rejects_duplicate_weeks(self):
        self.write()
        self.manifest["weeks"].append({"week": "2026-W37"})
        (self.folder / "manifest.json").write_text(json.dumps(self.manifest))
        with self.assertRaisesRegex(ValueError, "repetidas"):
            publish_backfill.make_upload_plan(self.folder, "gdrive")


if __name__ == "__main__":
    unittest.main()
