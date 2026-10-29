"""Fail-closed public-only editorial coverage and pending-actions report.

Consumes only the existing synchronized, audited public pipeline snapshots.
It does not read private repositories, publish a portfolio or prove runtime QA.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import tempfile

from src.portfolio_data import ROOT
from src.project_selection_core import NAME_RE, SHA_RE, commit_date

OUT = ROOT / "out"
INPUTS = {
    "selection": OUT / "project-selection-public.json",
    "quality": OUT / "project-quality-public.json",
    "strategy": OUT / "project-strategy-public.json",
    "drafts": OUT / "candidate-profiles-review.json",
    "sources": OUT / "candidate-source-audit-public.json",
    "release": OUT / "portfolio-release-review.json",
}
JSON_OUT = OUT / "editorial-coverage-public.json"
MD_OUT = OUT / "editorial-coverage-public.md"

CI_STATES = {"success_at_head", "failure_or_cancelled",
             "unknown", "pending", "inconclusive", "not_checked"}
BLOCKER_RE = re.compile(r"^[a-z][a-z0-9_]{2,100}$")


def index(rows: object, *, label: str) -> dict:
    if not isinstance(rows, list) or len(rows) > 100:
        raise ValueError(f"{label}: filas inválidas o excesivas")
    result = {}
    for row in rows:
        if not isinstance(row, dict) or row.get("visibility") != "public":
            raise ValueError(f"{label}: entrada privada o inválida")
        repo = row.get("repo")
        if (not isinstance(repo, str) or not NAME_RE.fullmatch(repo)
                or repo in result):
            raise ValueError(f"{label}: repo inválido o duplicado")
        result[repo] = row
    return result


def build(selection: dict, quality: dict, strategy: dict, drafts: dict,
          sources: dict, release: dict, *, now: datetime) -> dict:
    if now.tzinfo is None:
        raise ValueError("Fecha editorial sin zona horaria")
    for label, data in (("selection", selection), ("quality", quality),
                        ("strategy", strategy), ("drafts", drafts),
                        ("sources", sources), ("release", release)):
        if (not isinstance(data, dict) or data.get("schema") != 1
                or data.get("visibility") != "public"):
            raise ValueError(f"{label}: informe no público o incompatible")
    stamp = selection.get("generated_at")
    scanned = commit_date(stamp)
    if scanned is None or not timedelta(0) <= now - scanned <= timedelta(hours=36):
        raise ValueError("Selección obsoleta o futura")
    if (quality.get("source_selection_generated_at") != stamp
            or strategy.get("selection_generated_at") != stamp
            or sources.get("source_selection_generated_at") != stamp
            or release.get("selection_generated_at") != stamp
            or sources.get("source_quality_generated_at") != quality.get("generated_at")):
        raise ValueError("Informes editoriales desincronizados")
    if (drafts.get("automatic_publication") is not False
            or strategy.get("automatic_publication") is not False
            or sources.get("automatic_publication") is not False
            or release.get("automatic_publication") is not False
            or release.get("safe_to_replace_public_portfolio") is not False
            or release.get("private_inputs_accessed") is not False
            or sources.get("no_private_data") is not True
            or sources.get("not_functionality_validation") is not True):
        raise ValueError("Promoción automática o contaminación privada")
    current = release.get("current_portfolio")
    if (not isinstance(current, list) or not current
            or any(not isinstance(row, dict)
                   or row.get("visibility") != "public"
                   or row.get("replacement_automatically_allowed") is not False
                   for row in current)):
        raise ValueError("Portfolio publicado no preservado")

    active = {}
    for bucket in ("ranked", "other_active"):
        rows = selection.get(bucket, [])
        if not isinstance(rows, list):
            raise ValueError("Selección activa inválida")
        for group in rows:
            if not isinstance(group, dict) or group.get("visibility") != "public":
                raise ValueError("Selección privada rechazada")
            names = group.get("repos")
            if not isinstance(names, list) or not names:
                raise ValueError("Grupo de repositorios inválido")
            for name in names:
                if (not isinstance(name, str) or not NAME_RE.fullmatch(name)
                        or name in active or len(active) >= 100):
                    raise ValueError("Repositorio duplicado o inválido")
                active[name] = bucket

    indexed = {
        "quality": index(quality.get("records"), label="quality"),
        "strategy": index(strategy.get("proposed_slate"), label="strategy"),
        "drafts": index(drafts.get("drafts"), label="drafts"),
        "sources": index(sources.get("probes"), label="sources"),
        "release": index(release.get("candidates"), label="release"),
    }
    for label in ("quality", "strategy", "release"):
        if set(indexed[label]) != set(active):
            raise ValueError(f"{label}: falta cobertura activa o sobran proyectos")
    if set(indexed["drafts"]) != set(indexed["sources"]):
        raise ValueError("Borradores y auditoría de fuentes sin correspondencia")

    rows = []
    for name in indexed["strategy"]:
        q = indexed["quality"][name]
        strategy_row = indexed["strategy"][name]
        release_row = indexed["release"][name]
        draft = indexed["drafts"].get(name)
        audit = indexed["sources"].get(name)
        head = q.get("head")
        if head is not None and (not isinstance(head, str)
                                or not SHA_RE.fullmatch(head)):
            raise ValueError("HEAD de calidad inválido")
        ci = q.get("ci")
        ci = ci if isinstance(ci, dict) else {}
        ci_state = ci.get("status", "not_checked")
        if (ci_state not in CI_STATES or strategy_row.get("ci_status") != ci_state
                or release_row.get("ci_status") != ci_state
                or strategy_row.get("selection_bucket") != active[name]
                or release_row.get("selection_bucket") != active[name]):
            raise ValueError("Estado CI o procedencia de candidatos contradictorio")
        if (strategy_row.get("publishable") is not False
                or release_row.get("approved_for_release") is not False):
            raise ValueError("Candidato aprobado o promocionado indebidamente")
        blockers = release_row.get("blockers")
        if (not isinstance(blockers, list) or not blockers
                or any(not isinstance(b, str) or not BLOCKER_RE.fullmatch(b)
                       for b in blockers)
                or "independent_runtime_check_missing" not in blockers
                or "explicit_owner_editorial_approval_missing" not in blockers):
            raise ValueError("Puertas de publicación incompletas")
        current_draft = bool(
            draft and isinstance(head, str) and draft.get("revision") == head
            and draft.get("draft_only") is True
            and draft.get("publication_allowed") is False)
        if draft and (draft.get("draft_only") is not True
                      or draft.get("publication_allowed") is not False):
            raise ValueError("Borrador publicado o promovido")
        present = False
        count = 0
        if draft:
            if (audit is None or audit.get("revision") != draft.get("revision")
                    or audit.get("quality_head_matches_revision") is not
                    current_draft):
                raise ValueError("Auditoría de fuentes no corresponde al borrador")
            citations = audit.get("sources")
            if not isinstance(citations, list) or len(citations) > 20:
                raise ValueError("Fuentes de candidato inválidas")
            count = len(citations)
            present = bool(current_draft and count
                           and audit.get("all_sources_exist_at_pinned_revision") is True
                           and all(isinstance(c, dict)
                                   and c.get("status") == "present"
                                   for c in citations))
        if release_row.get("source_presence_verified_at_revision") is not present:
            raise ValueError("Auditoría y preflight discrepan en las fuentes")
        feature = release_row.get("feature_branch_ci", [])
        if not isinstance(feature, list) or len(feature) > 5:
            raise ValueError("CI de ramas sin límite")
        rows.append({
            "repo": name, "visibility": "public",
            "selection_bucket": active[name],
            "default_head": head,
            "ci_at_default_head": ci_state,
            "ci_run_url_at_head": release_row.get("ci_run_url_at_head"),
            "editorial_tier": strategy_row.get("editorial_tier"),
            "has_draft": draft is not None,
            "draft_revision_matches_default_head": current_draft,
            "source_paths_present_at_head": present,
            "source_count": count,
            "subject_statements_not_independently_proven": True,
            "feature_branch_ci_tip_count": len(feature),
            "feature_ci_does_not_validate_default_head": True,
            "blockers": blockers,
            "approved_for_release": False,
        })
    return {
        "schema": 1, "visibility": "public",
        "generated_at": now.astimezone(timezone.utc).isoformat(),
        "source_selection_generated_at": stamp,
        "current_portfolio_preserved": True,
        "current_portfolio_count": len(current),
        "active_candidate_count": len(rows),
        "current_draft_count": sum(x["draft_revision_matches_default_head"] for x in rows),
        "source_verified_candidate_count": sum(x["source_paths_present_at_head"] for x in rows),
        "missing_draft_count": sum(not x["has_draft"] for x in rows),
        "source_paths_are_not_functional_proof": True,
        "ci_is_not_runtime_or_complete_workflow_proof": True,
        "all_cleared_for_publication": False,
        "publication_approved_count": 0,
        "automatic_publication": False,
        "private_inputs_accessed": False,
        "candidates": rows,
    }


def markdown(report: dict) -> str:
    if (report.get("schema") != 1 or report.get("visibility") != "public"
            or report.get("all_cleared_for_publication") is not False
            or report.get("automatic_publication") is not False):
        raise ValueError("Informe editorial no seguro")
    output = [
        "# Cobertura editorial pública — revisión sin publicación", "",
        "**NO PUBLICAR**. Datos públicos por commit; no acreditan ejecución real.",
        "El informe no aprueba ni sustituye el Portfolio Maestro.", "",
        f"Selección: `{report['source_selection_generated_at']}`",
        f"Candidatos activos: **{report['active_candidate_count']}**.",
        f"Fichas en HEAD: **{report['current_draft_count']}**.",
        f"Candidatos con rutas de fuentes verificadas: **{report['source_verified_candidate_count']}**.",
        f"Portfolio conservado: **{report['current_portfolio_count']}** proyectos.", "",
        "| Proyecto | CI en HEAD predeterminado | Ficha actual | Rutas de fuente | Bloqueos |",
        "|---|---|---|---|---:|",
    ]
    for row in report["candidates"]:
        output.append(
            "| " + " | ".join([
                row["repo"], row["ci_at_default_head"],
                "sí" if row["draft_revision_matches_default_head"] else "no",
                "presentes" if row["source_paths_present_at_head"] else "no comprobadas",
                str(len(row["blockers"])),
            ]) + " |")
    output.extend([
        "", "## Interpretación y criterios pendientes", "",
        "Las rutas de archivos verificadas no validan el contenido de las afirmaciones.",
        "La CI de una rama feature no sustituye CI de la rama predeterminada.",
        "Aunque la CI en HEAD esté verde, faltan validación funcional independiente,",
        "capturas autorizadas y aprobación editorial del propietario.", "",
        "El archivo es una vista previa interna, no una autorización para publicar.",
        "",
    ])
    return "\n".join(output)


def run() -> dict:
    inputs = {label: json.loads(path.read_text(encoding="utf-8"))
              for label, path in INPUTS.items()}
    report = build(**inputs, now=datetime.now(timezone.utc))
    outputs = ((JSON_OUT, json.dumps(report, indent=2, ensure_ascii=False) + "\n"),
               (MD_OUT, markdown(report)))
    for target, content in outputs:
        if target.is_symlink() or target.parent.resolve() != OUT.resolve():
            raise ValueError("Ruta de informe editorial no autorizada")
        fd, temp = tempfile.mkstemp(prefix=".editorial-coverage-", dir=OUT)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as writer:
                writer.write(content)
            os.replace(temp, target)
        finally:
            if os.path.exists(temp):
                os.unlink(temp)
    return report


if __name__ == "__main__":
    result = run()
    print("Cobertura pública:", result["active_candidate_count"],
          "fichas en HEAD:", result["current_draft_count"],
          "fuentes estructurales:", result["source_verified_candidate_count"],
          "publicaciones aprobadas:", result["publication_approved_count"])
