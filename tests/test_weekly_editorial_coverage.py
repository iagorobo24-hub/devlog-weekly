"""Guard against silently omitting strategically prominent PUBLIC repositories."""
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import unittest

import yaml

from src import collect
from src import confirm_pipeline_state as state
from src.project_selection_core import configured_projects


ROOT = Path(__file__).resolve().parent.parent


class WeeklyCoverageContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tracked = yaml.safe_load((ROOT / "config/repos.yml").read_text())
        cls.editorial = yaml.safe_load(
            (ROOT / "config/project-selection.yml").read_text())
        cls.names = [item["name"] for item in cls.tracked["repos"]]

    def test_high_priority_public_projects_are_in_weekly_inputs(self):
        curated = configured_projects(self.editorial)
        prominent = {
            repo for item in curated
            if item["priority"] >= 4 and item.get("spotlight", True)
            for repo in item["repos"]
        }
        self.assertTrue(prominent)
        self.assertEqual(prominent,
                         {"iagorobo24-hub/GuiaIA",
                          "iagorobo24-hub/T-IA-Portal-RocaRoibas"})
        self.assertTrue(prominent.issubset(self.names))

    def test_no_duplicates_or_unintended_master_promotion(self):
        self.assertEqual(len(self.names), len(set(self.names)))
        self.assertEqual(len(self.names), 7)
        for item in self.tracked["repos"]:
            self.assertEqual(item["name"].split("/")[0],
                             self.editorial["owner"])
            self.assertIs(type(item.get("showcase")), bool)
        for name in ("iagorobo24-hub/GuiaIA",
                     "iagorobo24-hub/T-IA-Portal-RocaRoibas",
                     "iagorobo24-hub/atm10sky-es-es-localization"):
            candidate = next(x for x in self.tracked["repos"]
                             if x["name"] == name)
            self.assertFalse(candidate["showcase"])

    def test_first_monitoring_window_for_untracked_state_is_bounded(self):
        now = datetime(2026, 10, 30, 3, 30, tzinfo=timezone.utc)
        for name in ("iagorobo24-hub/GuiaIA",
                     "iagorobo24-hub/T-IA-Portal-RocaRoibas",
                     "iagorobo24-hub/atm10sky-es-es-localization"):
            conf = next(x for x in self.tracked["repos"] if x["name"] == name)
            since = collect.resolve_since(
                conf, self.tracked["defaults"], {}, now, None)
            self.assertEqual(since, now - timedelta(days=7))

    def test_state_can_bootstrap_new_repos_without_changing_other_cursors(self):
        now = datetime.now(timezone.utc).replace(microsecond=0)
        initial = now - timedelta(hours=7)
        previous = {
            name: {"since": initial.isoformat(), "tags_seen": []}
            for name in self.names[3:]
        }
        collected = {
            "generated_at": now.isoformat(), "github_run_id": "987654321",
            "repos": [{
                "name": name,
                "since": (initial if name in previous else
                          now - timedelta(days=7)).isoformat(),
                "until": now.isoformat(),
                "tags_all": [], "tags_new": [],
            } for name in self.names],
        }
        collected_raw = json.dumps(collected).encode()
        summaries = {
            "generated_at": now.isoformat(), "github_run_id": "987654321",
            "source_collected_sha256":
                hashlib.sha256(collected_raw).hexdigest(),
            "repos": [{
                "name": item["name"], "since": item["since"],
                "until": item["until"], "narrativa_actualizada":
                    "Solo evidencia sintética de prueba de cobertura.",
            } for item in collected["repos"]],
        }
        updates = state.prepare_state(
            collected, collected_raw, summaries, previous,
            self.names, expected_run_id="987654321")
        self.assertEqual(set(updates["last_run"]), set(self.names))
        self.assertEqual(len(updates["narratives"]), 7)
        for name in previous:
            self.assertEqual(initial.isoformat(), previous[name]["since"])
        without_guiaia = dict(summaries)
        without_guiaia["repos"] = summaries["repos"][1:]
        with self.assertRaisesRegex(ValueError, "no cubren"):
            state.prepare_state(collected, collected_raw, without_guiaia,
                                previous, self.names,
                                expected_run_id="987654321")


if __name__ == "__main__":
    unittest.main()
