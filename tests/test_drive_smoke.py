"""The manual Drive test is synthetic, isolated and has no state side effects."""
import contextlib
import hashlib
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import yaml
from src import drive_smoke


ROOT = Path(__file__).resolve().parent.parent


class DriveSmokeTests(unittest.TestCase):
    def test_synthetic_pdf_has_consistent_offsets_and_no_personal_content(self):
        pdf = drive_smoke.synthetic_pdf()
        self.assertTrue(pdf.startswith(b"%PDF-1.4"))
        self.assertTrue(pdf.rstrip().endswith(b"%%EOF"))
        self.assertIn(b"Drive smoke test", pdf)
        self.assertNotIn(b"GitHub", pdf)
        xref = pdf.index(b"xref\n0 6\n")
        declared = int(pdf.split(b"startxref\n")[1].split(b"\n")[0])
        self.assertEqual(xref, declared)
        for number in range(1, 6):
            expected = pdf.index(f"{number} 0 obj\n".encode())
            index_line = pdf.split(b"xref\n0 6\n")[1].splitlines()[number]
            self.assertEqual(int(index_line.split()[0]), expected)

    @unittest.skipUnless(shutil.which("rclone"), "real rclone is not installed")
    def test_local_rclone_roundtrip_is_identical_without_touching_state(self):
        with tempfile.TemporaryDirectory(prefix="devlog-drive-test-") as folder:
            original = Path.cwd()
            os.chdir(folder)
            self.addCleanup(os.chdir, original)
            state_path = Path(folder) / "state.json"
            state_path.write_bytes(b"UNCHANGED-STATE")
            with patch.object(drive_smoke, "check_drive_config"):
                result = drive_smoke.run_smoke(
                    config="[testlocal]\ntype = local\n",
                    remote="testlocal", run_id="123456789", attempt="2",
                )
            self.assertEqual(result["result"], "verified")
            self.assertEqual(result["remote_path"],
                             "testlocal:Portfolio/verificaciones/123456789-2/devlog.pdf")
            remote_file = Path(folder) / "Portfolio/verificaciones/123456789-2/devlog.pdf"
            self.assertEqual(remote_file.read_bytes(), drive_smoke.synthetic_pdf())
            self.assertEqual(result["sha256"], hashlib.sha256(remote_file.read_bytes()).hexdigest())
            self.assertEqual(state_path.read_bytes(), b"UNCHANGED-STATE")
            with patch.object(drive_smoke, "check_drive_config"):
                retried = drive_smoke.run_smoke(
                    config="[testlocal]\ntype = local\n",
                    remote="testlocal", run_id="123456789", attempt="2",
                )
            self.assertEqual(retried["sha256"], result["sha256"])

    def test_refuses_missing_or_unsafe_run_identifier_before_remote_write(self):
        with patch.object(drive_smoke, "check_drive_config") as gate, patch.object(
                drive_smoke, "upload") as upload:
            for run_id, attempt in (("", "1"), ("../bad", "1"),
                                    ("123456", "../2"), ("123456", "")):
                with self.subTest(run_id=run_id, attempt=attempt):
                    with self.assertRaises(ValueError):
                        drive_smoke.run_smoke(
                            config="synthetic", remote="testlocal",
                            run_id=run_id, attempt=attempt,
                        )
            upload.assert_not_called()
            self.assertEqual(gate.call_count, 4)

    def test_missing_oauth_fails_without_rclone_attempt(self):
        with patch.object(drive_smoke, "upload") as upload:
            with self.assertRaises(ValueError):
                drive_smoke.run_smoke(config="", remote="gdrive",
                                      run_id="123456", attempt="1")
            upload.assert_not_called()

    def test_checksum_mismatch_is_a_hard_error(self):
        with tempfile.TemporaryDirectory() as folder:
            def corrupting_upload(source, destination, *_args, **_kwargs):
                dest = Path(destination)
                if dest.is_absolute():
                    dest.write_bytes(b"CORRUPTED")
            with patch.object(drive_smoke, "check_drive_config"), patch.object(
                    drive_smoke, "upload", side_effect=corrupting_upload), patch.object(
                    drive_smoke.tempfile, "TemporaryDirectory", return_value=contextlib.nullcontext(folder)):
                with self.assertRaisesRegex(ValueError, "bytes distintos"):
                    drive_smoke.run_smoke(config="mock", remote="gdrive",
                                          run_id="123456789", attempt="1")

    def test_weekly_conditions_separate_test_and_production(self):
        data = yaml.safe_load((ROOT / ".github/workflows/weekly.yml").read_text())
        steps = data["jobs"]["devlog"]["steps"]
        keyed = {s["name"]: s for s in steps if "name" in s}
        self.assertIn("Rechazar modos manuales incompatibles", keyed)
        invalid = keyed["Rechazar modos manuales incompatibles"]["if"]
        self.assertIn("inputs.solo_portfolio == true", invalid)
        self.assertIn("inputs.modo_prueba == true", invalid)
        smoke = keyed["Prueba aislada de Drive con PDF sintético y SHA256"]
        self.assertIn("src.drive_smoke", smoke["run"])
        self.assertIn("inputs.modo_prueba == true", smoke["if"])
        skip_while_smoke = (
            "Recoger", "Sintetizar", "Validar consistencia antes de renderizar o publicar",
            "Renderizar", "Publicar", "Confirmar estado", "Guardar estado",
        )
        for name in skip_while_smoke:
            self.assertIn("inputs.modo_prueba == false", keyed[name]["if"], name)
        for name in ("Instalar Marp CLI desde package-lock.json", "Instalar ffmpeg",
                     "Generar y validar Portfolio Editorial V2 (PDF + vídeo + subtítulos)",
                     "Publicar deck maestro"):
            self.assertIn("inputs.modo_prueba == false", keyed[name]["if"], name)
        self.assertNotIn("src/collect.py", smoke["run"])
        self.assertNotIn("src/render.py", smoke["run"])
        self.assertNotIn("src/synthesize.py", smoke["run"])


if __name__ == "__main__":
    unittest.main()
