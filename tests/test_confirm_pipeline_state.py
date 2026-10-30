"""Single transactional commit for both weekly history and GitHub cursors."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from src import confirm_pipeline_state as state

NOW = "2026-10-29T20:00:00+00:00"
START = "2026-10-28T20:00:00+00:00"
NAMES = ["example/alpha", "example/bravo"]


def fixture(names=None, run_id="123"):
    names = names or NAMES
    collected = {"generated_at": NOW, "github_run_id": run_id,
                 "repos": [{"name": n, "since": START, "until": NOW,
                            "tags_all": ["v1.0"], "tags_new": [],
                            "commits": [], "prs_closed": [], "issues_closed": [],
                            "showcase": False, "pitch": None} for n in names]}
    raw = (json.dumps(collected, indent=2) + "\n").encode()
    summaries = {"generated_at": NOW, "github_run_id": run_id,
                 "source_collected_sha256": hashlib.sha256(raw).hexdigest(),
                 "repos": [{"name": n, "since": START, "until": NOW,
                            "narrativa_actualizada": "Narrative for " + n} for n in names]}
    prev = {n: {"since": START, "tags_seen": []} for n in names}
    return collected, raw, summaries, prev


class PrepareTests(unittest.TestCase):
    def test_matching_source_and_single_run_valid(self):
        c, raw, s, prev = fixture()
        plan = state.prepare_state(c, raw, s, prev, NAMES, "123")
        self.assertEqual(set(plan["narratives"]), {"alpha.md", "bravo.md"})
        self.assertEqual(plan["last_run"][NAMES[0]]["since"], NOW)

    def test_rejects_missing_extra_or_duplicate_repo(self):
        c, raw, s, prev = fixture()
        s["repos"].pop()
        with self.assertRaisesRegex(ValueError, "mismos repos"):
            state.prepare_state(c, raw, s, prev, NAMES, "123")
        c, raw, s, prev = fixture()
        c["repos"].append(c["repos"][0])
        with self.assertRaisesRegex(ValueError, "duplicados"):
            state.prepare_state(c, raw, s, prev, NAMES, "123")

    def test_rejects_stale_summary_sha_and_mismatched_run_id(self):
        c, raw, s, prev = fixture()
        s["source_collected_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "desacoplada"):
            state.prepare_state(c, raw, s, prev, NAMES, "123")
        c, raw, s, prev = fixture()
        with self.assertRaisesRegex(ValueError, "GITHUB_RUN_ID"):
            state.prepare_state(c, raw, s, prev, NAMES, "124")

    def test_rejects_interval_mismatch_and_state_regression(self):
        c, raw, s, prev = fixture()
        s["repos"][1]["until"] = START
        with self.assertRaisesRegex(ValueError, "otro intervalo"):
            state.prepare_state(c, raw, s, prev, NAMES, "123")
        c, raw, s, prev = fixture()
        prev[NAMES[0]]["since"] = "2026-10-30T00:00:00+00:00"
        with self.assertRaisesRegex(ValueError, "retroceso"):
            state.prepare_state(c, raw, s, prev, NAMES, "123")

    def test_rejects_nonexistent_narrative_and_name_collision(self):
        c, raw, s, prev = fixture()
        s["repos"][1]["narrativa_actualizada"] = " "
        with self.assertRaisesRegex(ValueError, "narrativa ausente"):
            state.prepare_state(c, raw, s, prev, NAMES, "123")
        names = ["user1/same", "user2/same"]
        c, raw, s, prev = fixture(names)
        with self.assertRaisesRegex(ValueError, "colisionan"):
            state.prepare_state(c, raw, s, prev, names, "123")

    def test_rejects_future_source_and_naive_time(self):
        c, raw, s, prev = fixture()
        c["generated_at"] = "2099-01-01T00:00:00+00:00"
        s["generated_at"] = c["generated_at"]
        with self.assertRaisesRegex(ValueError, "futura"):
            state.prepare_state(c, raw, s, prev, NAMES, "123")
        c, raw, s, prev = fixture()
        c["repos"][0]["since"] = "2026-10-28T20:00:00"
        with self.assertRaisesRegex(ValueError, "zona"):
            state.prepare_state(c, raw, s, prev, NAMES, "123")


class ConfirmTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.out = self.root / "out"
        self.out.mkdir()
        self.state_dir = self.root / "state"
        self.state_dir.mkdir()
        self.narr = self.state_dir / "narrative"
        self.narr.mkdir()
        self.config = self.root / "repos.yml"
        self.config.write_text("repos:\n  - name: example/alpha\n  - name: example/bravo\n")
        c, raw, s, prev = fixture()
        (self.out / "collected.json").write_bytes(raw)
        (self.out / "summaries.json").write_text(json.dumps(s), encoding="utf-8")
        self.last = self.state_dir / "last_run.json"
        self.last.write_text(json.dumps(prev), encoding="utf-8")
        for name in ("alpha.md", "bravo.md"):
            (self.narr / name).write_text("Old narrative\n")
        overrides = {
            "COLLECTED_PATH": self.out / "collected.json",
            "SUMMARIES_PATH": self.out / "summaries.json",
            "LAST_RUN_PATH": self.last,
            "NARRATIVE_DIR": self.narr,
            "CONFIG_PATH": self.config,
        }
        self.patchers = [patch.object(state, name, path) for name, path in overrides.items()]
        for p in self.patchers:
            p.start()
            self.addCleanup(p.stop)

    def _original(self):
        return {p: p.read_bytes() for p in [self.last, self.narr/"alpha.md", self.narr/"bravo.md"]}

    def test_prepublication_gate_reads_but_does_not_modify_any_state(self):
        before = self._original()
        with (patch.dict(os.environ, {"GITHUB_RUN_ID": "123"}),
              patch.object(state, "install_state") as writer):
            self.assertEqual(state.check_state(), 2)
            writer.assert_not_called()
        self.assertEqual(self._original(), before)
        self.assertEqual(list(self.state_dir.rglob(".devlog-stage-*")), [])

    def test_prepublication_gate_rejects_corrupted_summary_before_publish(self):
        before = self._original()
        broken = json.loads((self.out / "summaries.json").read_text())
        broken["source_collected_sha256"] = "0" * 64
        (self.out / "summaries.json").write_text(json.dumps(broken))
        with patch.dict(os.environ, {"GITHUB_RUN_ID": "123"}):
            with self.assertRaisesRegex(ValueError, "desacoplada"):
                state.check_state()
        self.assertEqual(self._original(), before)

    def test_prepublication_and_confirmation_share_validation(self):
        with patch.dict(os.environ, {"GITHUB_RUN_ID": "123"}):
            plan = state.validated_updates()
            self.assertEqual(plan[self.last], (
                json.dumps({name: {"since": NOW, "tags_seen": ["v1.0"]}
                            for name in NAMES},
                           indent=2, ensure_ascii=False) + "\n").encode("utf-8"))
            self.assertEqual(state.check_state(), state.confirm_state())
        self.assertEqual(self._original(), plan)

    def test_prepublication_fails_on_unsafe_destination_without_writing(self):
        before = self._original()
        alias = self.narr / "alpha.md"
        alias.unlink()
        alias.symlink_to(self.narr / "bravo.md")
        with patch.dict(os.environ, {"GITHUB_RUN_ID": "123"}):
            with self.assertRaisesRegex(ValueError, "inseguro"):
                state.check_state()
        self.assertEqual(self.last.read_bytes(), before[self.last])
        self.assertEqual((self.narr / "bravo.md").read_bytes(), before[self.narr / "bravo.md"])

    def test_complete_commit_updates_both_and_is_idempotent(self):
        with patch.dict(os.environ, {"GITHUB_RUN_ID": "123"}):
            self.assertEqual(state.confirm_state(), 2)
            first = self._original()
            self.assertIn(b"2026-10-29", first[self.last])
            self.assertIn(b"Narrative for example", first[self.narr / "bravo.md"])
            self.assertEqual(state.confirm_state(), 2)
            self.assertEqual(self._original(), first)

    def test_failure_does_not_touch_existing_state(self):
        original = self._original()
        broken = json.loads((self.out/"summaries.json").read_text())
        broken["github_run_id"] = "other"
        (self.out/"summaries.json").write_text(json.dumps(broken))
        with patch.dict(os.environ, {"GITHUB_RUN_ID": "123"}):
            with self.assertRaisesRegex(ValueError, "GITHUB_RUN_ID"):
                state.confirm_state()
        self.assertEqual(self._original(), original)

    def test_io_failure_rolls_back_all_already_written_targets(self):
        original = self._original()
        real_replace = os.replace
        calls = 0

        def fail_second(src, dst):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("simulated I/O failure")
            return real_replace(src, dst)

        with (patch.dict(os.environ, {"GITHUB_RUN_ID": "123"}),
              patch.object(state.os, "replace", side_effect=fail_second)):
            with self.assertRaisesRegex(OSError, "simulated"):
                state.confirm_state()
        self.assertEqual(self._original(), original)
        self.assertFalse(list(self.state_dir.rglob(".devlog-stage-*")))

    def test_failed_rollback_preserves_recoverable_backups(self):
        # On the second write failure AND failed rollback of the first write,
        # old bytes must remain retrievable for manual recovery.
        import stat
        original = self._original()
        real_replace = os.replace
        calls = 0

        def fail_write_and_rollback(src, dst):
            nonlocal calls
            calls += 1
            if calls in (2, 3):
                raise OSError("simulated failed write / failed rollback")
            return real_replace(src, dst)

        with (patch.dict(os.environ, {"GITHUB_RUN_ID": "123"}),
              patch.object(state.os, "replace", side_effect=fail_write_and_rollback)):
            with self.assertRaisesRegex(
                    RuntimeError, "respaldos conservados") as raised:
                state.confirm_state()

        copies = list(self.state_dir.rglob(".devlog-stage-*"))
        self.assertTrue(copies)
        self.assertTrue(any(path.read_bytes() == original[self.last]
                            for path in copies))
        self.assertTrue(all(stat.S_IMODE(path.stat().st_mode) == 0o600
                            for path in copies))
        self.assertIn("last_run.json", str(raised.exception))
        self.assertIn("recuperación manual", str(raised.exception))

    def test_synthesis_uses_exact_source_bytes_then_commits(self):
        # Integration without LLM/network: repositories have no activity.
        from argparse import Namespace
        from src import synthesize

        with (patch.object(synthesize, "COLLECTED_PATH", self.out/"collected.json"),
              patch.object(synthesize, "OUT_PATH", self.out/"summaries.json"),
              patch.object(synthesize, "parse_args", return_value=Namespace(
                  commit_state=False, dry_run=False, no_state=True, repo=None, model=None)),
              patch.object(synthesize, "OpenAI", return_value=object()),
              patch.dict(os.environ, {"GITHUB_RUN_ID": "123",
                                      "NVIDIA_API_KEY": "synthetic-not-a-secret"})):
            synthesize.main()

        summary = json.loads((self.out/"summaries.json").read_text())
        self.assertEqual(summary["github_run_id"], "123")
        self.assertEqual(summary["source_collected_sha256"],
                         hashlib.sha256((self.out/"collected.json").read_bytes()).hexdigest())
        self.assertEqual(summary["repos"][0]["narrativa_actualizada"],
                         "Sin actividad registrada todavía.")

        with patch.dict(os.environ, {"GITHUB_RUN_ID": "123"}):
            state.confirm_state()
        self.assertIn("Sin actividad registrada",
                      (self.narr/"alpha.md").read_text())

    def test_workflow_has_only_one_state_confirmation_step(self):
        workflow = (state.ROOT / ".github/workflows/weekly.yml").read_text()
        self.assertEqual(workflow.count("uv run python -m src.confirm_pipeline_state --check-only"), 1)
        self.assertEqual(workflow.count("uv run python -m src.confirm_pipeline_state\n"), 1)
        self.assertLess(workflow.index("      - name: Sintetizar"),
                        workflow.index("      - name: Validar consistencia antes de renderizar o publicar"))
        self.assertLess(workflow.index("      - name: Validar consistencia antes de renderizar o publicar"),
                        workflow.index("      - name: Renderizar"))
        self.assertLess(workflow.index("      - name: Validar consistencia antes de renderizar o publicar"),
                        workflow.index("      - name: Publicar\n"))
        self.assertNotIn("uv run python src/collect.py --commit-state", workflow)
        self.assertNotIn("uv run python src/synthesize.py --commit-state", workflow)
        self.assertIn("git diff --staged --quiet || git commit", workflow)
        self.assertLess(workflow.index("      - name: Publicar deck maestro"),
                        workflow.index("      - name: Confirmar estado"))
        self.assertLess(workflow.index("      - name: Confirmar estado"),
                        workflow.index("      - name: Guardar estado"))

    def test_rejects_narrative_symlink_before_writing(self):
        original = self._original()
        target = self.narr / "bravo.md"
        target.unlink()
        target.symlink_to(self.narr / "alpha.md")
        with patch.dict(os.environ, {"GITHUB_RUN_ID": "123"}):
            with self.assertRaisesRegex(ValueError, "inseguro"):
                state.confirm_state()
        self.assertEqual(self.last.read_bytes(), original[self.last])
        self.assertEqual((self.narr/"alpha.md").read_bytes(), original[self.narr/"alpha.md"])


if __name__ == "__main__":
    unittest.main()
