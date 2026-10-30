"""V4 must not be labelled current when GitHub heads move after curation."""
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

import yaml

from src import editorial_live_freshness as freshness


class EditorialLiveFreshnessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.selection = yaml.safe_load(freshness.SELECTION.read_text())

    def test_all_six_cases_are_unique_public_and_pinned(self):
        result = freshness.selected_revisions(self.selection)
        self.assertEqual(len(result), 6)
        self.assertIn("iagorobo24-hub/GuiaIA", result)
        self.assertTrue(all(len(sha) == 40 for sha in result.values()))

    def _fetch(self, moved=None, unavailable=None):
        moved = moved or {}
        pinned = freshness.selected_revisions(self.selection)
        def fake(endpoint, token):
            repo = endpoint.split("/")[2] + "/" + endpoint.split("/")[3]
            if repo == unavailable:
                raise HTTPError("test", 403, "rate limit", None, None)
            if "/branches/" not in endpoint:
                return {"private": False, "default_branch": "main"}
            return {"commit": {"sha": moved.get(repo, pinned[repo])}}
        return fake

    def test_guiaia_revision_is_consistent_across_public_evidence(self):
        base = freshness.ROOT / 'content/portfolio'
        expected = freshness.selected_revisions(self.selection)['iagorobo24-hub/GuiaIA']
        candidate = yaml.safe_load((base / 'candidates/guiaia.yml').read_text())
        inventory = yaml.safe_load((base / 'evidence-inventory-public.yml').read_text())
        match = [row for row in inventory['projects'] if row['repo'] == 'iagorobo24-hub/GuiaIA']
        self.assertEqual(len(match), 1)
        self.assertEqual(candidate['revision'], expected)
        self.assertEqual(match[0]['revision'], expected)
        self.assertFalse(inventory['allow_publication'])
        self.assertFalse(inventory['owner_image_use_approval'])

    def test_matching_six_pinned_heads_are_only_a_freshness_gate(self):
        report = freshness.inspect(self.selection, self._fetch())
        self.assertTrue(report["revision_gate_pass"])
        self.assertEqual(report["current_count"], 6)
        self.assertFalse(report["automatic_publication"])
        self.assertNotIn("publication_approved", report)

    def test_moved_guiaia_blocks_without_mutating_selection(self):
        initial = json.dumps(self.selection, sort_keys=True)
        report = freshness.inspect(self.selection, self._fetch(
            moved={"iagorobo24-hub/GuiaIA": "a" * 40}))
        self.assertFalse(report["revision_gate_pass"])
        self.assertEqual(report["outdated_count"], 1)
        self.assertEqual(json.dumps(self.selection, sort_keys=True), initial)
        self.assertTrue(any(x["repo"].endswith("/GuiaIA") and x["status"] == "outdated"
                            for x in report["projects"]))

    def test_missing_gitHub_response_fails_closed(self):
        report = freshness.inspect(self.selection, self._fetch(
            unavailable="iagorobo24-hub/T-IA-Portal-RocaRoibas"))
        self.assertFalse(report["revision_gate_pass"])
        self.assertEqual(report["unavailable_count"], 1)
        self.assertEqual(len(report["projects"]), 6)

    def test_private_repository_response_fails_closed(self):
        def private(_endpoint, _token):
            return {"private": True, "default_branch": "main"}
        report = freshness.inspect(self.selection, private)
        self.assertEqual(report["unavailable_count"], 6)
        self.assertFalse(report["revision_gate_pass"])

    def test_rejects_duplicate_malformed_or_auto_published_selection(self):
        from copy import deepcopy
        for field in ("duplicate", "automatic", "private"):
            spec = deepcopy(self.selection)
            if field == "duplicate":
                spec["supporting_cases"][0]["repo"] = spec["main_cases"][0]["repo"]
            elif field == "automatic":
                spec["policy"]["automatic_publication"] = True
            else:
                spec["main_cases"][0]["repo"] = "private/GuiaIA"
            with self.subTest(field=field):
                with self.assertRaises(ValueError):
                    freshness.selected_revisions(spec)

    def test_pdf_preview_workflow_rechecks_heads_before_rendering(self):
        workflow = yaml.safe_load((freshness.ROOT / '.github/workflows/portfolio-editorial-v4-pdf-preview.yml').read_text())
        steps = workflow['jobs']['editorial-pdf']['steps']
        gate = next(i for i, step in enumerate(steps)
                    if 'src.editorial_live_freshness' in step.get('run', ''))
        export = next(i for i, step in enumerate(steps)
                      if 'marp out/portfolio-editorial-closure-v4.md' in step.get('run', ''))
        self.assertLess(gate, export)
        self.assertIn('github.token', steps[gate]['env']['GITHUB_TOKEN'])
        self.assertNotIn('permissions: write', str(workflow))

    def test_cli_reports_drift_and_never_updates_pinned_sha(self):
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / "out" / "fresh.json"
            out.parent.mkdir()
            selection = Path(folder) / "selection.yml"
            selection.write_text(yaml.safe_dump(self.selection))
            report = freshness.inspect(self.selection, self._fetch(
                moved={"iagorobo24-hub/GuiaIA": "a" * 40}))
            with (patch.object(freshness, "ROOT", Path(folder)),
                  patch.object(freshness, "OUT", out),
                  patch.object(freshness, "SELECTION", selection),
                  patch.object(freshness, "inspect", return_value=report),
                  patch("sys.stdout", new_callable=io.StringIO) as printed):
                with self.assertRaises(SystemExit):
                    freshness.main()
            self.assertTrue(out.is_file())
            self.assertFalse(json.loads(out.read_text())["revision_gate_pass"])
            self.assertIn("GuiaIA", printed.getvalue())
            self.assertEqual(yaml.safe_load(selection.read_text()), self.selection)


if __name__ == "__main__":
    unittest.main()
