"""Compare public candidates to existing editorial cases. NEVER auto-promote.

A public repo can be a relevant candidate without having the screenshot,
tests, evidence and manually approved text required by the portfolio.
"""
from __future__ import annotations

import json
from pathlib import Path

import yaml

try:
    from src.project_selection_core import NAME_RE
    from src.portfolio_data import ROOT, load_portfolio
    from src.candidate_profiles import CANDIDATES
except ModuleNotFoundError:
    from project_selection_core import NAME_RE
    from portfolio_data import ROOT, load_portfolio
    from candidate_profiles import CANDIDATES

INPUT = ROOT / "out" / "project-selection-public.json"
OUTPUT = ROOT / "out" / "project-selection-review.json"


def build_review(selection: dict, editorial: dict,
                 quality: dict | None = None,
                 candidate_drafts: set[str] | None = None) -> dict:
    if selection.get("schema") != 1 or selection.get("visibility") != "public":
        raise ValueError("solo es válida la selección de repositorios públicos")
    groups = selection.get("ranked")
    overflow = selection.get("other_active", [])
    if not isinstance(groups, list) or not isinstance(overflow, list):
        raise ValueError("selector no contiene candidatos")
    quality_index = {}
    if quality is not None:
        if (quality.get("schema") != 1 or quality.get("visibility") != "public"
                or quality.get("source_selection_generated_at") != selection.get("generated_at")):
            raise ValueError("informe de calidad ajeno o desactualizado")
        for row in quality.get("records", []):
            if row.get("visibility") != "public":
                raise ValueError("calidad privada bloqueada")
            if row["repo"] in quality_index:
                raise ValueError("calidad con repositorio duplicado")
            quality_index[row["repo"]] = row
    catalog = {p["repo"] for p in editorial["projects"]}
    if candidate_drafts is not None and (not isinstance(candidate_drafts, set)
            or any(not isinstance(x, str) or not NAME_RE.fullmatch(x)
                   for x in candidate_drafts)):
        raise ValueError("fichas candidatas inválidas")
    recommendations = []
    seen_candidates = set()
    for section, candidate in ((k, c) for k, items in
                               (("ranked", groups), ("other_active", overflow))
                               for c in items):
        names = candidate.get("repos")
        if (candidate.get("visibility") != "public"
                or not isinstance(names, list) or not names
                or not all(isinstance(name, str) and NAME_RE.fullmatch(name) for name in names)):
            raise ValueError("candidato mixto, privado o inválido")
        if seen_candidates.intersection(names):
            raise ValueError("repo duplicado entre candidatos")
        seen_candidates.update(names)
        available = sorted(set(names) & catalog)
        missing = sorted(set(names) - catalog)
        drafted = sorted(set(names) & candidate_drafts) if candidate_drafts is not None else []
        unprepared = sorted(set(names) - candidate_drafts) if candidate_drafts is not None else []
        checks = [
            {"repo": repo, "readiness": quality_index.get(repo, {}).get(
                "readiness", "quality_not_checked"),
             "ci_at_current_head": quality_index.get(repo, {}).get("ci", {}).get(
                 "status") == "success_at_head",
             "evidence_score": quality_index.get(repo, {}).get("evidence_score", 0),
             "source_head": quality_index.get(repo, {}).get("head")}
            for repo in names
        ]
        recommendations.append({
            "id": candidate["id"], "title": candidate["title"],
            "selection_bucket": section,
            "score": candidate["score"], "active_7d": candidate["active_7d"],
            "repos": names,
            "existing_editorial_profiles": available,
            "missing_editorial_profiles": missing,  # legacy: absent from published portfolio
            "existing_showcase_entries": available,
            "missing_showcase_entries": missing,
            "prepared_candidate_drafts": drafted,
            "missing_candidate_drafts": unprepared,
            "candidate_draft_inventory_checked": candidate_drafts is not None,
            "decision": ("review_existing_profile" if not missing
                         else "review_prepared_candidate" if candidate_drafts is not None
                         and not unprepared else "prepare_evidence_profile"),
            "automatic_publication": False,
            "quality_checks": checks,
            "requires_visual_and_functional_evidence": True,
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
        "quality_evidence_considered": quality is not None,
        "automatic_publication": False,
        "recommended": recommendations,
        "showcase_not_in_top_candidates": sorted(
            catalog - {repo for item in recommendations
                       if item["selection_bucket"] == "ranked" for repo in item["repos"]}),
        "showcase_without_active_candidate": sorted(
            catalog - {repo for item in recommendations for repo in item["repos"]}),
    }


def public_candidate_draft_repos() -> set[str]:
    """Public-only tracked draft inventory, not a readiness/semantic audit."""
    paths = sorted(CANDIDATES.glob("*.yml"))
    if len(paths) > 100:
        raise ValueError("inventario de fichas candidatas sin límite")
    found = set()
    for path in paths:
        if path.is_symlink():
            raise ValueError("ficha simbólica no autorizada")
        item = yaml.safe_load(path.read_text(encoding="utf-8"))
        if (not isinstance(item, dict) or item.get("visibility") != "public"
                or item.get("editorial_status") != "draft_only"
                or not isinstance(item.get("repo"), str)
                or not NAME_RE.fullmatch(item["repo"])
                or item["repo"] in found):
            raise ValueError("ficha candidata privada, inválida o duplicada")
        found.add(item["repo"])
    return found


def main() -> None:
    source = json.loads(INPUT.read_text(encoding="utf-8"))
    quality_file = ROOT / "out" / "project-quality-public.json"
    if not quality_file.is_file():
        raise ValueError("falta informe de calidad: ejecutar audit_project_quality")
    quality = json.loads(quality_file.read_text(encoding="utf-8"))
    result = build_review(source, load_portfolio(), quality,
                          candidate_drafts=public_candidate_draft_repos())
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Selección editorial pendiente: {len(result['recommended'])} candidatos públicos, "
          f"{sum(bool(x['missing_showcase_entries']) for x in result['recommended'])} "
          "fuera del portfolio oficial; "
          f"{sum(bool(x['missing_candidate_drafts']) for x in result['recommended'])} "
          "sin ficha candidata. Sin modificar PDF ni Drive.")


if __name__ == "__main__":
    main()
