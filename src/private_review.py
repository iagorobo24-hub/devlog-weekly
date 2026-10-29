"""Join GitHub private candidates and explicit local worktrees, without scoring dirty files.

This is a private review inbox, not an input to the public portfolio or
NVIDIA. No Git or network calls: uses two pre-validated local snapshots.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import tempfile

import yaml

try:
    from src.select_projects import PRIVATE_DIR, PRIVATE_OUT
    from src.local_activity import OUTPUT as LOCAL_OUTPUT
except ModuleNotFoundError:
    from select_projects import PRIVATE_DIR, PRIVATE_OUT
    from local_activity import OUTPUT as LOCAL_OUTPUT

MAPPING = PRIVATE_DIR / "local-project-map.yml"
PRIVATE_QUALITY = PRIVATE_DIR / "project-quality-private.json"
OUTPUT = PRIVATE_DIR / "project-review-private.json"
REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
LOCAL_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]{1,64}$")


def read_json(path: Path) -> dict:
    if path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o077:
        raise ValueError("lectura privada insegura")
    obj = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(obj, dict) or obj.get("visibility") != "private-local":
        raise ValueError("informes privados incompatibles")
    return obj


def build_review(selection: dict, local: dict, mapping: dict, *,
                 now: datetime, quality: dict | None = None) -> dict:
    if selection.get("visibility") != "private-local" or local.get("visibility") != "private-local":
        raise ValueError("no combinar informes públicos con privados")
    for section in ("ranked", "other_active", "watchlist"):
        if any(item.get("visibility") != "private" for item in selection.get(section, [])):
            raise ValueError("candidato público detectado en informe privado")
    try:
        observed = datetime.fromisoformat(local["generated_utc"].replace("Z", "+00:00"))
    except (ValueError, KeyError, TypeError) as exc:
        raise ValueError("marca temporal local inválida") from exc
    if observed.tzinfo is None or not timedelta(0) <= now - observed <= timedelta(hours=48):
        raise ValueError("observaciones locales desactualizadas")
    rows = mapping.get("mappings") if isinstance(mapping, dict) and mapping.get("version") == 1 else None
    if not isinstance(rows, list) or not rows or len(rows) > 25:
        raise ValueError("mapeo local inválido")
    repo_index = {repo for group in (selection.get("ranked", []),)
                  for item in group for repo in item.get("repos", [])}
    # If a repo is outside top-N, retain its local signal without inventing a ranking.
    quality_index = {}
    if quality is not None:
        if quality.get("visibility") != "private-local" or quality.get("schema") != 1:
            raise ValueError("calidad privada incompatible")
        try:
            quality_date = datetime.fromisoformat(quality["generated_at"].replace("Z", "+00:00"))
        except (ValueError, KeyError, AttributeError) as exc:
            raise ValueError("fecha de calidad inválida") from exc
        if quality_date.tzinfo is None or not timedelta(0) <= now - quality_date <= timedelta(hours=48):
            raise ValueError("calidad privada desactualizada")
        for item in quality.get("records", []):
            if item.get("visibility") != "private":
                raise ValueError("calidad pública mezclada en informe privado")
            if item["repo"] in quality_index:
                raise ValueError("repo duplicado en informe de calidad")
            quality_index[item["repo"]] = item
    records, seen_paths = [], set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("regla local inválida")
        path = row.get("path")
        if not isinstance(path, str) or path not in local.get("repositories", {}) or path in seen_paths:
            raise ValueError("ruta local no auditada o duplicada")
        seen_paths.add(path)
        repo = row.get("repo")
        project = row.get("local_project")
        if (repo is None) == (project is None):
            raise ValueError("mapeo local requiere repo o local_project, no ambos")
        if repo is not None and (not isinstance(repo, str) or not REPO_RE.fullmatch(repo)):
            raise ValueError("identidad remota inválida")
        if project is not None and (not isinstance(project, str) or not LOCAL_ID_RE.fullmatch(project)):
            raise ValueError("identidad local inválida")
        state = local["repositories"][path]
        changed = state.get("tracked_changes", 0)
        if state.get("state") != "inspected":
            review = "unavailable"
        elif changed > 0:
            review = "local_tracked_changes_require_review"
        elif isinstance(state.get("ahead_of_remote_verified"), int) and state["ahead_of_remote_verified"] > 0:
            review = "remote_confirmed_unpushed_commits_require_review"
        elif state.get("remote_check") == "tracking_ref_stale_or_diverged":
            review = "remote_history_diverged_or_tracking_stale"
        elif state.get("remote_check") == "no_upstream":
            review = "upstream_missing"
        else:
            review = "no_local_flag"
        evidence = quality_index.get(repo, {}) if repo else {}
        records.append({
            "repo": repo, "local_project": project,
            "in_github_top_candidates": repo in repo_index if repo else False,
            "head_ci_status": evidence.get("ci", {}).get("status", "unknown"),
            "quality_readiness": evidence.get("readiness", "quality_not_checked"),
            "strategic_priority": "requires_owner_review",
            "publishable": False,
            "review": review,
            "tracked_changed_files": changed if state.get("state") == "inspected" else None,
            "ahead_of_remote_verified": state.get("ahead_of_remote_verified"),
            "remote_check": state.get("remote_check", "not_checked"),
            "no_claim_of_validated_feature": True,
        })
    return {
        "schema": 1, "visibility": "private-local",
        "built_at": now.isoformat(), "has_private_project_metadata": True,
        "automatic_publication": False, "scoring_changed": False,
        "projects_to_review": records,
    }


def run(now: datetime | None = None) -> dict:
    if os.environ.get("CI") or os.environ.get("GITHUB_ACTIONS"):
        raise RuntimeError("revisión de proyectos privados prohibida en CI")
    if (not MAPPING.is_file() or MAPPING.is_symlink()
            or MAPPING.stat().st_mode & 0o077):
        raise ValueError("mapeo privado inseguro")
    selection = read_json(PRIVATE_OUT)
    local = read_json(LOCAL_OUTPUT)
    mapping = yaml.safe_load(MAPPING.read_text(encoding="utf-8"))
    quality = read_json(PRIVATE_QUALITY) if PRIVATE_QUALITY.exists() else None
    result = build_review(selection, local, mapping, now=now or datetime.now(timezone.utc),
                          quality=quality)
    if PRIVATE_DIR.is_symlink() or OUTPUT.is_symlink() or OUTPUT.parent.resolve() != PRIVATE_DIR.resolve():
        raise ValueError("salida privada no autorizada")
    fd, temp = tempfile.mkstemp(prefix=".project-review-", dir=PRIVATE_DIR)
    try:
        os.chmod(temp, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            json.dump(result, out, ensure_ascii=False, indent=2)
        os.replace(temp, OUTPUT)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)
    return result


if __name__ == "__main__":
    report = run()
    print(f"Revisión privada: {len(report['projects_to_review'])} proyectos y worktrees vinculados. "
          "Ningún cambio de puntuación ni publicación.")
