"""A weekly PDF should not promote PSM-only repository maintenance."""
import json
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from src import render, synthesize


def commit(n: int, message: str) -> dict:
    return {
        "sha": f"{n:040x}",
        "date": "2026-10-29T12:00:00+00:00",
        "message": message,
    }


def sample(commits: list[dict], **extra) -> dict:
    data = {
        "name": "example/alpha",
        "since": "2026-10-23T00:00:00+00:00",
        "until": "2026-10-30T03:00:00+00:00",
        "commits": commits,
        "issues_closed": [], "prs_closed": [], "tags_new": [],
        "pitch": "Repo sintético", "showcase": False,
        "diff_stats": {"files_changed": 1, "additions": 1, "deletions": 0},
    }
    data.update(extra)
    return data


class SubstantiveWeeklyTests(unittest.TestCase):
    def test_psm_and_routine_only_do_not_trigger_ai(self):
        row = sample([
            commit(1, "fix(psm): refresh manifest audit hash"),
            commit(2, "docs: update README"),
            commit(3, "chore: routine metadata"),
            commit(4, "ci: pin action"),
        ])
        self.assertFalse(synthesize.has_activity(row))
        model = Mock(side_effect=AssertionError("No AI calls permitted"))
        result = synthesize.synthesize_repo(
            None, ["not-needed"], row, "Preservar narrativa histórica.", False)
        model.assert_not_called()
        self.assertTrue(result["trivial"])
        self.assertEqual(result["narrativa_actualizada"],
                         "Preservar narrativa histórica.")
        self.assertIn("rutinaria", result["estado"])
        self.assertEqual(synthesize.verified_sources(row), [])

    def test_unknown_subject_remains_reviewable_not_silently_dropped(self):
        row = sample([commit(1, "Implement device bridge")])
        self.assertTrue(synthesize.has_activity(row))
        condensed = synthesize.condense(row)
        self.assertEqual(condensed["commits"]["relevantes_o_sin_clasificar"], 1)
        self.assertEqual(len(condensed["commits"]["eventos"]), 1)

    def test_substantive_commit_overrides_noisy_neighbors(self):
        row = sample([
            commit(1, "fix(psm): refresh"),
            commit(2, "docs: overview"),
            commit(3, "feat: actual source change"),
            commit(4, "test: check response"),
        ])
        self.assertTrue(synthesize.has_activity(row))
        events = synthesize.condense(row)["commits"]
        self.assertEqual(events["total"], 4)
        self.assertEqual(events["relevantes_o_sin_clasificar"], 2)
        self.assertEqual(events["mantenimiento_y_psm_omitidos"], 2)
        self.assertEqual([x["titulo"] for x in events["eventos"]],
                         ["feat: actual source change", "test: check response"])
        references = synthesize.verified_sources(row)
        self.assertEqual(len(references), 2)
        self.assertTrue(all("fix(psm)" not in x["title"] for x in references))

    def test_pr_issue_or_release_still_is_real_activity(self):
        noise = [commit(1, "docs(psm): baseline refresh")]
        for override in (
            {"prs_closed": [{"number": 1, "title": "Closed",
                             "merged": False, "closed_at": "2026-10-29T00:00:00Z"}]},
            {"issues_closed": [{"number": 1, "title": "Resolved",
                                "closed_at": "2026-10-29T00:00:00Z"}]},
            {"tags_new": ["v1.2.0"]},
        ):
            with self.subTest(source=override):
                self.assertTrue(synthesize.has_activity(sample(noise, **override)))

    def test_model_cannot_mark_substantive_work_as_trivial(self):
        body = {
            "titular": "Cambio registrado",
            "avances": ["Cambio de código contrastable."],
            "estado": "Sin QA externa.",
            "narrativa_actualizada": "Pendiente de revisión.",
            "trivial": True,
        }
        response = SimpleNamespace(choices=[
            SimpleNamespace(message=SimpleNamespace(content=json.dumps(body)))])
        model = Mock()
        model.chat.completions.create.return_value = response
        output = synthesize.call_model_once(model, "mock-model", "Prompt")
        self.assertFalse(output["trivial"])

    def test_main_derives_trivial_from_source_even_if_adapter_lies(self):
        import os
        import tempfile
        from argparse import Namespace
        from pathlib import Path
        from unittest.mock import patch

        code = sample([commit(1, "feat: implementation")])
        docs = sample([commit(2, "docs(psm): metadata refresh")],
                      name="example/bravo")
        source = {"generated_at": "2026-10-30T03:00:00+00:00",
                  "repos": [code, docs]}
        mocked = {"titular": "Actividad para revisión",
                  "avances": ["Solo evidencia sintética"],
                  "estado": "Requiere QA",
                  "narrativa_actualizada": "No publicar",
                  "trivial": True, "model_used": "synthetic"}
        with tempfile.TemporaryDirectory() as folder:
            inp = Path(folder) / "collected.json"
            out = Path(folder) / "summaries.json"
            inp.write_text(json.dumps(source))
            with (patch.dict(os.environ, {"NVIDIA_API_KEY": "offline-only"}),
                  patch.object(synthesize, "COLLECTED_PATH", inp),
                  patch.object(synthesize, "OUT_PATH", out),
                  patch.object(synthesize, "parse_args",
                               return_value=Namespace(
                                   commit_state=False, dry_run=False,
                                   no_state=True, repo=None, model=None)),
                  patch.object(synthesize, "OpenAI", return_value=object()),
                  patch.object(synthesize, "synthesize_repo",
                               return_value=dict(mocked))):
                synthesize.main()
            results = json.loads(out.read_text())["repos"]
        self.assertEqual([r["trivial"] for r in results], [False, True])

    def test_renderer_labels_non_substantive_projects_accurately(self):
        repo = sample([commit(1, "docs(psm): audit")])
        summary = synthesize.synthesize_repo(
            None, ["unused"], repo, "Narrativa previa.", False)
        view = {"name": repo["name"], "trivial": summary["trivial"],
                "since": repo["since"], "until": repo["until"],
                "titular": summary["titular"], "estado": summary["estado"]}
        sections, inactive, active = render.build_sections({"repos": [view]})
        self.assertEqual(sections, [])
        self.assertEqual(inactive, ["alpha"])
        self.assertEqual(active, [])
        content = render.render_markdown({
            "generated_at": "2026-10-30T03:00:00+00:00",
            "repos": [view],
        })
        self.assertIn("Sin avances sustanciales: alpha", content)
        self.assertNotIn("## alpha", content)


if __name__ == "__main__":
    unittest.main()
