"""Drive-independent publication contract for immutable weekly PDF releases."""
from __future__ import annotations

import os
import shutil
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch, Mock

from src import publish

RUN = "40964950875-1"
WEEK = "2026-W44"
DEST = f"gdrive:Portfolio/semanal/{WEEK}/devlog.pdf"
VERSION = f"gdrive:Portfolio/semanal/{WEEK}/versions/{RUN}/devlog.pdf"
PDF = b"%PDF-1.4\n" + b"synthetic test payload" * 300 + b"\n%%EOF"


class FakeDrive:
    def __init__(self):
        self.objects: dict[str, bytes] = {}
        self.calls: list[tuple[str, str, bool]] = []
        self.corrupt_stage = False
        self.corrupt_alias = False
        self.fail_at: str | None = None
        self.mutate_local: Path | None = None

    def upload(self, src, dst, config, remote, immutable=False):
        a, b = str(src), str(dst)
        self.calls.append((a, b, immutable))
        if b == self.fail_at:
            raise subprocess.CalledProcessError(1, "fake-rclone")
        if a.startswith("gdrive:"):
            if b.startswith("gdrive:"):
                self.objects[b] = self.objects[a]
            else:
                payload = self.objects[a]
                if a == VERSION and self.corrupt_stage:
                    payload = b"corrupt staged bytes"
                if a == DEST and self.corrupt_alias:
                    payload = b"corrupt published bytes"
                Path(dst).write_bytes(payload)
        else:
            if immutable and b in self.objects and self.objects[b] != Path(a).read_bytes():
                raise subprocess.CalledProcessError(1, "immutable")
            self.objects[b] = Path(a).read_bytes()
            if self.mutate_local:
                self.mutate_local.write_bytes(b"%PDF-1.4\nchanged\n%%EOF")


class WeeklyPublishTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.pdf = self.root / "deck.pdf"
        self.pdf.write_bytes(PDF)
        self.drive = FakeDrive()
        self.drive.objects[DEST] = b"previous-published-week"

    def run_release(self):
        with patch.object(publish, "upload", side_effect=self.drive.upload):
            publish.verified_weekly_release(self.pdf, DEST, "dummy-config", "gdrive", RUN)

    def test_staged_readback_then_alias_readback(self):
        self.run_release()
        self.assertEqual(self.drive.objects[VERSION], PDF)
        self.assertEqual(self.drive.objects[DEST], PDF)
        self.assertEqual(len(self.drive.calls), 4)
        self.assertEqual(self.drive.calls[0][1], VERSION)
        self.assertTrue(self.drive.calls[0][2])
        self.assertEqual(self.drive.calls[1][0], VERSION)
        self.assertEqual(self.drive.calls[2][1], DEST)
        self.assertEqual(self.drive.calls[3][0], DEST)

    def test_staged_corruption_never_updates_visible_week(self):
        self.drive.corrupt_stage = True
        with self.assertRaisesRegex(ValueError, "versionado"):
            self.run_release()
        self.assertEqual(self.drive.objects[DEST], b"previous-published-week")
        self.assertEqual(len(self.drive.calls), 2)

    def test_staged_upload_failure_keeps_alias_intact(self):
        self.drive.fail_at = VERSION
        with self.assertRaises(subprocess.CalledProcessError):
            self.run_release()
        self.assertEqual(self.drive.objects[DEST], b"previous-published-week")

    def test_replacing_alias_fails_but_version_is_recoverable(self):
        self.drive.fail_at = DEST
        with self.assertRaises(subprocess.CalledProcessError):
            self.run_release()
        self.assertEqual(self.drive.objects[DEST], b"previous-published-week")
        self.assertEqual(self.drive.objects[VERSION], PDF)

    def test_post_publication_corruption_detected(self):
        self.drive.corrupt_alias = True
        with self.assertRaisesRegex(ValueError, "publicado"):
            self.run_release()
        self.assertEqual(self.drive.objects[VERSION], PDF)

    def test_mutated_source_never_updates_alias(self):
        self.drive.mutate_local = self.pdf
        with self.assertRaisesRegex(ValueError, "versionado"):
            self.run_release()
        self.assertEqual(self.drive.objects[DEST], b"previous-published-week")

    def test_repeated_same_version_is_idempotent(self):
        self.run_release()
        self.run_release()
        self.assertEqual(self.drive.objects[DEST], PDF)
        self.assertEqual(self.drive.objects[VERSION], PDF)

    def test_rejects_unsafe_identifiers_paths_and_invalid_pdf(self):
        for run in ("../bad", "x", "1-1", "11111-foo", "11111-1/../../"):
            with self.subTest(run=run), self.assertRaisesRegex(ValueError, "GITHUB_RUN_ID"):
                publish.verified_weekly_release(self.pdf, DEST, "dummy", "gdrive", run)
        for dest in ("gdrive:Portfolio/master/devlog.pdf",
                     "gdrive:Portfolio/semanal/2026-W99/devlog.pdf",
                     "gdrive:Portfolio/semanal/2026-W44/../devlog.pdf"):
            with self.subTest(dest=dest), self.assertRaisesRegex(ValueError, "canónica"):
                publish.verified_weekly_release(self.pdf, dest, "dummy", "gdrive", RUN)
        self.pdf.write_bytes(b"not a PDF")
        with self.assertRaisesRegex(ValueError, "cabecera PDF"):
            self.run_release()
        self.assertEqual(self.drive.objects[DEST], b"previous-published-week")

    def test_main_production_weekly_uses_verified_release(self):
        args = Mock(target="semanal", remote="gdrive", dry_run=False)
        with (patch.object(publish, "parse_args", return_value=args),
              patch.object(publish, "DECK_PDF_PATH", self.pdf),
              patch.object(publish, "load_generated_at",
                           return_value=__import__("datetime").datetime(2026, 10, 29)),
              patch.object(publish, "verified_weekly_release") as verified,
              patch("src.deck_provenance.verify_manifest") as provenance_check,
              patch.dict(os.environ, {"RCLONE_CONF": "only-test",
                                      "GITHUB_RUN_ID": "40964950875",
                                      "GITHUB_RUN_ATTEMPT": "2"})):
            publish.main()
        verified.assert_called_once_with(self.pdf, DEST, "only-test",
                                         "gdrive", "40964950875-2")

    @unittest.skipUnless(shutil.which("rclone"), "rclone no instalado")
    def test_real_rclone_local_backend_roundtrip_offline(self):
        # Uses actual rclone copyto/--immutable, no Google account or network.
        with tempfile.TemporaryDirectory(prefix="devlog-rclone-qa-") as path:
            previous = Path.cwd()
            os.chdir(path)
            try:
                source = Path(path) / "deck.pdf"
                source.write_bytes(PDF)
                config = "[devlogtest]\ntype = local\n"
                alias = "devlogtest:Portfolio/semanal/2026-W44/devlog.pdf"
                with patch.object(publish.log, "warning"):
                    publish.verified_weekly_release(source, alias, config,
                                                    "devlogtest", RUN)
                    # Exact same immutable version must be safely reusable.
                    publish.verified_weekly_release(source, alias, config,
                                                    "devlogtest", RUN)
                self.assertEqual(
                    (Path(path) / "Portfolio/semanal/2026-W44/devlog.pdf").read_bytes(),
                    PDF)
                self.assertEqual(
                    (Path(path) / "Portfolio/semanal/2026-W44/versions" /
                     RUN / "devlog.pdf").read_bytes(), PDF)
            finally:
                os.chdir(previous)

    def test_main_mismatch_exits_nonzero_without_fallback_alias(self):
        args = Mock(target="semanal", remote="gdrive", dry_run=False)
        with (patch.object(publish, "parse_args", return_value=args),
              patch.object(publish, "DECK_PDF_PATH", self.pdf),
              patch.object(publish, "load_generated_at",
                           return_value=__import__("datetime").datetime(2026, 10, 29)),
              patch.object(publish, "verified_weekly_release",
                           side_effect=ValueError("corrupt staged PDF")),
              patch("src.deck_provenance.verify_manifest"),
              patch.object(publish, "upload") as uploader,
              patch.dict(os.environ, {"RCLONE_CONF": "only-test",
                                      "GITHUB_RUN_ID": "40964950875",
                                      "GITHUB_RUN_ATTEMPT": "1"})):
            with self.assertRaises(SystemExit) as error:
                publish.main()
        self.assertEqual(error.exception.code, 1)
        uploader.assert_not_called()


if __name__ == "__main__":
    unittest.main()
