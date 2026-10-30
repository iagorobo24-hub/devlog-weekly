"""End-to-end deterministic weekly path without GitHub, LLM, Marp or Drive."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from argparse import Namespace
from contextlib import ExitStack
from unittest.mock import patch

from src import confirm_pipeline_state as state
from src import deck_provenance, publish, render, synthesize


class OfflineWeeklyIntegrationTests(unittest.TestCase):
    def test_collect_synthesize_preflight_render_publish_then_commit(self):
        with tempfile.TemporaryDirectory(prefix="devlog-e2e-offline-") as directory:
            base = Path(directory)
            out, storage, narrative, config = (base / "out", base / "state",
                                                base / "state" / "narrative",
                                                base / "repos.yml")
            out.mkdir()
            templates = base / "templates"
            templates.mkdir()
            (templates / render.TEMPLATE_NAME).write_bytes(
                (render.TEMPLATE_DIR / render.TEMPLATE_NAME).read_bytes())
            (templates / "theme.css").write_bytes(render.THEME_PATH.read_bytes())
            narrative.mkdir(parents=True)
            config.write_text("repos:\n  - name: example/alpha\n")
            initial = {"example/alpha": {"since": "2026-10-28T20:00:00+00:00",
                                         "tags_seen": []}}
            (storage / "last_run.json").write_text(json.dumps(initial))
            collected = {
                "generated_at": "2026-10-29T20:00:00+00:00",
                "github_run_id": "987654321",
                "repos": [{
                    "name": "example/alpha",
                    "since": "2026-10-28T20:00:00+00:00",
                    "until": "2026-10-29T20:00:00+00:00",
                    "tags_all": [], "tags_new": [], "commits": [],
                    "issues_closed": [], "prs_closed": [], "showcase": False,
                    "pitch": "Proyecto de demostración",
                    "diff_stats": {"files_changed": 0, "additions": 0,
                                   "deletions": 0},
                }],
            }
            (out / "collected.json").write_text(json.dumps(collected))
            previous_md = narrative / "alpha.md"
            previous_md.write_text("Historia previa de prueba\n")
            previous_bytes = (storage / "last_run.json").read_bytes()

            def convert(_md, pdf):
                pdf.write_bytes(b"%PDF-1.4\n" + b"offline test data" * 30
                                + b"\n%%EOF")

            with ExitStack() as stack:
                stack.enter_context(patch.dict(os.environ, {
                    "GITHUB_RUN_ID": "987654321",
                    "GITHUB_RUN_ATTEMPT": "1",
                    "NVIDIA_API_KEY": "offline-placeholder",
                    "RCLONE_CONF": "offline-placeholder",
                }))
                for module, attrs in (
                    (state, {
                        "COLLECTED_PATH": out / "collected.json",
                        "SUMMARIES_PATH": out / "summaries.json",
                        "LAST_RUN_PATH": storage / "last_run.json",
                        "NARRATIVE_DIR": narrative,
                        "CONFIG_PATH": config,
                    }),
                    (synthesize, {
                        "COLLECTED_PATH": out / "collected.json",
                        "OUT_PATH": out / "summaries.json",
                        "NARRATIVE_DIR": narrative,
                    }),
                    (render, {
                        "TEMPLATE_DIR": templates,
                        "THEME_PATH": templates / "theme.css",
                        "SUMMARIES_PATH": out / "summaries.json",
                        "DECK_MD_PATH": out / "deck.md",
                        "DECK_PDF_PATH": out / "deck.pdf",
                    }),
                    (deck_provenance, {
                        "COLLECTED_PATH": out / "collected.json",
                        "MANIFEST_PATH": out / "deck-provenance.json",
                    }),
                    (publish, {
                        "ROOT": base,
                        "SUMMARIES_PATH": out / "summaries.json",
                        "DECK_PDF_PATH": out / "deck.pdf",
                    }),
                ):
                    for key, value in attrs.items():
                        stack.enter_context(patch.object(module, key, value))
                stack.enter_context(patch.object(synthesize, "parse_args",
                    return_value=Namespace(commit_state=False, dry_run=False,
                        no_state=False, repo=None, model=None)))
                stack.enter_context(patch.object(synthesize, "OpenAI",
                                                  return_value=object()))
                stack.enter_context(patch.object(render, "parse_args",
                    return_value=Namespace(no_pdf=False)))
                stack.enter_context(patch.object(render, "convert_to_pdf",
                                                  side_effect=convert))
                stack.enter_context(patch.object(publish, "parse_args",
                    return_value=Namespace(target="semanal", remote="gdrive",
                                           dry_run=False)))

                synthesize.main()
                self.assertEqual(state.check_state(), 1)
                self.assertEqual((storage / "last_run.json").read_bytes(),
                                 previous_bytes)
                render.main()
                attestation = json.loads((out / "deck-provenance.json").read_text())
                self.assertEqual(
                    attestation["digests"]["collected"],
                    hashlib.sha256((out / "collected.json").read_bytes()).hexdigest())

                with patch.object(publish, "verified_weekly_release") as remote:
                    publish.main()
                remote.assert_called_once()
                self.assertEqual((storage / "last_run.json").read_bytes(),
                                 previous_bytes)
                self.assertEqual(state.confirm_state(), 1)
                saved = json.loads((storage / "last_run.json").read_text())
                self.assertEqual(saved["example/alpha"]["since"],
                                 "2026-10-29T20:00:00+00:00")
                self.assertIn("Historia previa", previous_md.read_text())


if __name__ == "__main__":
    unittest.main()
