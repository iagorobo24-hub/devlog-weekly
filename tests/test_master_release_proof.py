"""Master V2 release is authorized by the exact freshly verified file set."""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

from src import master_release_provenance as proof
from src import run_portfolio_v2 as bridge
from src import publish


class MasterReceiptContracts(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.files = {
            "projects": self.root / "projects.yml",
            "manifest": self.root / "portfolio-v2-manifest.json",
            "markdown": self.root / "portfolio-v2.md",
            "theme": self.root / "portfolio.css",
            "pdf": self.root / "portfolio.pdf",
            "video": self.root / "portfolio.mp4",
            "subtitles": self.root / "portfolio.srt",
        }
        self.receipt = self.root / "proof.json"
        self.files["projects"].write_bytes(b"version: 2\n")
        self.files["manifest"].write_text(json.dumps({
            "schema": 2, "published_to_drive": False,
            "project_revisions": {"example/test": "a" * 40},
            "slides": [{"index": 1, "narration": "Demo"}],
        }))
        self.files["markdown"].write_bytes(b"# portfolio master\n")
        self.files["theme"].write_bytes(b"body { color: black }")
        self.files["pdf"].write_bytes(b"%PDF-1.4\n" + b"dummy" * 400)
        self.files["video"].write_bytes(b"synthetic" * 4000)
        self.files["subtitles"].write_bytes(b"1\n00:00:00,000 --> 00:00:01,000\nDemo")
        self.options = dict(**self.files, run_id="123456789")

    def emit(self):
        return proof.write_receipt(receipt=self.receipt, **self.options)

    def verify(self, run_id="123456789"):
        return proof.verify_receipt(
            receipt=self.receipt, expected_run_id=run_id, **self.files)

    def test_fresh_complete_set_has_single_matching_receipt(self):
        created = self.emit()
        self.assertEqual(created["schema"], 1)
        self.assertEqual(created["github_run_id"], "123456789")
        self.assertEqual(self.verify(), created)
        self.assertEqual(len(created["sha256"]), 7)

    def test_changed_any_output_or_input_blocks_release(self):
        for key in self.files:
            with self.subTest(file=key):
                self.emit()
                original = self.files[key].read_bytes()
                try:
                    self.files[key].write_bytes(original + b" changed")
                    # A broken source manifest may fail at JSON parsing before
                    # the hash comparison: both outcomes must deny release.
                    with self.assertRaises(ValueError):
                        self.verify()
                finally:
                    self.files[key].write_bytes(original)

    def test_missing_or_symlinked_receipt_rejected(self):
        with self.assertRaisesRegex(ValueError, "ausente"):
            self.verify()
        self.receipt.symlink_to(self.files["manifest"])
        with self.assertRaisesRegex(ValueError, "inseguro"):
            self.verify()
        with self.assertRaisesRegex(ValueError, "inseguro"):
            self.emit()

    def test_different_run_never_reuses_past_receipt(self):
        self.emit()
        with self.assertRaisesRegex(ValueError, "sin prueba válida"):
            self.verify(run_id="987654321")

    def test_missing_output_invalid_schema_and_truncated_video(self):
        self.files["subtitles"].unlink()
        with self.assertRaisesRegex(ValueError, "ausente"):
            self.emit()
        self.files["subtitles"].write_text("Subtítulos")
        original = self.files["video"].read_bytes()
        self.files["video"].write_bytes(b"too short")
        with self.assertRaisesRegex(ValueError, "vídeo"):
            self.emit()
        self.files["video"].write_bytes(original)
        self.files["manifest"].write_text(json.dumps({"schema": 2}))
        with self.assertRaisesRegex(ValueError, "manifiesto master"):
            self.emit()

    def _run_release_with_temp_paths(self, build=True, failure=False,
                                     mutate_editorial=False):
        # Validate bridge's real copy/receipt code; expensive renderers mocked.
        with (patch.object(bridge, "ROOT", self.root),
              patch.object(bridge, "PDF_PATH", self.files["pdf"]),
              patch.object(bridge, "MANIFEST_PATH", self.files["manifest"]),
              patch.object(bridge, "MD_PATH", self.files["markdown"]),
              patch.object(bridge, "THEME", self.files["theme"]),
              patch.object(bridge, "VIDEO_PATH", self.files["video"]),
              patch.object(bridge, "SRT_PATH", self.files["subtitles"]),
              patch.object(bridge, "PUBLIC_PDF", self.root / "out" / "portfolio.pdf"),
              patch.object(bridge, "PUBLIC_MP4", self.root / "out" / "portfolio.mp4"),
              patch.object(bridge, "PUBLIC_SRT", self.root / "out" / "portfolio.srt"),
              patch.object(proof, "RECEIPT_PATH", self.receipt),
              patch.object(bridge, "should_build", return_value=build),
              patch.object(bridge, "write_preview") as renderer,
              patch.object(bridge, "check_pdf", side_effect=(
                  RuntimeError("quality gate failed") if failure else
                  lambda *_: {"status": "pass"})),
              patch.object(bridge, "render", return_value={"status": "pass"}),
              patch.dict(os.environ, {"GITHUB_RUN_ID": "123456789"})):
            (self.root / "out").mkdir(exist_ok=True)
            (self.root / "content" / "portfolio").mkdir(parents=True, exist_ok=True)
            editorial = self.root / "content" / "portfolio" / "projects.yml"
            editorial.write_bytes(self.files["projects"].read_bytes())
            if mutate_editorial:
                renderer.side_effect = lambda **_: editorial.write_bytes(
                    editorial.read_bytes() + b"# late change")
            result = bridge.prepare()
            if not build:
                renderer.assert_not_called()
            return result

    def test_skipped_master_build_invalidates_old_receipt(self):
        self.emit()
        self.assertFalse(self._run_release_with_temp_paths(build=False))
        self.assertFalse(self.receipt.exists())

    def test_failed_quality_gate_leaves_no_release_authorization(self):
        self.emit()
        with self.assertRaisesRegex(RuntimeError, "quality gate failed"):
            self._run_release_with_temp_paths(failure=True)
        self.assertFalse(self.receipt.exists())

    def test_editorial_change_during_render_never_mints_receipt(self):
        with self.assertRaisesRegex(RuntimeError, "alterada durante"):
            self._run_release_with_temp_paths(mutate_editorial=True)
        self.assertFalse(self.receipt.exists())

    def test_successful_bridge_creates_verified_receipt(self):
        self.assertTrue(self._run_release_with_temp_paths())
        expected = dict(self.files)
        expected.update({
            "pdf": self.root / "out" / "portfolio.pdf",
            "video": self.root / "out" / "portfolio.mp4",
            "subtitles": self.root / "out" / "portfolio.srt",
        })
        proof.verify_receipt(receipt=self.receipt, expected_run_id="123456789",
                             **expected)

    @unittest.skipUnless(shutil.which("rclone"), "rclone no instalado")
    def test_master_publication_using_real_rclone_local_backend(self):
        # Real rclone protocol and SHA readbacks, never Google or a network.
        root = self.root
        out = root / "out"
        out.mkdir()
        (root / "templates").mkdir()
        (root / "content" / "portfolio").mkdir(parents=True)
        dest = {}
        for key, path in (("pdf", out / "portfolio.pdf"),
                          ("video", out / "portfolio.mp4"),
                          ("subtitles", out / "portfolio.srt")):
            path.write_bytes(self.files[key].read_bytes())
            dest[key] = path
        (out / "portfolio-v2-manifest.json").write_bytes(self.files["manifest"].read_bytes())
        (out / "portfolio-v2.md").write_bytes(self.files["markdown"].read_bytes())
        (root / "templates" / "portfolio.css").write_bytes(self.files["theme"].read_bytes())
        (root / "content" / "portfolio" / "projects.yml").write_bytes(
            self.files["projects"].read_bytes())
        proof.write_receipt(
            receipt=out / "portfolio-master-release-proof.json",
            projects=root / "content" / "portfolio" / "projects.yml",
            manifest=out / "portfolio-v2-manifest.json",
            markdown=out / "portfolio-v2.md",
            theme=root / "templates" / "portfolio.css",
            pdf=dest["pdf"], video=dest["video"], subtitles=dest["subtitles"],
            run_id="123456789")
        args = Mock(target="master", remote="devlogtest", dry_run=False)
        previous = Path.cwd()
        os.chdir(root)
        try:
            with (patch.object(publish, "ROOT", root),
                  patch.object(publish, "PORTFOLIO_PDF_PATH", dest["pdf"]),
                  patch.object(publish, "PORTFOLIO_MP4_PATH", dest["video"]),
                  patch.object(publish, "PORTFOLIO_SRT_PATH", dest["subtitles"]),
                  patch.object(publish, "parse_args", return_value=args),
                  patch.dict(os.environ, {
                      "GITHUB_RUN_ID": "123456789",
                      "GITHUB_RUN_ATTEMPT": "1",
                      "PORTFOLIO_V2_RELEASE": "1",
                      "RCLONE_CONF": "[devlogtest]\ntype = local\n",
                  })):
                with patch.object(publish.log, "warning"):
                    publish.main()
                    publish.main()  # Same immutable version is retryable.
                    marker = publish.download_verified_master_snapshot(
                        "devlogtest", "[devlogtest]\ntype = local\n",
                        root / "verified-snapshot")
                    self.assertEqual(marker["run_id"], "123456789-1")
                    for key, filename in (
                        ("pdf", "portfolio.pdf"), ("video", "portfolio.mp4"),
                        ("subtitles", "portfolio.srt")
                    ):
                        self.assertEqual(
                            (root / "verified-snapshot" / filename).read_bytes(),
                            dest[key].read_bytes())
            for key, suffix in (("pdf", "pdf"), ("video", "mp4"),
                                ("subtitles", "srt")):
                expected = dest[key].read_bytes()
                self.assertEqual(
                    (root / "Portfolio" / "master" /
                     f"portfolio.{suffix}").read_bytes(), expected)
                self.assertEqual(
                    (root / "Portfolio" / "master" / "versions" /
                     "123456789-1" / f"portfolio.{suffix}").read_bytes(),
                    expected)
        finally:
            os.chdir(previous)

    def test_master_publisher_blocks_stale_or_missing_proof_before_rclone(self):
        target = self.root / "out"
        target.mkdir()
        destination = {
            "pdf": target / "portfolio.pdf",
            "video": target / "portfolio.mp4",
            "subtitles": target / "portfolio.srt",
        }
        for key, path in destination.items():
            path.write_bytes(self.files[key].read_bytes())
        (target / "portfolio-v2-manifest.json").write_bytes(
            self.files["manifest"].read_bytes())
        (target / "portfolio-v2.md").write_bytes(
            self.files["markdown"].read_bytes())
        (self.root / "templates").mkdir()
        (self.root / "templates" / "portfolio.css").write_bytes(
            self.files["theme"].read_bytes())
        (self.root / "content" / "portfolio").mkdir(parents=True)
        (self.root / "content" / "portfolio" / "projects.yml").write_bytes(
            self.files["projects"].read_bytes())

        args = Mock(target="master", remote="gdrive", dry_run=False)
        with (patch.object(publish, "ROOT", self.root),
              patch.object(publish, "PORTFOLIO_PDF_PATH", destination["pdf"]),
              patch.object(publish, "PORTFOLIO_MP4_PATH", destination["video"]),
              patch.object(publish, "PORTFOLIO_SRT_PATH", destination["subtitles"]),
              patch.object(publish, "parse_args", return_value=args),
              patch.object(publish, "verified_master_release") as uploader,
              patch.dict(os.environ, {"GITHUB_RUN_ID": "123456789",
                                      "GITHUB_RUN_ATTEMPT": "1",
                                      "PORTFOLIO_V2_RELEASE": "1",
                                      "RCLONE_CONF": "test-not-a-secret"})):
            with self.assertRaisesRegex(ValueError, "ausente"):
                publish.main()
            uploader.assert_not_called()
            proof.write_receipt(
                receipt=target / "portfolio-master-release-proof.json",
                projects=self.root / "content" / "portfolio" / "projects.yml",
                manifest=target / "portfolio-v2-manifest.json",
                markdown=target / "portfolio-v2.md",
                theme=self.root / "templates" / "portfolio.css",
                pdf=destination["pdf"], video=destination["video"],
                subtitles=destination["subtitles"], run_id="123456789")
            publish.main()
            uploader.assert_called_once()
            self.assertEqual(
                uploader.call_args.kwargs["expected_sha256"]["pdf"],
                __import__("hashlib").sha256(destination["pdf"].read_bytes()).hexdigest())
            destination["pdf"].write_bytes(destination["pdf"].read_bytes() + b"changed")
            with self.assertRaisesRegex(ValueError, "sin prueba válida"):
                publish.main()
            uploader.assert_called_once()


if __name__ == "__main__":
    unittest.main()
