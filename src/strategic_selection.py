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
    from src.project_selection_core import configured_projects, NAME_RE, SHA_RE
except ModuleNotFoundError:
    from select_projects import ROOT
    from project_selection_core import configured_projects, NAME_RE, SHA_RE

CONFIG = ROOT / "config/project-selection.yml"
SELECTION = ROOT / "out/project-selection-public.json"
QUALITY = ROOT / "out/project-quality-public.json"
DRAFTS = ROOT / "out/candidate-profiles-review.json"
OUTPUT = ROOT / "out/project-strategy-public.json"
BRANCHES = ROOT / "out/project-branch-activity-public.json"

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


def branch_map_for_selection(selection: dict, report: dict | None) -> dict:
    """Public unmerged activity evidence, distinct from default branch CI."""
    if report is None:
        return {}
    if (not isinstance(report, dict) or report.get("schema") != 1
            or report.get("visibility") != "public"
            or report.get("source_selection_generated_at") != selection.get("generated_at")
            or report.get("private_inputs_accessed") is not False
            or report.get("automatic_publication") is not False
            or report.get("feature_work_is_not_main_or_ci_evidence") is not True
            or report.get("default_branch_counts_unchanged") is not True):
        raise ValueError("Informe de ramas privado, inseguro o desincronizado")
    found = {}
    for row in report.get("repos", []):
        if (not isinstance(row, dict) or row.get("visibility") != "public"
                or row.get("separate_from_default_head_ci") is not True
                or row.get("not_merged_or_runtime_verified") is not True):
            raise ValueError("Información privada o inverificable de ramas")
        name = row.get("repo")
        if not isinstance(name, str) or not NAME_RE.fullmatch(name) or name in found:
            raise ValueError("Rama pública duplicada o repo inválido")
        samples = row.get("sample_recent_substantive_commits", [])
        if not isinstance(samples, list) or len(samples) > 5:
            raise ValueError("Muestra de commits de ramas sin límite seguro")
        seen_samples = set()
        for item in samples:
            if (not isinstance(item, dict)
                    or item.get("kind") not in ("code", "test")
                    or not isinstance(item.get("sha"), str)
                    or not SHA_RE.fullmatch(item["sha"])
                    or item["sha"] in seen_samples
                    or item.get("url") != f"https://github.com/{name}/commit/{item['sha']}"
                    or item.get("commit_subject_only") is not True
                    or item.get("not_merged_or_functionally_verified") is not True
                    or not isinstance(item.get("subject"), str)
                    or not 1 <= len(item["subject"]) <= 300):
                raise ValueError("Muestra de ramas ajena o inválida")
            seen_samples.add(item["sha"])
        counts = row.get("counts_unique_ahead_of_default")
        if counts is not None:
            for key in ("code_7d", "tests_7d", "code_30d", "tests_30d"):
                if type(counts.get(key)) is not int or counts[key] < 0:
                    raise ValueError("Recuentos de rama inválidos")
        found[name] = row
    expected = {name for group in ("ranked", "other_active", "watchlist")
                for candidate in selection.get(group, []) for name in candidate["repos"]}
    if set(found) != expected:
        raise ValueError("Cobertura de actividad de ramas incompleta")
    return found


def branch_signal(row: dict | None, quality: dict | None) -> dict:
    if not row:
        return {"unmerged_code_7d": 0, "unmerged_tests_7d": 0,
                "unmerged_30d": 0, "branch_scan_complete": False,
                "branch_evidence_status": "not_checked",
                "branch_commit_samples": []}
    head = quality.get("head") if quality else None
    stored_head = row.get("default_head_at_scan")
    if head is not None and head != stored_head:
        return {"unmerged_code_7d": 0, "unmerged_tests_7d": 0,
                "unmerged_30d": 0, "branch_scan_complete": False,
                "branch_evidence_status": "default_head_changed",
                "branch_commit_samples": []}
    counts = row.get("counts_unique_ahead_of_default")
    if not isinstance(counts, dict):
        return {"unmerged_code_7d": 0, "unmerged_tests_7d": 0,
                "unmerged_30d": 0, "branch_scan_complete": False,
                "branch_evidence_status": "probe_unavailable",
                "branch_commit_samples": []}
    return {
        "unmerged_code_7d": counts["code_7d"],
        "unmerged_tests_7d": counts["tests_7d"],
        "unmerged_30d": counts["code_30d"] + counts["tests_30d"],
        "branch_scan_complete": row.get("scan_complete") is True,
        "branch_evidence_status": "unmerged_not_validated_on_main",
        "branch_commit_samples": row.get("sample_recent_substantive_commits", []),
    }


