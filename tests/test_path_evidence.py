import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from src.path_evidence import verify_paths, valid_prefix
from src import select_projects

NOW = datetime(2026, 10, 29, 13, 0, tzinfo=timezone.utc)
REPO = "iagorobo24-hub/family-homelab"
MAPPING = {
    "version": 1,
    "monorepos": [{"repo": REPO, "components": [
        {"id": "duranmusic", "scopes": ["duranmusic"], "paths": ["apps/spotube/"]},
        {"id": "spotube", "scopes": ["spotube"], "paths": ["apps/spotube/"]},
    ]}]
}


def commit(n, message):
    return {"sha": f"{n:040x}", "message": message,
            "date": NOW.isoformat()}


class FilePathEvidenceTests(unittest.TestCase):
    def test_shared_paths_are_not_falsely_certified(self):
        inventory = [{"name": REPO, "visibility": "private", "archived": False,
                      "commits": [commit(1, "feat(duranmusic): UI"),
                                  commit(2, "fix(spotube): metadata")]}]
        calls = []
        def fetch(repo, sha):
            calls.append((repo, sha))
            return ["apps/spotube/lib/main.dart"]
        report = verify_paths(inventory, MAPPING, owner="iagorobo24-hub",
                              fetch_files=fetch, sample_per_component=3)
        self.assertEqual(len(calls), 2)
        for item in report[0]["components"]:
            self.assertEqual(item["results"]["shared"], 1)
            self.assertEqual(item["results"]["exclusive"], 0)
            self.assertFalse(item["verified_functionality"])
            self.assertEqual(item["scope_path_status"], "shared_paths_not_exclusive")

    def test_exclusive_mixed_unknown_and_fetch_errors(self):
        config = {"version": 1, "monorepos": [{"repo": REPO, "components": [
            {"id": "duranmusic", "scopes": ["duranmusic"], "paths": ["apps/music/"]},
            {"id": "spotube", "scopes": ["spotube"], "paths": ["apps/spotube/"]},
        ]}]}
        inventory = [{"name": REPO, "visibility": "private", "archived": False,
                      "commits": [commit(1, "feat(duranmusic): a"),
                                  commit(2, "fix(duranmusic): b"),
                                  commit(3, "test(duranmusic): c"),
                                  commit(4, "feat(duranmusic): d"),
                                  commit(5, "docs(duranmusic): skip"),
                                  commit(6, "fix(duranmusic): error")]}]
        def fetch(repo, sha):
            if sha == f"{6:040x}":
                raise RuntimeError("Rate limited")
            return {1: ["apps/music/main.dart"],
                    2: ["apps/music/main.dart", "README.md"],
                    3: ["apps/spotube/main.dart"],
                    4: ["apps/music/main.dart", "apps/spotube/main.dart"]}[int(sha, 16)]
        report = verify_paths(inventory, config, owner="iagorobo24-hub",
                              fetch_files=fetch, sample_per_component=6)
        results = report[0]["components"][0]["results"]
        self.assertEqual(results,
                         {"exclusive": 1, "shared": 1, "mixed": 1,
                          "no_path_match": 1, "fetch_error": 1})

    def test_rejects_prefix_traversal_or_insecure_paths(self):
        for value in ("../secret/", "apps/../secret/", "/etc/", "", "apps/*/", "apps\\secret\\"):
            self.assertFalse(valid_prefix(value), value)
        self.assertTrue(valid_prefix("apps/spotube/"))

    def test_public_mode_rejects_diff_verification(self):
        with self.assertRaisesRegex(ValueError, "private-local"):
            select_projects.run(mode="public", inventory=[], verify_file_paths=True)

    def test_bounded_sampling(self):
        inventory = [{"name": REPO, "visibility": "private", "archived": False,
                      "commits": [commit(n, "feat(duranmusic): x") for n in range(1, 30)]}]
        calls = []
        def fetch(repo, sha):
            calls.append(sha)
            return ["apps/spotube/lib/main.dart"]
        result = verify_paths(inventory, MAPPING, owner="iagorobo24-hub",
                              fetch_files=fetch, sample_per_component=4)
        self.assertEqual(len(calls), 4)
        self.assertEqual(result[0]["components"][0]["sampled"], 4)


if __name__ == "__main__":
    unittest.main()
