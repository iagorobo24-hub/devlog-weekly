"""A single release pointer permits coherent reads across non-atomic aliases."""
import hashlib
import json
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from src import publish

NAMES = publish.MASTER_FILES
NEW = "88888888-1"
OLD = "77777777-1"
CURRENT = "drive:Portfolio/master/current.json"


class MemoryDrive:
    def __init__(self):
        self.objects = {}
        self.calls = []
        self.fail_destination = None
        self.bad_read_source = None

    def upload(self, src, dst, conf, remote, immutable=False):
        source, target = str(src), str(dst)
        self.calls.append((source, target, immutable))
        if target == self.fail_destination:
            raise subprocess.CalledProcessError(23, "test")
        if source.startswith("drive:"):
            if target.startswith("drive:"):
                self.objects[target] = self.objects[source]
            else:
                payload = self.objects[source]
                if source == self.bad_read_source:
                    payload = b"changed"
                Path(target).write_bytes(payload)
        else:
            payload = Path(source).read_bytes()
            if immutable and target in self.objects and self.objects[target] != payload:
                raise subprocess.CalledProcessError(22, "immutable")
            self.objects[target] = payload


class MasterPointerTests(unittest.TestCase):
    def setUp(self):
        self.folder = TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        self.drive = MemoryDrive()
        self.paths = []
        self.new_content = {}
        old_entries = {}
        for name in NAMES:
            new = (name.encode() + b"-new") * 300
            old = (name.encode() + b"-old") * 300
            local = self.root / name
            local.write_bytes(new)
            self.paths.append((local, f"drive:Portfolio/master/{name}"))
            self.new_content[name] = new
            name_path = f"Portfolio/master/versions/{OLD}/{name}"
            old_entries[name] = {"path": name_path,
                                 "sha256": hashlib.sha256(old).hexdigest()}
            self.drive.objects[f"drive:{name_path}"] = old
            self.drive.objects[f"drive:Portfolio/master/{name}"] = old
        self.old_pointer = json.dumps({
            "schema": 1, "run_id": OLD, "files": old_entries}).encode()
        self.drive.objects[CURRENT] = self.old_pointer

    def release(self):
        with patch.object(publish, "upload", side_effect=self.drive.upload):
            publish.verified_master_release(self.paths, "local", "drive", NEW)

    def snapshot(self, directory="snapshot"):
        with patch.object(publish, "upload", side_effect=self.drive.upload):
            return publish.download_verified_master_snapshot(
                "drive", "local", self.root / directory)

    def test_complete_release_has_coherent_pointer_and_retry(self):
        self.release()
        marker = json.loads(self.drive.objects[CURRENT])
        self.assertEqual(marker["run_id"], NEW)
        self.assertEqual(set(marker["files"]), set(NAMES))
        writes = [dest for _, dest, _ in self.drive.calls]
        self.assertGreater(writes.index(CURRENT), max(
            writes.index(f"drive:Portfolio/master/{name}") for name in NAMES))
        self.release()
        self.assertEqual(json.loads(self.drive.objects[CURRENT]), marker)
        self.assertEqual(self.snapshot(), marker)
        for name in NAMES:
            self.assertEqual((self.root / "snapshot" / name).read_bytes(),
                             self.new_content[name])

    def test_mid_alias_failure_keeps_previous_coherent_snapshot(self):
        self.drive.fail_destination = "drive:Portfolio/master/portfolio.mp4"
        with self.assertRaises(subprocess.CalledProcessError):
            self.release()
        self.assertEqual(self.drive.objects[CURRENT], self.old_pointer)
        self.assertEqual(self.drive.objects["drive:Portfolio/master/portfolio.pdf"],
                         self.new_content["portfolio.pdf"])
        old = self.snapshot("old-snapshot")
        self.assertEqual(old["run_id"], OLD)
        for name in NAMES:
            restored = (self.root / "old-snapshot" / name).read_bytes()
            self.assertEqual(hashlib.sha256(restored).hexdigest(),
                             old["files"][name]["sha256"])
        self.drive.fail_destination = None
        self.release()
        self.assertEqual(self.snapshot("recovered")["run_id"], NEW)

    def test_failed_pointer_staging_does_not_advance_current(self):
        self.drive.fail_destination = f"drive:Portfolio/master/versions/{NEW}/release.json"
        with self.assertRaises(subprocess.CalledProcessError):
            self.release()
        self.assertEqual(self.drive.objects[CURRENT], self.old_pointer)

    def test_version_readback_corruption_leaves_aliases_untouched(self):
        self.drive.bad_read_source = f"drive:Portfolio/master/versions/{NEW}/portfolio.mp4"
        with self.assertRaisesRegex(ValueError, "bytes idénticos"):
            self.release()
        self.assertEqual(self.drive.objects[CURRENT], self.old_pointer)
        self.assertNotEqual(self.drive.objects["drive:Portfolio/master/portfolio.pdf"],
                            self.new_content["portfolio.pdf"])

    def test_manifest_stage_corruption_rejects_pointer_update(self):
        self.drive.bad_read_source = f"drive:Portfolio/master/versions/{NEW}/release.json"
        with self.assertRaisesRegex(ValueError, "manifiesto master versionado"):
            self.release()
        self.assertEqual(self.drive.objects[CURRENT], self.old_pointer)

    def test_corrupted_version_prevents_partial_local_snapshot(self):
        self.release()
        self.drive.objects[f"drive:Portfolio/master/versions/{NEW}/portfolio.mp4"] = b"bad"
        with self.assertRaisesRegex(ValueError, "snapshot master corrupto"):
            self.snapshot("failed")
        self.assertFalse((self.root / "failed").exists())

    def test_rejects_invalid_pointer_without_trusting_legacy_aliases(self):
        self.drive.objects[CURRENT] = b'{"schema": 1, "run_id": "bad", "files": {}}'
        with self.assertRaisesRegex(ValueError, "puntero master"):
            self.snapshot("invalid")
        self.assertFalse((self.root / "invalid").exists())
        self.drive.objects.pop(CURRENT)
        with self.assertRaises(KeyError):
            self.snapshot("missing")
        self.assertFalse((self.root / "missing").exists())


if __name__ == "__main__":
    unittest.main()
