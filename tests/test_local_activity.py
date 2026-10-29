import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from src import local_activity as la


class LocalActivityTests(unittest.TestCase):
    def test_detects_ahead_uncommitted_without_mutating_repo(self):
        with tempfile.TemporaryDirectory() as work:
            root = Path(work)
            origin = root/"origin.git"
            repo = root/"repo"
            def git(*args):
                p = subprocess.run(["git", *map(str, args)], capture_output=True,
                                   text=True, check=True)
                return p.stdout.strip()
            git("init", "--bare", origin)
            git("clone", origin, repo)
            git("-C", repo, "config", "user.name", "Test")
            git("-C", repo, "config", "user.email", "test@example.org")
            (repo/"one.txt").write_text("one")
            git("-C", repo, "add", "one.txt")
            git("-C", repo, "commit", "-m", "feat: first")
            git("-C", repo, "push", "-u", "origin", "HEAD")
            (repo/"one.txt").write_text("two")
            git("-C", repo, "commit", "-am", "feat: next")
            (repo/"one.txt").write_text("three")
            before = git("-C", repo, "rev-parse", "HEAD")
            result = la.audit_one(repo, allowed_root=root)
            after = git("-C", repo, "rev-parse", "HEAD")
            self.assertEqual(before, after)
            self.assertEqual(result["ahead_of_tracking_ref"], 1)
            self.assertEqual(result["tracked_changes"], 1)
            self.assertTrue(result["upstream_tracking_ref_may_be_stale"])
            verified = la.audit_one(repo, allowed_root=root, verify_remote=True)
            self.assertEqual(verified["remote_check"], "tracking_ref_matches_remote")
            self.assertEqual(verified["ahead_of_remote_verified"], 1)
            self.assertFalse(verified["upstream_tracking_ref_may_be_stale"])

    def test_other_root_and_symlinks_blocked(self):
        with tempfile.TemporaryDirectory() as work:
            root = Path(work)
            (root/"allowed").mkdir()
            (root/"other").mkdir()
            with self.assertRaisesRegex(ValueError, "fuera"):
                la.audit_one(root/"other", allowed_root=root/"allowed")
            (root/"link").symlink_to(root/"other")
            self.assertEqual(la.audit_one(root/"link", allowed_root=root)["state"], "unavailable")

    def test_ci_banned(self):
        with patch.dict(os.environ, {"CI": "true"}):
            with self.assertRaisesRegex(RuntimeError, "prohibida"):
                la.audit()

    def test_rejects_world_readable_config(self):
        with tempfile.TemporaryDirectory() as work:
            p = Path(work)/"allowed.yml"
            p.write_text("version: 1\nrepositories: []\n")
            p.chmod(0o644)
            with self.assertRaisesRegex(ValueError, "permisos"):
                la.ensure_private_file(p)


if __name__ == "__main__":
    unittest.main()
