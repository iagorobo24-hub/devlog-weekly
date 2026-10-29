"""Public editorial release preflight; never replaces or publishes a PDF."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import tempfile
from urllib.parse import urlparse

from src.portfolio_data import ROOT, load_portfolio
from src.project_selection_core import NAME_RE, SHA_RE

INPUTS = {
    "selection": ROOT / "out/project-selection-public.json",
    "quality": ROOT / "out/project-quality-public.json",
    "strategy": ROOT / "out/project-strategy-public.json",
    "drafts": ROOT / "out/candidate-profiles-review.json",
}
OUTPUT = ROOT / "out/portfolio-release-review.json"


def _index(rows: object, *, visibility: str) -> dict:
    if not isinstance(rows, list):
        raise ValueError("Filas de revisión editorial inválidas")
    found = {}
    for row in rows:
        if not isinstance(row, dict) or row.get("visibility") != visibility:
            raise ValueError("Contaminación privada en preflight público")
        repo = row.get("repo")
        if not isinstance(repo, str) or not NAME_RE.fullmatch(repo) or repo in found:
            raise ValueError("Identidad pública inválida o duplicada")
        found[repo] = row
    return found


def _pinned_sources(draft: dict, repo: str, revision: str) -> bool:
    sources = draft.get("sources")
    if not isinstance(sources, list) or not sources:
        return False
    for source in sources:
        if not isinstance(source, dict) or not isinstance(source.get("statement"), str):
            return False
        url = source.get("url")
        if not isinstance(url, str) or len(source["statement"].strip()) < 15:
            return False
        uri = urlparse(url)
        base = f"/{repo}/"
        if (uri.scheme != "https" or uri.netloc != "github.com"
                or uri.username or uri.password or uri.query or uri.fragment
                or not (uri.path.startswith(base + "blob/" + revision + "/")
                        or uri.path.startswith(base + "tree/" + revision + "/"))):
            return False
    return True


def build_review(selection: dict, quality: dict, strategy: dict,
                 drafts: dict, portfolio: dict, *, now: datetime | None = None) -> dict:
    for label, report in (("selection", selection), ("quality", quality),
                          ("strategy", strategy), ("drafts", drafts)):
        if not isinstance(report, dict) or report.get("visibility") != "public":
            raise ValueError(f"{label}: partición pública obligatoria")
        if report.get("schema") != 1:
            raise ValueError("Versión pública incompatible")
    if (strategy.get("selection_generated_at") != selection.get("generated_at")
            or quality.get("source_selection_generated_at") != selection.get("generated_at")):
        raise ValueError("Fuentes de selección no coinciden")
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("Fecha de revisión sin zona horaria")
    for label, stamp in (("selection", selection.get("generated_at")),
                         ("quality", quality.get("generated_at"))):
        try:
            observed = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        except (AttributeError, ValueError) as exc:
            raise ValueError(f"{label}: fecha no verificable") from exc
        if observed.tzinfo is None or not timedelta(0) <= now - observed <= timedelta(hours=36):
            raise ValueError(f"{label}: informe obsoleto o futuro")
    watch = selection.get("watchlist", [])
    if not isinstance(watch, list) or any(
            not isinstance(x, dict) or x.get("visibility") != "public" for x in watch):
        raise ValueError("Seguimiento público contaminado")
    if (strategy.get("automatic_publication") is not False or
            drafts.get("automatic_publication") is not False or
            strategy.get("private_projects_excluded") is not True):
        raise ValueError("Señal de publicación insegura")
    active = {}
    for bucket in ("ranked", "other_active"):
        rows = selection.get(bucket, [])
        if not isinstance(rows, list):
            raise ValueError("Selección sin grupos válidos")
        for group in rows:
            if not isinstance(group, dict) or group.get("visibility") != "public":
                raise ValueError("Candidato privado en selección pública")
            names = group.get("repos")
            if not isinstance(names, list) or not names:
                raise ValueError("Candidato sin identidad")
            for repo in names:
                if not isinstance(repo, str) or not NAME_RE.fullmatch(repo) or repo in active:
                    raise ValueError("Candidato duplicado o inválido")
                active[repo] = bucket
    checked = _index(quality.get("records"), visibility="public")
    ranked = _index(strategy.get("proposed_slate"), visibility="public")
    profiles = _index(drafts.get("drafts"), visibility="public")
    historical = _index(strategy.get("historical_watchlist", []), visibility="public")
    if set(active) != set(checked) or set(active) != set(ranked):
        raise ValueError("Cobertura activa incompleta")
    if set(active) & set(historical):
        raise ValueError("Solapamiento activos/históricos")
    if any(p.get("publication_allowed") is not False or p.get("draft_only") is not True
           for p in profiles.values()):
        raise ValueError("Ficha no autorizada para publicación")
    if any(p.get("publishable") is not False for p in ranked.values()):
        raise ValueError("Candidato marcado para publicación prematura")
    if any(p.get("publishable") is not False for p in historical.values()):
        raise ValueError("Histórico marcado para publicación")
    if not isinstance(portfolio, dict) or portfolio.get("version") != 2:
        raise ValueError("Portfolio incompatible")
    current = {}
    for project in portfolio.get("projects", []):
        if not isinstance(project, dict):
            raise ValueError("Portfolio inválido")
        repo, revision = project.get("repo"), project.get("revision")
        if (not isinstance(repo, str) or not NAME_RE.fullmatch(repo)
                or not isinstance(revision, str) or not SHA_RE.fullmatch(revision)
                or repo in current):
            raise ValueError("Identidad actual inválida")
        current[repo] = revision
    rows = []
    for repo, bucket in active.items():
        q, s, draft = checked[repo], ranked[repo], profiles.get(repo)
        if s.get("selection_bucket") != bucket:
            raise ValueError("Grupo de estrategia distinto")
        ci = q.get("ci", {}).get("status", "not_checked")
        if s.get("ci_status") != ci:
            raise ValueError("Evidencia CI contradictoria")
        head = q.get("head")
        head_valid = isinstance(head, str) and bool(SHA_RE.fullmatch(head))
        blockers = []
        if ci == "failure_or_cancelled":
            blockers.append("ci_failure_needs_diagnosis")
        elif ci != "success_at_head":
            blockers.append("ci_at_current_head_not_proven")
        if q.get("test_path_present") is not True:
            blockers.append("test_path_not_proven")
        if not draft:
            blockers.append("no_editorial_draft")
        elif (not head_valid or draft.get("revision") != head or draft.get("warnings")
              or not _pinned_sources(draft, repo, head)):
            blockers.append("editorial_evidence_stale_or_unverified")
        blockers.extend(("independent_runtime_check_missing",
                         "authorized_runtime_visuals_missing",
                         "explicit_owner_editorial_approval_missing"))
        rows.append({
            "repo": repo, "title": s.get("title"), "visibility": "public",
            "selection_bucket": bucket, "head": head if head_valid else None,
            "ci_status": ci, "editorial_tier": s.get("editorial_tier"),
            "currently_in_portfolio": repo in current,
            "blockers": blockers, "approved_for_release": False,
        })
    return {
        "schema": 1, "visibility": "public",
        "selection_generated_at": selection["generated_at"],
        "current_portfolio_preserved": True, "automatic_publication": False,
        "safe_to_replace_public_portfolio": False,
        "runtime_evidence_not_inferred_from_ci": True,
        "candidates": rows,
        "current_portfolio": [
            {"repo": repo, "visibility": "public", "pinned_revision": revision,
             "active_candidate": repo in active,
             "historical_watchlist": repo in historical,
             "replacement_automatically_allowed": False}
            for repo, revision in current.items()
        ],
        "historical_review_count": len(historical),
        "private_inputs_accessed": False,
    }


def run() -> dict:
    reports = {label: json.loads(path.read_text(encoding="utf-8"))
               for label, path in INPUTS.items()}
    result = build_review(**reports, portfolio=load_portfolio())
    if OUTPUT.is_symlink() or OUTPUT.parent.resolve() != (ROOT / "out").resolve():
        raise ValueError("Destino no autorizado")
    fd, temp = tempfile.mkstemp(prefix=".release-review-", dir=OUTPUT.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as writer:
            json.dump(result, writer, ensure_ascii=False, indent=2)
            writer.write("\n")
        os.replace(temp, OUTPUT)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)
    return result


if __name__ == "__main__":
    result = run()
    print(f"Preflight público: {len(result['candidates'])} candidatos; "
          f"{len(result['current_portfolio'])} proyectos conservados; "
          "ninguna autorización de publicación.")
