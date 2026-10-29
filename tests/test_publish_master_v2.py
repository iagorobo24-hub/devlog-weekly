import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src import publish


class MasterReleaseTests(unittest.TestCase):
    def test_three_master_outputs_and_stable_paths(self):
        self.assertEqual(publish.master_subtitle_remote_path("drive"), "drive:Portfolio/master/portfolio.srt")

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
            self.assertEqual(len(published),3)
            self.assertTrue(all("Portfolio/master/portfolio." in k for k in published))

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