def build_public(selection: dict, quality: dict, drafts: dict, config: dict,
                 *, branch_report: dict | None = None) -> dict:
    configured_projects(config)
    if any(obj.get("visibility") != "public" for obj in (selection, quality, drafts)):
        raise ValueError("Datos privados rechazados de selección pública")
    if selection.get("schema") != 1 or quality.get("schema") != 1:
        raise ValueError("Informes públicos inválidos")
    if quality.get("source_selection_generated_at") != selection.get("generated_at"):
        raise ValueError("Informe de calidad de otra revisión")
    sections = ("ranked", "other_active")
    if any(not isinstance(selection.get(k, []), list) for k in sections):
        raise ValueError("Secciones de candidatos inválidas")
    candidates = [(k, c) for k in sections for c in selection.get(k, [])]
    if any(not isinstance(c, dict) or c.get("visibility") != "public"
           for _, c in candidates):
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
    branch_rows = branch_map_for_selection(selection, branch_report)
    result = []
    seen_repos = set()
    for section, candidate in candidates:
        repos = candidate.get("repos")
        if not isinstance(repos, list) or not repos:
            raise ValueError("Candidato sin identidad de repositorio")
        for repo in repos:
            if not isinstance(repo, str) or not NAME_RE.fullmatch(repo):
                raise ValueError("Repositorio inválido")
            if repo in seen_repos:
                raise ValueError("Repositorio repetido entre candidatos")
            seen_repos.add(repo)
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
            branch_evidence = branch_signal(branch_rows.get(repo), q)
            if branch_evidence["unmerged_code_7d"] + branch_evidence["unmerged_tests_7d"]:
                reasons.append("Actividad pública en ramas aún no integradas en la rama predeterminada")
            if branch_rows and not branch_evidence["branch_scan_complete"]:
                reasons.append("Auditoría de ramas incompleta; recuento como mínimo observado")
            result.append({
                **branch_evidence,
                "repo": repo, "title": candidate["title"],
                "selection_bucket": section,
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
    # Historical projects are visible for review, but never promoted just
    # because an old editorial profile or a declared priority exists.
    historical = []
    branch_only_watchlist = []
    watch = selection.get("watchlist", [])
    if not isinstance(watch, list):
        raise ValueError("Lista de seguimiento inválida")
    for candidate in watch:
        if not isinstance(candidate, dict) or candidate.get("visibility") != "public":
            raise ValueError("Candidato privado detectado en seguimiento")
        repos = candidate.get("repos")
        if not isinstance(repos, list) or not repos:
            raise ValueError("Seguimiento sin identidad de repositorio")
        for repo in repos:
            if not isinstance(repo, str) or not NAME_RE.fullmatch(repo):
                raise ValueError("Repositorio de seguimiento inválido")
            if repo in seen_repos:
                raise ValueError("Repositorio duplicado en seguimiento")
            seen_repos.add(repo)
            priority = priorities.get(repo)
            branch_evidence = branch_signal(branch_rows.get(repo), None)
            if (candidate.get("spotlight") is not False and
                    branch_evidence["unmerged_code_7d"] + branch_evidence["unmerged_tests_7d"] > 0):
                branch_only_watchlist.append({
                    **branch_evidence, "repo": repo, "title": candidate["title"],
                    "visibility": "public", "default_branch_inactive": True,
                    "not_ready_for_publication": True, "publishable": False,
                })
            if priority is None or priority < 2 or candidate.get("spotlight") is False:
                continue
            historical.append({
                **branch_evidence,
                "repo": repo, "title": candidate["title"],
                "visibility": "public", "strategic_priority": priority,
                "priority_basis": "proposed_public_config_not_owner_confirmed",
                "watch_reason": candidate.get("watch_reason", "needs_new_evidence"),
                "quality_status": "not_audited_in_current_active_selection",
                "requires_fresh_evidence": True, "publishable": False,
            })
    historical.sort(key=lambda row: (-row["strategic_priority"], row["repo"]))
    tier_order = {"candidate_for_manual_review": 0,
                  "strategic_high_requires_verification": 1,
                  "observe_not_publication_ready": 2,
                  "block_until_ci_diagnosis": 3}
    result.sort(key=lambda x: (tier_order[x["editorial_tier"]],
                               -(x["strategic_priority"] or 0),
                               -(x["unmerged_code_7d"] + x["unmerged_tests_7d"]),
                               -x["evidence_score"], x["repo"]))
    return {
        "schema": 1, "visibility": "public",
        "selection_generated_at": selection["generated_at"],
        "ranked_by_editorial_readiness_not_commit_volume": True,
        "automatic_publication": False,
        "configured_priorities_are_not_owner_approval": True,
        "private_projects_excluded": True,
        "all_active_candidates_considered": True,
        "branch_work_does_not_prove_main_or_ci": True,
        "branch_activity_checked": branch_report is not None,
        "branch_selection_generated_at": (
            branch_report["source_selection_generated_at"] if branch_report else None),
        "proposed_slate": result,
        "historical_watchlist": historical,
        "branch_only_watchlist": branch_only_watchlist,
    }


def main() -> None:
    selection = json.loads(SELECTION.read_text(encoding="utf-8"))
    quality = json.loads(QUALITY.read_text(encoding="utf-8"))
    drafts = json.loads(DRAFTS.read_text(encoding="utf-8"))
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    branch_report = json.loads(BRANCHES.read_text(encoding="utf-8"))
    result = build_public(selection, quality, drafts, cfg, branch_report=branch_report)
    OUTPUT.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{len(result['proposed_slate'])} candidatos públicos clasificados por preparación editorial; "
          "no se cambia el portfolio.")


if __name__ == "__main__":
    main()
