import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src import publish


class MasterReleaseTests(unittest.TestCase):
    def test_three_master_outputs_and_stable_paths(self):
        self.assertEqual(publish.master_subtitle_remote_path("drive"), "drive:Portfolio/master/portfolio.srt")

    def test_master_receipt_digest_binds_bytes_before_remote_write(self):
        with tempfile.TemporaryDirectory() as folder:
            local = Path(folder) / "portfolio.pdf"
            local.write_bytes(b"new bytes")
            with patch.object(publish, "upload") as remote:
                with self.assertRaisesRegex(ValueError, "recibo aprobado"):
                    publish.verified_master_release(
                        [(local, "drive:Portfolio/master/portfolio.pdf")],
                        "config", "drive", "40833760474-1",
                        expected_sha256={"pdf": "0" * 64})
            remote.assert_not_called()

    def test_requires_valid_run_id(self):
        with self.assertRaisesRegex(ValueError,"GITHUB_RUN_ID"):
            publish.verified_master_release([], "config", "drive", "../../bad")

    def test_versioned_roundtrip_before_alias_changes(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            files=[root/"portfolio.pdf",root/"portfolio.mp4",root/"portfolio.srt"]
            for n,f in enumerate(files):
                f.write_bytes(bytes([n+1])*100)
            uploaded={}
            published=[]
            def fake_upload(src,dst,conf,remote,immutable=False):
                key=str(src)
                if key.startswith("drive:"):
                    if str(dst).startswith("drive:"):
                        uploaded[dst]=uploaded[key]
                        published.append(dst)
                    else:
                        Path(dst).write_bytes(uploaded[key])
                else:
                    uploaded[dst]=Path(src).read_bytes()
                    if "/versions/" not in dst:
                        published.append(dst)
            paths=[(f,f"drive:Portfolio/master/{f.name}") for f in files]
            with patch.object(publish,"upload",side_effect=fake_upload):
                publish.verified_master_release(paths,"config","drive","40833760474-1")
            self.assertEqual(len(published), 4)
            self.assertTrue(all("Portfolio/master/portfolio." in k for k in published[:3]))
            self.assertEqual(published[-1], publish.master_current_remote_path("drive"))
            self.assertIn("drive:Portfolio/master/versions/40833760474-1/release.json", uploaded)

    def test_alias_readback_mismatch_fails_without_lying_about_success(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            local=root/"portfolio.pdf"
            local.write_bytes(b"correct source")
            alias="drive:Portfolio/master/portfolio.pdf"
            stage="drive:Portfolio/master/versions/40833760474-1/portfolio.pdf"
            objects={}
            writes=[]

            def upload(src, dst, conf, remote, immutable=False):
                a,b=str(src),str(dst)
                if a.startswith("drive:"):
                    if b.startswith("drive:"):
                        objects[b]=objects[a]
                        writes.append(b)
                    else:
                        Path(dst).write_bytes(b"corrupted" if a==alias else objects[a])
                else:
                    objects[b]=Path(src).read_bytes()

            with patch.object(publish,"upload",side_effect=upload):
                with self.assertRaisesRegex(ValueError,"alias master"):
                    publish.verified_master_release(
                        [(local,alias)],"config","drive","40833760474-1")
            self.assertIn(stage, objects)
            self.assertEqual(objects[stage], b"correct source")
            self.assertEqual(writes, [alias])

    def test_corrupted_alias_copy_fails_and_retains_staged_version(self):
        with tempfile.TemporaryDirectory() as folder:
            local=Path(folder)/"portfolio.pdf"
            local.write_bytes(b"expected")
            objects={}
            alias="drive:Portfolio/master/portfolio.pdf"
            stage="drive:Portfolio/master/versions/40833760474-1/portfolio.pdf"
            def upload(src,dst,conf,remote,immutable=False):
                a,b=str(src),str(dst)
                if b==alias:
                    raise __import__("subprocess").CalledProcessError(1,"fake-rclone")
                if a.startswith("drive:"):
                    Path(dst).write_bytes(objects[a])
                else:
                    objects[b]=Path(src).read_bytes()
            with patch.object(publish,"upload",side_effect=upload):
                with self.assertRaises(__import__("subprocess").CalledProcessError):
                    publish.verified_master_release([(local,alias)],"config","drive",
                                                    "40833760474-1")
            self.assertEqual(objects[stage], b"expected")

    def test_modified_master_source_fails_before_alias_changes(self):
        with tempfile.TemporaryDirectory() as folder:
            local=Path(folder)/"portfolio.pdf"
            local.write_bytes(b"initial PDF")
            objects={}
            alias="drive:Portfolio/master/portfolio.pdf"
            writes=[]
            def upload(src,dst,conf,remote,immutable=False):
                a,b=str(src),str(dst)
                if a.startswith("drive:"):
                    if b.startswith("drive:"):
                        writes.append(b)
                    else:
                        Path(dst).write_bytes(objects[a])
                else:
                    objects[b]=Path(src).read_bytes()
                    local.write_bytes(b"changed PDF")
            with patch.object(publish,"upload",side_effect=upload):
                with self.assertRaisesRegex(ValueError,"bytes idénticos"):
                    publish.verified_master_release([(local,alias)],"config","drive",
                                                    "40833760474-1")
            self.assertEqual(writes, [])

    def test_preflight_rejects_missing_output_before_network(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            good=root/"portfolio.pdf"
            good.write_bytes(b"existing PDF")
            missing=root/"portfolio.mp4"
            with patch.object(publish,"upload") as uploader:
                with self.assertRaisesRegex(ValueError,"master inválido"):
                    publish.verified_master_release(
                        [(good,"drive:Portfolio/master/portfolio.pdf"),
                         (missing,"drive:Portfolio/master/portfolio.mp4")],
                        "config","drive","40833760474-1")
            uploader.assert_not_called()

    def test_verification_mismatch_prevents_alias_update(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/"portfolio.pdf"
            p.write_bytes(b"legitimate")
            writes=[]
            def corrupted(src,dst,conf,remote,immutable=False):
                if str(src).startswith("drive:"):
                    Path(dst).write_bytes(b"corrupted")
                else:
                    writes.append(dst)
            with patch.object(publish,"upload",side_effect=corrupted):
                with self.assertRaisesRegex(ValueError,"bytes idénticos"):
                    publish.verified_master_release([(p,"drive:Portfolio/master/portfolio.pdf")],
                                                    "config","drive","40833760474-1")
            self.assertTrue(all("/versions/" in w for w in writes))


if __name__ == "__main__":
    unittest.main()
