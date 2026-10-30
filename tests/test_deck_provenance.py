"""Pre-Drive release gate: a PDF must be from this run's exact content."""
from __future__ import annotations

from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch, Mock

from src import deck_provenance as provenance


class ManifestTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.collected = self.root / "collected.json"
        self.summary = self.root / "summaries.json"
        self.md = self.root / "deck.md"
        self.pdf = self.root / "deck.pdf"
        self.template = self.root / "deck.md.j2"
        self.theme = self.root / "theme.css"
        self.manifest = self.root / "deck-provenance.json"
        self.collected.write_text(json.dumps({"generated_at": "2026-10-30T00:00:00+00:00", "github_run_id": "123456", "repos": [{"name":"example/repo", "since":"2026-10-23T00:00:00+00:00", "until":"2026-10-30T00:00:00+00:00"}]}))
        self.summary.write_text(json.dumps({
            "generated_at": "2026-10-30T00:00:00+00:00",
            "github_run_id": "123456",
            "source_collected_sha256": hashlib.sha256(self.collected.read_bytes()).hexdigest(),
            "repos": [{"name": "example/repo", "since":"2026-10-23T00:00:00+00:00", "until":"2026-10-30T00:00:00+00:00"}]}))
        self.md.write_text("# weekly report")
        self.pdf.write_bytes(b"%PDF-1.4\n" + b"test synthetic pdf" * 100 + b"%%EOF")
        self.template.write_text("{{ sections }}")
        self.theme.write_text("body { background: white }")
        self.args = dict(summary=self.summary, collected=self.collected, markdown=self.md, pdf=self.pdf,
                         template=self.template, theme=self.theme, manifest=self.manifest)

    def emit(self):
        return provenance.write_manifest(**self.args)

    def verify(self, expected="123456"):
        return provenance.verify_manifest(**self.args, expected_run_id=expected)

    def test_matching_pdf_summary_and_template_accepted(self):
        initial = self.emit()
        self.assertEqual(initial["schema"], 1)
        self.assertEqual(initial["digests"]["pdf"], hashlib.sha256(self.pdf.read_bytes()).hexdigest())
        self.assertEqual(self.verify(), initial)

    def test_manifest_attests_exact_collected_bytes(self):
        doc = self.emit()
        digest = hashlib.sha256(self.collected.read_bytes()).hexdigest()
        self.assertEqual(doc["source_collected_sha256"], digest)
        self.assertEqual(doc["digests"]["collected"], digest)
        self.assertEqual(self.verify(), doc)

    def test_changed_collection_blocks_release(self):
        self.emit()
        self.collected.write_bytes(self.collected.read_bytes() + b" ")
        with self.assertRaisesRegex(ValueError, "desacoplada"):
            self.verify()

    def test_missing_or_forged_collected_digest_blocks_render(self):
        baseline = self.summary.read_bytes()
        for changed_digest in (None, "0" * 64, "invalid"):
            with self.subTest(digest=changed_digest):
                report = json.loads(baseline)
                if changed_digest is None:
                    report.pop("source_collected_sha256")
                else:
                    report["source_collected_sha256"] = changed_digest
                self.summary.write_text(json.dumps(report))
                with self.assertRaisesRegex(ValueError, "desacoplada"):
                    self.emit()
        self.summary.write_bytes(baseline)

    def test_sha_correct_but_run_mismatch_blocks_render(self):
        self.emit()
        report = json.loads(self.summary.read_text())
        report["github_run_id"] = "777777"
        self.summary.write_text(json.dumps(report))
        with self.assertRaisesRegex(ValueError, "GITHUB_RUN_ID"):
            self.emit()

    def test_sha_correct_but_interval_mismatch_blocks_render(self):
        collected = json.loads(self.collected.read_text())
        collected["repos"][0]["since"] = "2026-10-24T00:00:00+00:00"
        self.collected.write_text(json.dumps(collected))
        summary = json.loads(self.summary.read_text())
        summary["source_collected_sha256"] = hashlib.sha256(self.collected.read_bytes()).hexdigest()
        self.summary.write_text(json.dumps(summary))
        with self.assertRaisesRegex(ValueError, "intervalos"):
            self.emit()

    def test_duplicate_repo_in_collection_blocks_render(self):
        collected = json.loads(self.collected.read_text())
        collected["repos"].append(dict(collected["repos"][0]))
        self.collected.write_text(json.dumps(collected))
        summary = json.loads(self.summary.read_text())
        summary["source_collected_sha256"] = hashlib.sha256(self.collected.read_bytes()).hexdigest()
        self.summary.write_text(json.dumps(summary))
        with self.assertRaisesRegex(ValueError, "duplicada"):
            self.emit()

    def test_rejects_stale_pdf_even_with_valid_header(self):
        self.emit()
        self.pdf.write_bytes(b"%PDF-1.4\nnew replacement valid PDF\n%%EOF")
        with self.assertRaisesRegex(ValueError, "no corresponde"):
            self.verify()

    def test_rejects_changed_summary_or_markdown(self):
        for path in (self.summary, self.md):
            with self.subTest(path=path.name):
                self.emit()
                path.write_bytes(path.read_bytes() + b" ")
                with self.assertRaisesRegex(ValueError, "no corresponde"):
                    self.verify()

    def test_rejects_changed_theme_or_jinja(self):
        for path in (self.theme, self.template):
            with self.subTest(path=path.name):
                self.emit()
                path.write_bytes(path.read_bytes() + b"\nchange")
                with self.assertRaisesRegex(ValueError, "no corresponde"):
                    self.verify()

    def test_rejects_other_run_and_missing_manifest(self):
        self.emit()
        with self.assertRaisesRegex(ValueError, "otro GITHUB_RUN_ID"):
            self.verify(expected="654321")
        self.manifest.unlink()
        with self.assertRaisesRegex(ValueError, "ausente"):
            self.verify()

    def test_rejects_tampered_manifest_and_symlinks(self):
        self.emit()
        doc = json.loads(self.manifest.read_text())
        doc["digests"]["pdf"] = "0" * 64
        self.manifest.write_text(json.dumps(doc))
        with self.assertRaisesRegex(ValueError, "no corresponde"):
            self.verify()
        self.manifest.unlink()
        self.manifest.symlink_to(self.summary)
        with self.assertRaisesRegex(ValueError, "enlace simbólico"):
            self.emit()
        with self.assertRaisesRegex(ValueError, "inseguro"):
            self.verify()

    def test_does_not_generate_manifest_for_invalid_pdf_or_empty_repos(self):
        self.pdf.write_bytes(b"bad")
        with self.assertRaisesRegex(ValueError, "PDF"):
            self.emit()
        self.assertFalse(self.manifest.exists())
        self.pdf.write_bytes(b"%PDF-1.4\n" + b"synthetic" * 20)
        doc = json.loads(self.summary.read_text())
        doc["repos"] = []
        self.summary.write_text(json.dumps(doc))
        with self.assertRaisesRegex(ValueError, "sin repositorios"):
            self.emit()

    def test_renderer_records_provenance_only_after_pdf_success(self):
        from src import render
        with (patch.object(render, "DECK_MD_PATH", self.md),
              patch.object(render, "DECK_PDF_PATH", self.pdf),
              patch.object(render, "SUMMARIES_PATH", self.summary),
              patch.object(render, "TEMPLATE_DIR", self.root),
              patch.object(render, "TEMPLATE_NAME", self.template.name),
              patch.object(render, "THEME_PATH", self.theme),
              patch.object(provenance, "MANIFEST_PATH", self.manifest),
              patch.object(provenance, "COLLECTED_PATH", self.collected),
              patch.object(render, "parse_args", return_value=SimpleNamespace(no_pdf=False)),
              patch.object(render, "load_summaries", return_value=json.loads(self.summary.read_text())),
              patch.object(render, "render_markdown", return_value="# regenerated"),
              patch.object(render, "convert_to_pdf",
                           side_effect=lambda md, pdf: pdf.write_bytes(b"%PDF-1.4\n" + b"content" * 15))):
            render.main()
        self.assertEqual(self.verify()["digests"]["markdown"],
                         hashlib.sha256(self.md.read_bytes()).hexdigest())

    def test_failed_render_revokes_previous_manifest(self):
        from src import render
        self.emit()
        with (patch.object(render, "DECK_MD_PATH", self.md),
              patch.object(render, "DECK_PDF_PATH", self.pdf),
              patch.object(render, "SUMMARIES_PATH", self.summary),
              patch.object(render, "TEMPLATE_DIR", self.root),
              patch.object(render, "TEMPLATE_NAME", self.template.name),
              patch.object(render, "THEME_PATH", self.theme),
              patch.object(provenance, "MANIFEST_PATH", self.manifest),
              patch.object(provenance, "COLLECTED_PATH", self.collected),
              patch.object(render, "parse_args", return_value=SimpleNamespace(no_pdf=False)),
              patch.object(render, "load_summaries", return_value=json.loads(self.summary.read_text())),
              patch.object(render, "render_markdown", return_value="# updated"),
              patch.object(render, "convert_to_pdf", side_effect=RuntimeError("failed PDF"))):
            with self.assertRaisesRegex(RuntimeError, "failed PDF"):
                render.main()
        self.assertFalse(self.manifest.exists())

    def test_successful_converter_without_new_pdf_cannot_attest_old_file(self):
        from src import render
        self.emit()
        with (patch.object(render, "DECK_MD_PATH", self.md),
              patch.object(render, "DECK_PDF_PATH", self.pdf),
              patch.object(render, "SUMMARIES_PATH", self.summary),
              patch.object(render, "TEMPLATE_DIR", self.root),
              patch.object(render, "TEMPLATE_NAME", self.template.name),
              patch.object(render, "THEME_PATH", self.theme),
              patch.object(provenance, "MANIFEST_PATH", self.manifest),
              patch.object(provenance, "COLLECTED_PATH", self.collected),
              patch.object(render, "parse_args", return_value=SimpleNamespace(no_pdf=False)),
              patch.object(render, "load_summaries", return_value=json.loads(self.summary.read_text())),
              patch.object(render, "render_markdown", return_value="# fresh markdown"),
              patch.object(render, "convert_to_pdf", return_value=None)):
            with self.assertRaisesRegex(ValueError, "ausente"):
                render.main()
        self.assertFalse(self.manifest.exists())
        self.assertFalse(self.pdf.exists())

    def test_concurrent_summary_change_during_render_is_rejected(self):
        from src import render
        self.emit()
        def convert(md, pdf):
            pdf.write_bytes(b"%PDF-1.4\n" + b"new bytes" * 50)
            self.summary.write_bytes(self.summary.read_bytes() + b" ")
        with (patch.object(render, "DECK_MD_PATH", self.md),
              patch.object(render, "DECK_PDF_PATH", self.pdf),
              patch.object(render, "SUMMARIES_PATH", self.summary),
              patch.object(render, "TEMPLATE_DIR", self.root),
              patch.object(render, "TEMPLATE_NAME", self.template.name),
              patch.object(render, "THEME_PATH", self.theme),
              patch.object(provenance, "MANIFEST_PATH", self.manifest),
              patch.object(provenance, "COLLECTED_PATH", self.collected),
              patch.object(render, "parse_args", return_value=SimpleNamespace(no_pdf=False)),
              patch.object(render, "load_summaries", return_value=json.loads(self.summary.read_text())),
              patch.object(render, "render_markdown", return_value="# fresh markdown"),
              patch.object(render, "convert_to_pdf", side_effect=convert)):
            with self.assertRaisesRegex(RuntimeError, "cambiaron durante"):
                render.main()
        self.assertFalse(self.manifest.exists())

    def test_publish_main_accepts_matching_attestation(self):
        from src import publish
        out = self.root / "out"
        templates = self.root / "templates"
        out.mkdir()
        templates.mkdir()
        for source, dest in (
                (self.collected, out / "collected.json"),
                (self.summary, out / "summaries.json"),
                (self.md, out / "deck.md"),
                (self.template, templates / "deck.md.j2"),
                (self.theme, templates / "theme.css")):
            dest.write_bytes(source.read_bytes())
        provenance.write_manifest(
            summary=out / "summaries.json", collected=out / "collected.json", markdown=out / "deck.md",
            pdf=self.pdf, template=templates / "deck.md.j2",
            theme=templates / "theme.css",
            manifest=out / "deck-provenance.json")
        args = Mock(target="semanal", remote="gdrive", dry_run=False)
        with (patch.object(publish, "parse_args", return_value=args),
              patch.object(publish, "DECK_PDF_PATH", self.pdf),
              patch.object(publish, "SUMMARIES_PATH", out / "summaries.json"),
              patch.object(publish, "load_generated_at",
                           return_value=datetime(2026, 10, 30)),
              patch.object(publish, "ROOT", self.root),
              patch.object(publish, "verified_weekly_release") as uploader,
              patch.dict(os.environ, {"RCLONE_CONF": "synthetic",
                                      "GITHUB_RUN_ID": "123456",
                                      "GITHUB_RUN_ATTEMPT": "3"})):
            publish.main()
        uploader.assert_called_once_with(
            self.pdf, "gdrive:Portfolio/semanal/2026-W44/devlog.pdf",
            "synthetic", "gdrive", "123456-3")

    def test_publish_blocks_changed_raw_collection_before_drive(self):
        from src import publish
        out = self.root / "out"
        templates = self.root / "templates"
        out.mkdir()
        templates.mkdir()
        for source, target in (
            (self.collected, out / "collected.json"),
            (self.summary, out / "summaries.json"),
            (self.md, out / "deck.md"),
            (self.template, templates / "deck.md.j2"),
            (self.theme, templates / "theme.css"),
        ):
            target.write_bytes(source.read_bytes())
        provenance.write_manifest(
            collected=out / "collected.json", summary=out / "summaries.json",
            markdown=out / "deck.md", pdf=self.pdf,
            template=templates / "deck.md.j2", theme=templates / "theme.css",
            manifest=out / "deck-provenance.json")
        (out / "collected.json").write_bytes(
            (out / "collected.json").read_bytes() + b" ")
        args = Mock(target="semanal", remote="gdrive", dry_run=False)
        with (patch.object(publish, "parse_args", return_value=args),
              patch.object(publish, "DECK_PDF_PATH", self.pdf),
              patch.object(publish, "SUMMARIES_PATH", out / "summaries.json"),
              patch.object(publish, "load_generated_at",
                           return_value=datetime(2026, 10, 30)),
              patch.object(publish, "ROOT", self.root),
              patch.object(publish, "upload") as uploader,
              patch.object(publish, "verified_weekly_release") as release,
              patch.dict(os.environ, {"RCLONE_CONF": "synthetic",
                                      "GITHUB_RUN_ID": "123456"})):
            with self.assertRaisesRegex(ValueError, "desacoplada"):
                publish.main()
        uploader.assert_not_called()
        release.assert_not_called()

    def test_publish_main_denies_stale_pdf_before_remote_io(self):
        from src import publish
        self.emit()
        self.pdf.write_bytes(self.pdf.read_bytes() + b"tampered")
        args = Mock(target="semanal", remote="gdrive", dry_run=False)
        # Keep publication's canonical layout redirected to the synthetic files.
        with (patch.object(publish, "parse_args", return_value=args),
              patch.object(publish, "DECK_PDF_PATH", self.pdf),
              patch.object(publish, "SUMMARIES_PATH", self.summary),
              patch.object(publish, "load_generated_at", return_value=datetime(2026, 10, 30)),
              patch.object(publish, "ROOT", self.root),
              patch.object(publish, "verified_weekly_release") as uploader,
              patch.dict(os.environ, {"RCLONE_CONF": "synthetic",
                                      "GITHUB_RUN_ID": "123456"})):
            # Publisher uses ROOT / out/... and ROOT / templates/...; map
            # them into this fixture via a dedicated temporary layout.
            (self.root / "out").mkdir()
            (self.root / "templates").mkdir()
            for source, dest in ((self.collected, self.root/"out"/"collected.json"),
                                 (self.md, self.root/"out"/"deck.md"),
                                 (self.template, self.root/"templates"/"deck.md.j2"),
                                 (self.theme, self.root/"templates"/"theme.css"),
                                 (self.manifest, self.root/"out"/"deck-provenance.json")):
                dest.write_bytes(source.read_bytes())
            with self.assertRaisesRegex(ValueError, "no corresponde"):
                publish.main()
        uploader.assert_not_called()


if __name__ == "__main__":
    unittest.main()
