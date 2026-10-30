"""CI tool installers must match locally exercised and pinned versions."""
import json
from pathlib import Path
import re
import unittest

import yaml


ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS = ROOT / ".github" / "workflows"


class ToolchainLockContracts(unittest.TestCase):
    def test_marp_exact_version_and_integrity_metadata(self):
        package = json.loads((ROOT / "package.json").read_text())
        lock = json.loads((ROOT / "package-lock.json").read_text())
        self.assertTrue(package["private"])
        self.assertEqual(package["dependencies"]["@marp-team/marp-cli"], "4.5.0")
        self.assertEqual(lock["lockfileVersion"], 3)
        self.assertEqual(lock["packages"]["node_modules/@marp-team/marp-cli"]["version"], "4.5.0")
        self.assertEqual(lock["packages"][""]["dependencies"], package["dependencies"])
        registry = [entry for key, entry in lock["packages"].items()
                    if key.startswith("node_modules/") and entry.get("resolved", "").startswith("https://")]
        self.assertGreater(len(registry), 100)
        self.assertTrue(all(entry.get("integrity", "").startswith("sha512-") for entry in registry))

    def test_every_workflow_uses_locked_python(self):
        for path in WORKFLOWS.glob("*.yml"):
            text = path.read_text()
            yaml.safe_load(text)
            self.assertNotIn("- run: uv sync\n", text, path.name)
            self.assertEqual(text.count("uv sync --locked"),
                             text.count("- run: uv sync --locked"), path.name)

    def test_render_workflows_use_local_locked_marp_and_node22(self):
        expected = {"weekly.yml", "ci.yml", "backfill.yml",
                    "portfolio-v2-preview.yml",
                    "portfolio-editorial-v4-pdf-preview.yml"}
        observed = set()
        for path in WORKFLOWS.glob("*.yml"):
            text = path.read_text()
            if "npm ci --no-audit --no-fund" not in text:
                continue
            observed.add(path.name)
            self.assertIn("actions/setup-node@v7", text)
            self.assertIn("node-version: '22'", text)
            self.assertIn('echo "$GITHUB_WORKSPACE/node_modules/.bin" >> "$GITHUB_PATH"', text)
            self.assertIn("./node_modules/.bin/marp --version", text)
            self.assertNotIn("npm install -g", text)
        self.assertEqual(observed, expected)

    def test_rclone_is_versioned_checksum_verified_and_no_pipe_to_sudo(self):
        installer = ROOT / "scripts" / "install-rclone-pinned.sh"
        self.assertTrue(installer.is_file())
        body = installer.read_text()
        self.assertIn('version="1.75.0"', body)
        self.assertRegex(body, r'sha256="[0-9a-f]{64}"')
        self.assertIn("sha256sum --check --status", body)
        self.assertIn("curl --fail", body)
        self.assertNotIn("sudo", body)
        self.assertIn("GITHUB_PATH", body)
        invocations = 0
        for path in WORKFLOWS.glob("*.yml"):
            text = path.read_text()
            self.assertNotIn("rclone.org/install.sh", text)
            invocations += text.count("run: bash scripts/install-rclone-pinned.sh")
        self.assertEqual(invocations, 2)

    def test_node_modules_is_not_versioned(self):
        self.assertIn("node_modules/", (ROOT / ".gitignore").read_text().splitlines())


if __name__ == "__main__":
    unittest.main()
