"""Selector contracts: candidate relevance and fail-closed privacy."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch, Mock

from src import project_selection_core as core
from src import select_projects as cli

NOW = datetime(2026, 10, 29, 12, 0, tzinfo=timezone.utc)


def config():
    return {
        "version": 1, "owner": "iagorobo24-hub", "lookback_days": 30,
        "recent_days": 7, "max_commits_per_repo": 200,
        "max_repositories": 100, "top_n": 8,
        "projects": [
            {"id": "guiaia", "title": "GuiaIA", "priority": 5,
             "repos": ["iagorobo24-hub/GuiaIA"]},
            {"id": "legacy", "title": "Historic", "priority": 4,
             "repos": ["iagorobo24-hub/old"]},
        ],
    }


def commit(n, days, kind):
    return {"sha": f"{n:040x}", "date": (NOW - timedelta(days=days)).isoformat(),
            "message": kind}


def repo(name, commits, visibility="public", archived=False):
    return {"name": "iagorobo24-hub/" + name, "visibility": visibility,
            "archived": archived, "commits": commits}


class ProjectSelectionTests(unittest.TestCase):
    def test_psm_updates_are_not_product_development(self):
        psm = [
            "docs(psm): refresh manifest audit hash",
            "fix(psm): incluir fecha de comprobacion documental",
            "docs: project-system-map baseline refresh",
            "docs(psm): crear discovery remoto",
        ]
        self.assertTrue(all(core.categorize(x) == "psm_noise" for x in psm))
        self.assertEqual(core.categorize("feat(web): add login"), "code")
        self.assertEqual(core.categorize("test(core): verify token"), "test")
        self.assertEqual(core.categorize("docs: update guide"), "maintenance")

    def test_top_recent_active_beats_psm_only_even_with_priority(self):
        entries = [
            repo("GuiaIA", [commit(1, 1, "feat: gateway"), commit(2, 2, "test: queries")]),
            repo("old", [commit(i, 1, "fix(psm): update") for i in range(30, 120)]),
            repo("AutoCAD-Agentico", [commit(i, 1, "feat(cad): implement")
                                     for i in range(120, 135)]),
        ]
        answer = core.build_selection(entries, config(), now=NOW)
        self.assertEqual(answer["ranked"][0]["id"], "AutoCAD-Agentico")
        self.assertEqual(answer["ranked"][1]["id"], "guiaia")
        self.assertNotIn("legacy", [x["id"] for x in answer["ranked"]])
        legacy = next(x for x in answer["watchlist"] if x["id"] == "legacy")
        self.assertEqual(legacy["counts"]["psm_30d"], 90)
        self.assertEqual(legacy["watch_reason"], "no_substantive_activity_30d")

    def test_larger_substantive_workload_does_not_flatline_at_same_score(self):
        many = core.evaluate_repo(repo("many", [commit(i, 1, "feat: x") for i in range(1, 45)]), now=NOW)
        fewer = core.evaluate_repo(repo("fewer", [commit(i, 1, "feat: x") for i in range(45, 57)]), now=NOW)
        self.assertGreater(many["activity_score"], fewer["activity_score"])

    def test_recency_is_bounded_and_old_commits_ignored(self):
        s = core.evaluate_repo(repo("GuiaIA", [
            commit(1, 1, "feat: today"),
            commit(2, 20, "feat: older"),
            commit(3, 50, "feat: out of range"),
        ]), now=NOW)
        self.assertEqual(s["counts"]["code_7d"], 1)
        self.assertEqual(s["counts"]["code_30d"], 2)

    def test_no_duplicate_shas_and_bad_times(self):
        source = [commit(1, 0, "feat: x"), commit(1, 0, "feat: x"),
                  {"sha": "not a sha", "date": NOW.isoformat(), "message": "feat: y"},
                  {"sha": f"{3:040x}", "date": "2026-10-29", "message": "feat: z"}]
        s = core.evaluate_repo(repo("GuiaIA", source), now=NOW)
        self.assertEqual(s["counts"]["code_7d"], 1)

    def test_private_never_enters_public_results(self):
        data = [
            repo("GuiaIA", [commit(1, 1, "feat: public")]),
            repo("secret-industrial", [commit(2, 1, "feat: private")], "private"),
        ]
        p = core.build_selection(data, config(), now=NOW, visibility="public")
        as_text = json.dumps(p)
        self.assertNotIn("secret-industrial", as_text)
        self.assertEqual(p["coverage"]["exclusions"]["other_visibility"], 1)
        self.assertTrue(all(x["visibility"] == "public" for x in p["ranked"]))
        q = core.build_selection(data, config(), now=NOW, visibility="private-local")
        self.assertNotIn("GuiaIA", json.dumps(q))
        self.assertEqual(q["ranked"][0]["id"], "secret-industrial")

    def test_groups_sum_relevant_counts_not_commit_noise(self):
        cfg = config()
        cfg["projects"].append({
            "id": "suite", "title": "One suite", "priority": 1,
            "repos": ["iagorobo24-hub/a", "iagorobo24-hub/b"]
        })
        data = [repo("a", [commit(1, 1, "feat: x")]),
                repo("b", [commit(2, 1, "test: y")])]
        result = core.build_selection(data, cfg, now=NOW)
        merged = next(x for x in result["ranked"] if x["id"] == "suite")
        self.assertEqual(merged["counts"]["code_7d"], 1)
        self.assertEqual(merged["counts"]["tests_7d"], 1)
        self.assertEqual(len(merged["repos"]), 2)

    def test_bad_duplicate_and_foreign_config_rejected(self):
        cfg = config()
        cfg["projects"][1]["repos"] = ["iagorobo24-hub/GuiaIA"]
        with self.assertRaisesRegex(ValueError, "duplicados"):
            core.configured_projects(cfg)
        cfg["projects"][1]["repos"] = ["another-owner/private"]
        with self.assertRaisesRegex(ValueError, "externos"):
            core.configured_projects(cfg)

    def test_never_claim_verified_functionality(self):
        output = core.build_selection([repo("GuiaIA", [commit(1, 1, "feat: mock")])],
                                      config(), now=NOW)
        self.assertEqual(output["ranked"][0]["editorial_status"], "candidate_needs_review")
        self.assertTrue(output["limits"]["ranking_is_not_proof_of_functionality"])

    def test_public_path_confined_and_write_rejects_private_payload(self):
        with tempfile.TemporaryDirectory() as directory:
            public = Path(directory) / "out" / "selection.json"
            with patch.object(cli, "ROOT", Path(directory)), patch.object(cli, "PUBLIC_OUT", public):
                report = core.build_selection([repo("GuiaIA", [commit(1, 1, "feat: public")])],
                                              config(), now=NOW)
                cli.write_report(report, public, "public")
                self.assertEqual(json.loads(public.read_text())["visibility"], "public")
                report["ranked"][0]["visibility"] = "private"
                with self.assertRaisesRegex(ValueError, "privados bloqueados"):
                    cli.write_report(report, public, "public")
                report["ranked"][0]["visibility"] = "public"
                report["component_hints"] = [{"visibility": "private", "repo": "secret"}]
                with self.assertRaisesRegex(ValueError, "privados bloqueados"):
                    cli.write_report(report, public, "public")
                report.pop("component_hints")
                report["path_evidence"] = [{"visibility": "private", "repo": "secret"}]
                with self.assertRaisesRegex(ValueError, "privados bloqueados"):
                    cli.write_report(report, public, "public")
                report.pop("path_evidence")
                report["watchlist"] = [{"visibility": "private", "id": "secret"}]
                with self.assertRaisesRegex(ValueError, "privados bloqueados"):
                    cli.write_report(report, public, "public")
                with self.assertRaises(ValueError):
                    cli.ensure_safe_output(Path(directory).parent / "outside.json", "public")

    def test_private_output_confined_and_locked_down(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "restricted"
            dest = root / "project-selection-private.json"
            # Simulate the explicitly authorized local environment for this filesystem-only test.
            # Production's CI ban remains unchanged and is tested separately.
            with patch.object(cli, "PRIVATE_DIR", root), patch.object(cli, "PRIVATE_OUT", dest), \
                 patch.dict("os.environ", {"CI": "", "GITHUB_ACTIONS": ""}):
                report = core.build_selection(
                    [repo("secret", [commit(1, 1, "feat: prototype")], "private")],
                    config(), now=NOW, visibility="private-local")
                cli.write_report(report, dest, "private-local")
                self.assertEqual(dest.stat().st_mode & 0o777, 0o600)
                self.assertEqual(root.stat().st_mode & 0o777, 0o700)
                with self.assertRaises(ValueError):
                    cli.ensure_safe_output(root / "other.json", "private-local")

    def test_private_mode_banned_in_ci_even_for_injected_inventory(self):
        with patch.dict("os.environ", {"CI": "true"}):
            with self.assertRaisesRegex(RuntimeError, "nunca consultar repos privados"):
                cli.run(mode="private-local", inventory=[])

    def test_public_discovery_never_fetches_private_commits(self):
        public = Mock()
        public.full_name = "iagorobo24-hub/GuiaIA"
        public.private = False
        public.archived = False
        public.get_commits.return_value = []
        secret = Mock()
        secret.full_name = "iagorobo24-hub/secret"
        secret.private = True
        secret.archived = False
        api = Mock()
        api.get_user.return_value.get_repos.return_value = [secret, public]
        got = cli.discover(api, config(), now=NOW, mode="public")
        self.assertEqual([r["name"] for r in got], ["iagorobo24-hub/GuiaIA"])
        secret.get_commits.assert_not_called()

    def test_inventory_cap_fails_closed(self):
        cfg = config()
        cfg["max_repositories"] = 1
        api = Mock()
        api.get_user.return_value.get_repos.return_value = [Mock(), Mock()]
        with self.assertRaisesRegex(RuntimeError, "supera el límite"):
            cli.discover(api, cfg, now=NOW, mode="public")


    def test_top_n_does_not_discard_overflow_identity(self):
        cfg = config()
        cfg["top_n"] = 1
        data = [repo("GuiaIA", [commit(1, 1, "feat: gateway")]),
                repo("product-b", [commit(2, 1, "feat: product")]),
                repo("product-c", [commit(3, 1, "test: behavior")])]
        result = core.build_selection(data, cfg, now=NOW)
        self.assertEqual(len(result["ranked"]), 1)
        self.assertEqual(len(result["other_active"]), 2)
        self.assertTrue(all(len(p["repos"]) == 1 and p["title"] and p["activity_score"] > 0
                            and p["visibility"] == "public" for p in result["other_active"]))
        all_names = {name for section in ("ranked", "other_active")
                     for p in result[section] for name in p["repos"]}
        self.assertEqual(all_names, {x["name"] for x in data})



if __name__ == "__main__":
    unittest.main()
