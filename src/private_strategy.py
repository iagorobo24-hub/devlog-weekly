"""Private strategic proposal, based on explicit LOCAL candidate priorities.

These priorities are proposals, never inferred by the algorithm from commits.
No private names are logged or included in public reports.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile

import yaml

try:
    from src.select_projects import PRIVATE_DIR, PRIVATE_OUT
    from src.private_review import OUTPUT as LOCAL_REVIEW
    from src.private_project_quality import OUTPUT as PRIVATE_QUALITY
except ModuleNotFoundError:
    from select_projects import PRIVATE_DIR, PRIVATE_OUT
    from private_review import OUTPUT as LOCAL_REVIEW
    from private_project_quality import OUTPUT as PRIVATE_QUALITY

CONFIG = PRIVATE_DIR / "strategic-priorities.yml"
OUTPUT = PRIVATE_DIR / "project-strategy-private.json"
MAX_PRIORITIES = 40


def secure_read(path: Path) -> dict:
    if not path.is_file() or path.is_symlink() or path.stat().st_mode & 0o077:
        raise ValueError("lectura insegura del informe privado")
    if path.suffix == ".yml":
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    return json.loads(path.read_text(encoding="utf-8"))


def build(selection: dict, quality: dict, local: dict, config: dict) -> dict:
    if any(x.get("visibility") != "private-local" for x in (selection, quality, local)):
        raise ValueError("prohibido mezclar particiones de visibilidad")
    if not isinstance(config, dict) or config.get("version") != 1:
        raise ValueError("prioridades locales mal configuradas")
    proposed = config.get("proposals")
    if not isinstance(proposed, list) or len(proposed) > MAX_PRIORITIES:
        raise ValueError("propuestas estratégicas inválidas")
    priorities = {}
    for item in proposed:
        if not isinstance(item, dict) or set(item) != {
                "repo", "priority", "basis", "rationale"}:
            raise ValueError("prioridad sin campos esperados")
        key, priority, basis, rationale = (
            item["repo"], item["priority"], item["basis"], item["rationale"])
        if (not isinstance(key, str) or not key or key in priorities
                or type(priority) is not int or not 0 <= priority <= 5
                or basis not in {"inferred_proposal", "explicit_owner"}
                or not isinstance(rationale, str) or not 10 <= len(rationale) <= 300):
            raise ValueError("prioridad estratégica ambigua")
        priorities[key] = item
    quality_index = {}
    for q in quality.get("records", []):
        if q.get("visibility") != "private":
            raise ValueError("calidad contaminada por repositorios públicos")
        quality_index[q["repo"]] = q
    local_index = {r["repo"]: r for r in local.get("projects_to_review", [])
                   if r.get("repo") is not None}
    rows = []
    sections = ("ranked", "other_active")
    if any(not isinstance(selection.get(k, []), list) for k in sections):
        raise ValueError("sección de candidatos privados inválida")
    candidates = [(k, p) for k in sections for p in selection.get(k, [])]
    seen_repos = set()
    for section, project in candidates:
        if project.get("visibility") != "private":
            raise ValueError("candidato público en informe privado")
        for repo in project.get("repos", []):
            if repo in seen_repos:
                raise ValueError("repo privado duplicado entre candidatos")
            seen_repos.add(repo)
            info = priorities.get(repo)
            q = quality_index.get(repo, {})
            ci = q.get("ci", {}).get("status", "unknown")
            local_state = local_index.get(repo, {})
            flags = []
            if ci == "failure_or_cancelled":
                flags.append("diagnose_ci_at_head")
            elif ci != "success_at_head":
                flags.append("head_ci_unconfirmed")
            if local_state.get("review") not in (None, "no_local_flag"):
                flags.append("local_git_state_requires_review")
            if info is None or info["basis"] != "explicit_owner":
                flags.append("strategic_priority_not_owner_confirmed")
            if not q.get("test_path_present"):
                flags.append("test_path_not_detected")
            rows.append({
                "repo": repo, "visibility": "private",
                "selection_bucket": section,
                "activity_score": project.get("activity_score"),
                "priority": info["priority"] if info else None,
                "priority_basis": info["basis"] if info else "unset",
                "rationale": info["rationale"] if info else None,
                "quality_readiness": q.get("readiness", "not_checked"),
                "head_ci_status": ci,
                "local_state": local_state.get("review", "no_local_link"),
                "reasons_to_review": flags, "publishable": False,
                "approval_state": "not_requested",
            })
    # Strategic proposal order is separate from verified readiness.
    rows.sort(key=lambda row: (
        -(row["priority"] if row["priority"] is not None else -1),
        -int(row["head_ci_status"] == "success_at_head"),
        -(row["activity_score"] or 0),
        row["repo"],
    ))
    local_only = []
    for state in local.get("projects_to_review", []):
        local_id = state.get("local_project")
        if local_id is None:
            continue
        key = "local:" + local_id
        proposal = priorities.get(key)
        local_only.append({
            "local_project": local_id, "visibility": "private",
            "priority": proposal["priority"] if proposal else None,
            "priority_basis": proposal["basis"] if proposal else "unset",
            "rationale": proposal["rationale"] if proposal else None,
            "local_state": state.get("review", "not_checked"),
            "no_github_quality_equivalence": True,
            "publishable": False, "approval_state": "not_requested",
        })
    local_only.sort(key=lambda row: (-(row["priority"] if row["priority"] is not None else -1),
                                     row["local_project"]))
    return {
        "schema": 1, "visibility": "private-local",
        "automatic_publication": False,
        "priority_proposals_are_not_owner_approval": True,
        "not_safe_to_share_publicly": True,
        "ranked_for_private_review": rows,
        "local_only_projects": local_only,
    }


def run() -> dict:
    if os.environ.get("CI") or os.environ.get("GITHUB_ACTIONS"):
        raise RuntimeError("estrategia privada prohibida en CI")
    result = build(
        secure_read(PRIVATE_OUT), secure_read(PRIVATE_QUALITY),
        secure_read(LOCAL_REVIEW), secure_read(CONFIG))
    if (PRIVATE_DIR.is_symlink() or OUTPUT.is_symlink()
            or OUTPUT.parent.resolve() != PRIVATE_DIR.resolve()):
        raise ValueError("destino local privado inválido")
    fd, tmp = tempfile.mkstemp(prefix=".private-strategy-", dir=PRIVATE_DIR)
    try:
        os.chmod(tmp, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as writer:
            json.dump(result, writer, ensure_ascii=False, indent=2)
        os.replace(tmp, OUTPUT)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return result


if __name__ == "__main__":
    result = run()
    print(f"Propuesta estratégica privada: {len(result['ranked_for_private_review'])} proyectos; "
          "prioridades provisionales, no exportadas ni aprobadas.")
