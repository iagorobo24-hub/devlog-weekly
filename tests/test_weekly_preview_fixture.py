"""CI preview must use a coherent SYNTHETIC source chain, never live data."""
from argparse import Namespace
from contextlib import ExitStack
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import yaml

from src import deck_provenance, render
from tests.prepare_weekly_preview import prepare


ROOT = Path(__file__).resolve().parent.parent


class WeeklyPreviewFixtureTests(unittest.TestCase):
    def test_fixture_matches_collection_hash_and_has_no_real_run_id(self):
        with tempfile.TemporaryDirectory(prefix="devlog-demo-fixture-") as temp:
            collected, summary = prepare(
                ROOT / "tests/fixtures/weekly_sample.json", Path(temp) / "out")
            fingerprint = deck_provenance.verify_collected_source(collected, summary)
            data = json.loads(summary.read_text())
            source = json.loads(collected.read_text())
            self.assertEqual(data["source_collected_sha256"], fingerprint)
            self.assertIsNone(data["github_run_id"])
            self.assertIsNone(source["github_run_id"])
            self.assertTrue(source["fixture_only"])
            self.assertTrue(all(row["fixture_only"] for row in source["repos"]))
            self.assertEqual(len(source["repos"]), len(data["repos"]))
            collected.write_text(collected.read_text() + " ")
            with self.assertRaisesRegex(ValueError, "desacoplada"):
                deck_provenance.verify_collected_source(collected, summary)

    def test_demo_renders_markdown_through_real_provenance_gate(self):
        with tempfile.TemporaryDirectory(prefix="devlog-demo-render-") as temp:
            base = Path(temp)
            collected, summary = prepare(
                ROOT / "tests/fixtures/weekly_sample.json", base / "out")
            with ExitStack() as stack:
                stack.enter_context(patch.object(deck_provenance, "COLLECTED_PATH", collected))
                stack.enter_context(patch.object(render, "SUMMARIES_PATH", summary))
                stack.enter_context(patch.object(render, "DECK_MD_PATH", base / "out/deck.md"))
                stack.enter_context(patch.object(render, "DECK_PDF_PATH", base / "out/deck.pdf"))
                stack.enter_context(patch.object(render, "parse_args",
                                                 return_value=Namespace(no_pdf=True)))
                render.main()
            self.assertIn("Resumen de actividad",
                          (base / "out/deck.md").read_text())
            self.assertFalse((base / "out/deck.pdf").exists())

    def test_workflow_runs_fixture_generator_before_renderer(self):
        data = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())
        steps = data["jobs"]["preview"]["steps"]
        command = next(s["run"] for s in steps if s.get("name") ==
                       "Crear demostración sin secretos ni publicar")
        self.assertIn("tests.prepare_weekly_preview", command)
        self.assertLess(command.index("tests.prepare_weekly_preview"),
                        command.index("src/render.py"))
        self.assertNotIn("cp tests/fixtures/weekly_sample.json", command)


if __name__ == "__main__":
    unittest.main()
