"""Contract tests for deterministic factual inputs and zero clipping in Markdown."""
import unittest
from src import backfill, render, synthesize


def sample_repo():
    return {
        "name": "sample/repo", "since": "2026-10-19T00:00:00+00:00",
        "until": "2026-10-26T00:00:00+00:00", "pitch": "Demo",
        "commits": [{
            "sha": "a" * 40, "date": "2026-10-21T11:00:00+00:00",
            "message": "fix: valid evidence"
        }], "issues_closed": [], "prs_closed": [],
        "tags_new": [], "diff_stats": {"files_changed": 1, "additions": 4, "deletions": 2},
    }


class FactualInputTests(unittest.TestCase):
    def test_prompt_includes_full_sha_and_date(self):
        prompt = synthesize.build_prompt(sample_repo(), "")
        self.assertIn("a" * 40, prompt)
        self.assertIn("2026-10-21T11:00:00", prompt)
        self.assertIn("No inventes", prompt)

    def test_sources_have_real_urls_and_dates(self):
        sources = synthesize.verified_sources(sample_repo())
        self.assertEqual(sources[0]["id"], "a" * 10)
        self.assertEqual(sources[0]["url"], "https://github.com/sample/repo/commit/" + "a" * 40)
        self.assertEqual(sources[0]["date"][:10], "2026-10-21")

    def test_date_outside_period_is_rejected(self):
        summary = {"titular": "Cambio el 2026-09-02", "estado": "En pruebas",
                   "avances": ["Se corrigieron tests"], "narrativa_actualizada": "Estado reciente."}
        with self.assertRaisesRegex(ValueError, "fuera del intervalo"):
            synthesize.validate_generated_summary(sample_repo(), summary)

    def test_unsupported_week_number_is_rejected(self):
        summary = {"titular": "Semana 2: nueva migración", "estado": "En pruebas",
                   "avances": ["Se corrigieron tests"], "narrativa_actualizada": "Estado reciente."}
        with self.assertRaisesRegex(ValueError, "numeración"):
            synthesize.validate_generated_summary(sample_repo(), summary)


class SlideLayoutTests(unittest.TestCase):
    def test_empty_week_uses_one_section_not_four(self):
        sample = {"repos": [{"name": f"x/repo{n}", "trivial": True} for n in range(4)]}
        sections, inactive, active = render.build_sections(sample)
        self.assertEqual(len(sections), 1)
        self.assertEqual(len(inactive), 4)
        self.assertFalse(active)

    def test_long_advance_preserved_across_pages(self):
        words = [f"motivo{i}" for i in range(120)]
        slide_groups = render.paginated_bullets([" ".join(words)])
        self.assertGreater(len(slide_groups), 1)
        joint = " ".join(" ".join(p) for p in slide_groups)
        self.assertIn("motivo0", joint)
        self.assertIn("motivo119", joint)

    def test_real_evidence_link_in_weekly_markdown(self):
        repo = sample_repo()
        summary = {
            "name": repo["name"], "since": repo["since"], "until": repo["until"],
            "pitch": "Demo", "trivial": False, "titular": "Corrección concreta",
            "avances": ["Se actualizaron los tests"],
            "estado": "La compilación requiere verificación en CI",
            "activity_counts": {"commits": 1, "prs": 0, "issues": 0},
            "verified_sources": synthesize.verified_sources(repo),
        }
        content = render.render_markdown({
            "generated_at": "2026-10-26T00:00:00+00:00", "repos": [summary]
        })
        self.assertIn("https://github.com/sample/repo/commit/" + "a" * 40, content)
        self.assertIn("Corrección concreta", content)
        self.assertIn("1 de 1 repositorios", content)

    def test_literal_newlines_normalized_in_portfolio_only(self):
        from src import render_master
        from unittest.mock import patch
        from pathlib import Path
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "repo.md"
            path.write_text("primer texto" + chr(92) + "n" + chr(92) + "n" + "segundo texto")
            with patch.object(render_master, "narrative_path", return_value=path):
                text = render_master.load_narrative("sample/repo")
        self.assertEqual(text, "primer texto\n\nsegundo texto")

    def test_historical_slides_contain_every_commit(self):
        from datetime import datetime, timezone
        start = backfill.parse_utc("2026-10-12T00:00:00Z")
        end = backfill.parse_utc("2026-10-19T00:00:00Z")
        commits = [{
            "sha": f"{n+1:040x}",
            "date": "2026-10-15T10:00:00Z", "message": f"Change {n}"
        } for n in range(24)]
        document, info = backfill.summarize_week(
            backfill.week_windows(start, end)[0],
            [{"name": "sample/repo", "commits": commits, "issues_closed": [], "prs_closed": []}],
            max_items=5,
        )
        self.assertEqual(info["repos"][0]["commits"], 24)
        for c in commits:
            self.assertIn(c["sha"][:10], document)
        self.assertIn("Commits verificables · 5/5", document)
        self.assertNotIn("Mostrados 5 de 24", document)


if __name__ == "__main__":
    unittest.main()
