"""Explicit strategic/editorial triage. Activity is not strategic value.

Public and private facts are separate. There is no cross-partition ranking
and no automatic export to portfolio or Drive.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import re

import yaml

try:
    from src.select_projects import ROOT
    from src.project_selection_core import configured_projects, NAME_RE
except ModuleNotFoundError:
    from select_projects import ROOT
    from project_selection_core import configured_projects, NAME_RE

CONFIG = ROOT / "config/project-selection.yml"
SELECTION = ROOT / "out/project-selection-public.json"
QUALITY = ROOT / "out/project-quality-public.json"
DRAFTS = ROOT / "out/candidate-profiles-review.json"
OUTPUT = ROOT / "out/project-strategy-public.json"

# Readiness for presentation is NOT a binary consequence of CI.
def classify(*, strategic_priority: int | None, ci_status: str, has_test_path: bool,
             has_draft: bool, currently_active: bool) -> tuple[str, list[str]]:
    reasons = []
    if strategic_priority is None:
        reasons.append("Sin prioridad editorial establecida")
    elif strategic_priority >= 4:
        reasons.append("Prioridad editorial alta propuesta en la configuración; falta ratificación")
    if ci_status == "failure_or_cancelled":
        reasons.append("CI de HEAD fallida o cancelada: no promocionar")
        return "block_until_ci_diagnosis", reasons
    if ci_status in ("unknown", "pending", "inconclusive", "not_checked"):
        reasons.append("Sin validación de CI de la revisión actual")
    elif ci_status == "success_at_head":
        reasons.append("CI correcta sobre la revisión actual; no acredita E2E")
    if not has_test_path:
        reasons.append("Sin ruta de pruebas identificada")
    if not has_draft:
        reasons.append("Falta ficha editorial de evidencia versionada")
    if not currently_active:
        reasons.append("Sin actividad sustancial en la ventana reciente")
    if (strategic_priority is not None and strategic_priority >= 4 and has_draft
            and ci_status == "success_at_head" and has_test_path):
        return "candidate_for_manual_review", reasons
    if strategic_priority is not None and strategic_priority >= 4:
        return "strategic_high_requires_verification", reasons
    if has_draft and has_test_path and ci_status == "success_at_head":
        return "candidate_for_manual_review", reasons
    return "observe_not_publication_ready", reasons


def build_public(selection: dict, quality: dict, drafts: dict, config: dict) -> dict:
    configured_projects(config)
    if any(obj.get("visibility") != "public" for obj in (selection, quality, drafts)):
        raise ValueError("Datos privados rechazados de selección pública")
    if selection.get("schema") != 1 or quality.get("schema") != 1:
        raise ValueError("Informes públicos inválidos")
    if quality.get("source_selection_generated_at") != selection.get("generated_at"):
        raise ValueError("Informe de calidad de otra revisión")
    candidates = selection.get("ranked", [])
    if any(c.get("visibility") != "public" for c in candidates):
        raise ValueError("Candidato privado detectado")
    quality_map = {}
    for q in quality.get("records", []):
        if q.get("visibility") != "public" or q["repo"] in quality_map:
            raise ValueError("Calidad pública duplicada o privada")
        quality_map[q["repo"]] = q
    draft_map = {}
    for d in drafts.get("drafts", []):
        if d.get("visibility") != "public" or d["repo"] in draft_map:
            raise ValueError("Borrador privado o duplicado")
        if d.get("publication_allowed") is not False:
            raise ValueError("Borrador marcado para publicación automática")
        draft_map[d["repo"]] = d
    priorities = {repo: p["priority"] for p in config.get("projects", [])
                  for repo in p["repos"]}
    result = []
    for candidate in candidates:
        for repo in candidate.get("repos", []):
            if not NAME_RE.fullmatch(repo):
                raise ValueError("Repositorio inválido")
            q = quality_map.get(repo)
            if q is None:
                raise ValueError("Candidato sin evaluación de calidad")
            draft = draft_map.get(repo)
            priority = priorities.get(repo)
            ci = q.get("ci", {}).get("status", "not_checked")
            draft_usable = (draft is not None and not draft.get("warnings")
                            and draft.get("revision") == q.get("head"))
            kind, reasons = classify(
                strategic_priority=priority, ci_status=ci,
                has_test_path=q.get("test_path_present") is True,
                has_draft=draft_usable,
                currently_active=candidate.get("active_7d") is True,
            )
            if draft and draft.get("warnings"):
                reasons.append("Borrador con comprobaciones pendientes")
            result.append({
                "repo": repo, "title": candidate["title"],
                "visibility": "public", "strategic_priority": priority,
                "priority_basis": ("proposed_public_config_not_owner_confirmed"
                                   if priority is not None else "not_defined"),
                "activity_score": candidate["activity_score"],
                "evidence_score": q.get("evidence_score", 0),
                "ci_status": ci, "has_candidate_draft": draft is not None,
                "candidate_draft_current_and_verified": draft_usable,
                "editorial_tier": kind, "reasons": reasons,
                "publishable": False, "automatic_publication": False,
            })
    tier_order = {"candidate_for_manual_review": 0,
                  "strategic_high_requires_verification": 1,
                  "observe_not_publication_ready": 2,
                  "block_until_ci_diagnosis": 3}
    result.sort(key=lambda x: (tier_order[x["editorial_tier"]],
                               -(x["strategic_priority"] or 0),
                               -x["evidence_score"], x["repo"]))
    return {
        "schema": 1, "visibility": "public",
        "selection_generated_at": selection["generated_at"],
        "ranked_by_editorial_readiness_not_commit_volume": True,
        "automatic_publication": False,
        "configured_priorities_are_not_owner_approval": True,
        "private_projects_excluded": True,
        "proposed_slate": result,
    }


def main() -> None:
    selection = json.loads(SELECTION.read_text(encoding="utf-8"))
    quality = json.loads(QUALITY.read_text(encoding="utf-8"))
    drafts = json.loads(DRAFTS.read_text(encoding="utf-8"))
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    result = build_public(selection, quality, drafts, cfg)
    OUTPUT.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{len(result['proposed_slate'])} candidatos públicos clasificados por preparación editorial; "
          "no se cambia el portfolio.")


if __name__ == "__main__":
    main()
