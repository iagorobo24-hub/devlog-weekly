from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest

from src.component_selection import components_from_commits, read_private_mapping, validate_mapping

NOW = datetime(2026, 10, 29, 12, 0, tzinfo=timezone.utc)
OWNER = "iagorobo24-hub"
MAPPING = {"version":1,"monorepos":[{
    "repo": OWNER + "/family-homelab",
    "components": [
        {"id":"duranmusic", "scopes":["duranmusic","duranmusic-unificado"]},
        {"id":"spotube", "scopes":["spotube"]}
    ]}]}


def c(n, scope, kind="feat"):
    return {"sha":f"{n:040x}", "date":(NOW-timedelta(days=2)).isoformat(),
            "message":f"{kind}({scope}): change"}


class ComponentTests(unittest.TestCase):
    def test_attribution_disjoint_and_ambiguous_remains_unassigned(self):
        inventory = [{"name":OWNER+"/family-homelab", "visibility":"private",
                      "archived":False, "commits":[c(1,"spotube"),c(2,"duranmusic"),
                        c(3,"android-auto", "test"), c(4,"spotube","test"), c(5,"psm")]}]
        result=components_from_commits(inventory,MAPPING,owner=OWNER,now=NOW)
        self.assertEqual(len(result),1)
        slots={x["id"]:x["observed"] for x in result[0]["components"]}
        self.assertEqual(slots["spotube"]["code_7d"],1)
        self.assertEqual(slots["spotube"]["test_7d"],1)
        self.assertEqual(slots["duranmusic"]["code_7d"],1)
        self.assertEqual(result[0]["unassigned_substantive_commits"],1)
        self.assertFalse(result[0]["components"][0]["verified_by_file_diff"])

    def test_scopes_cannot_be_overlapping(self):
        mapping={"version":1,"monorepos":[{"repo":OWNER+"/family-homelab",
                "components":[{"id":"duranmusic","scopes":["android"]},
                              {"id":"spotube","scopes":["android"]}]}]}
        with self.assertRaisesRegex(ValueError,"duplicado"):
            validate_mapping(mapping,owner=OWNER)

    def test_no_mapped_private_repo_is_an_error(self):
        with self.assertRaisesRegex(ValueError, "no accesible"):
            components_from_commits([], MAPPING, owner=OWNER, now=NOW)

    def test_permissions_reject_world_readable_mapping(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/"components.yml"
            p.write_text("version: 1\nmonorepos: []\n")
            p.chmod(0o644)
            with self.assertRaisesRegex(ValueError,"permisos"):
                read_private_mapping(p)
            p.chmod(0o600)
            self.assertEqual(read_private_mapping(p)["version"],1)


if __name__ == "__main__":
    unittest.main()
