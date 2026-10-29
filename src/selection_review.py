"""Compare public candidates to existing editorial cases. NEVER auto-promote.

A public repo can be a relevant candidate without having the screenshot,
tests, evidence and manually approved text required by the portfolio.
"""
from __future__ import annotations

import json
from pathlib import Path

try:
    from src.project_selection_core import NAME_RE
    from src.portfolio_data import ROOT, load_portfolio
except ModuleNotFoundError:
    from project_selection_core import NAME_RE
    from portfolio_data import ROOT, load_portfolio

INPUT = ROOT / "out" / "project-selection-public.json"
OUTPUT = ROOT / "out" / "project-selection-review.json"


def build_review(selection: dict, editorial: dict) -> dict:
    if selection.get("schema") != 1 or selection.get("visibility") != "public":
        raise ValueError("solo es válida la selección de repositorios públicos")
    groups = selection.get("ranked")
    if not isinstance(groups, list):
        raise ValueError("selector no contiene candidatos")
    catalog = {p["repo"] for p in editorial["projects"]}
    recommendations = []
    for candidate in groups:
        names = candidate.get("repos")
        if (candidate.get("visibility") != "public"
                or not isinstance(names, list) or not names
                or not all(isinstance(name, str) and NAME_RE.fullmatch(name) for name in names)):
            raise ValueError("candidato mixto, privado o inválido")
        available = sorted(set(names) & catalog)
        missing = sorted(set(names) - catalog)
        recommendations.append({
            "id": candidate["id"], "title": candidate["title"],
            "score": candidate["score"], "active_7d": candidate["active_7d"],
            "repos": names,
            "existing_editorial_profiles": available,
            "missing_editorial_profiles": missing,
            "decision": "review_existing_profile" if not missing else "prepare_evidence_profile",
            "automatic_publication": False,
            "requirements": [
                "identidad y alcance del proyecto confirmados",
                "evidencia reproducible de la revisión específica",
                "capturas autorizadas y versionadas",
                "funcionalidades y limitaciones contrastadas",
                "aprobación editorial antes de promover al PDF",
            ],
        })
    return {
        "schema": 1, "visibility": "public",
        "source_generated_at": selection.get("generated_at"),
        "portfolio_source": "content/portfolio/projects.yml",
        "automatic_publication": False,
        "recommended": recommendations,
        "showcase_not_in_top_candidates": sorted(
            catalog - {repo for item in recommendations for repo in item["repos"]}),
    }


def main() -> None:
    source = json.loads(INPUT.read_text(encoding="utf-8"))
    result = build_review(source, load_portfolio())
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Selección editorial pendiente: {len(result['recommended'])} candidatos públicos, "
          f"{sum(bool(x['missing_editorial_profiles']) for x in result['recommended'])} "
          "necesitan nueva ficha. Sin modificar PDF ni Drive.")


if __name__ == "__main__":
    main()
