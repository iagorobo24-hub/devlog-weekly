"""Reviewable drafts of PUBLIC project profiles. Never render automatically.

The draft revision must match the quality probe's default-branch HEAD. Every
claim links to a pinned source path. CI statements need a separate run URL
bound to that HEAD; a workflow configuration file is NOT execution evidence.
"""
from __future__ import annotations

from pathlib import Path
import json
import re
from urllib.parse import quote

import yaml

try:
    from src.project_selection_core import NAME_RE, SHA_RE
    from src.select_projects import ROOT
except ModuleNotFoundError:
    from project_selection_core import NAME_RE, SHA_RE
    from select_projects import ROOT

CANDIDATES = ROOT / "content" / "portfolio" / "candidates"
REPORT = ROOT / "out" / "candidate-profiles-review.json"

PATH_RE = re.compile(r"^[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*$")
SUPPORTED_KINDS = {"documented", "repository_file", "repository_directory", "ci_at_head"}


def validate(profile: dict, quality: dict | None) -> dict:
    if profile.get("version") != 1 or profile.get("visibility") != "public":
        raise ValueError("perfil candidato no público o versión desconocida")
    if profile.get("editorial_status") != "draft_only":
        raise ValueError("candidato no puede autopromoverse")
    repo, revision = profile.get("repo"), profile.get("revision")
    if not isinstance(repo, str) or not NAME_RE.fullmatch(repo):
        raise ValueError("repo inválido")
    if not isinstance(revision, str) or not SHA_RE.fullmatch(revision):
        raise ValueError("revisión inválida")
    if not isinstance(profile.get("id"), str) or not isinstance(profile.get("title"), str):
        raise ValueError("identidad editorial inválida")
    if not isinstance(profile.get("statements"), list) or not profile["statements"]:
        raise ValueError("candidato sin afirmaciones")
    # A green label alone is not a verifiable CI reference. The quality
    # probe must expose a run at this exact public repository/HEAD.
    quality_matches = (
        isinstance(quality, dict) and quality.get("visibility") == "public"
        and quality.get("repo") == repo and quality.get("head") == revision
    )
    ci = quality.get("ci") if quality_matches else None
    ci = ci if isinstance(ci, dict) else {}
    run_url = ci.get("run_url")
    run_prefix = f"https://github.com/{repo}/actions/runs/"
    supported_ci = (
        ci.get("status") == "success_at_head"
        and type(ci.get("run_count_at_head")) is int
        and ci["run_count_at_head"] > 0
        and isinstance(run_url, str) and run_url.startswith(run_prefix)
        and run_url[len(run_prefix):].isdigit()
        and int(run_url[len(run_prefix):]) > 0
    )
    verified_run_url = run_url if supported_ci else None
    pitch = profile.get("pitch", "")
    limitations = profile.get("limitations", [])
    if (not isinstance(pitch, str) or len(pitch) > 320
            or not isinstance(limitations, list) or len(limitations) > 8
            or any(not isinstance(x, str) or not 10 <= len(x) <= 360
                   for x in limitations)):
        raise ValueError("narrativa pública candidata inválida")
    citations = []
    for claim in profile["statements"]:
        if (not isinstance(claim, dict) or claim.get("kind") not in SUPPORTED_KINDS
                or not isinstance(claim.get("text"), str)
                or not 15 <= len(claim["text"]) <= 500):
            raise ValueError("afirmación inválida")
        source = claim.get("source_path")
        if (not isinstance(source, str) or not PATH_RE.fullmatch(source)
                or any(part in (".", "..") for part in source.split("/"))):
            raise ValueError("fuente no versionada")
        action = "tree" if claim["kind"] == "repository_directory" else "blob"
        is_ci_statement = claim["kind"] == "ci_at_head"
        citations.append({
            "statement": claim["text"], "evidence_kind": claim["kind"],
            "url": f"https://github.com/{repo}/{action}/{revision}/{quote(source, safe='/')}",
            # Pinned file URLs are structural references. Their mere existence
            # does not independently verify what a statement asserts.
            "is_independently_verified": False,
            "source_semantics_not_verified": True,
            "ci_run_url_at_head": verified_run_url if is_ci_statement else None,
            "ci_run_url_is_not_runtime_evidence": True,
        })
    for image in profile.get("images", []):
        if (not isinstance(image, dict) or image.get("kind") != "conceptual_illustration"
                or not isinstance(image.get("path"), str)
                or not PATH_RE.fullmatch(image["path"])
                or any(part in (".", "..") for part in image["path"].split("/"))):
            raise ValueError("imagen conceptual inválida")
    gate = profile.get("publication_gate", {})
    if not isinstance(gate, dict) or any(
            gate.get(k) is not True for k in (
                "independent_functional_check_required",
                "runtime_evidence_required",
                "explicit_editorial_approval_required")):
        raise ValueError("las puertas editoriales no pueden desactivarse")
    reasons = []
    if quality is None or quality.get("repo") != repo or quality.get("visibility") != "public":
        reasons.append("quality_probe_missing")
    else:
        if quality.get("head") != revision:
            reasons.append("editorial_revision_outdated")
        if quality.get("readiness") != "ci_head_passed_tests_exist":
            reasons.append("head_ci_or_test_evidence_incomplete")
    if any(claim["kind"] == "ci_at_head" for claim in profile["statements"]):
        if not supported_ci:
            reasons.append("ci_statement_needs_recheck")
            reasons.append("ci_run_url_missing_or_invalid_at_head")
    return {
        "id": profile["id"], "title": profile["title"], "repo": repo,
        "revision": revision, "draft_only": True, "visibility": "public",
        "pitch": pitch, "limitations": limitations,
        "readiness": "requires_editorial_review",
        "warnings": reasons,
        "sources": citations,
        "illustrations_are_not_runtime_evidence": True,
        "publication_allowed": False,
    }


def build(quality: dict, folder: Path = CANDIDATES) -> dict:
    if quality.get("visibility") != "public":
        raise ValueError("calidad de repos privados no puede generar borradores públicos")
    index = {r["repo"]: r for r in quality.get("records", [])
             if r.get("visibility") == "public"}
    profiles = []
    for path in sorted(folder.glob("*.yml")):
        if path.is_symlink():
            raise ValueError("archivo candidato simbólico")
        profile = yaml.safe_load(path.read_text(encoding="utf-8"))
        profiles.append(validate(profile, index.get(profile.get("repo"))))
    return {"schema": 1, "visibility": "public", "automatic_publication": False,
            "drafts": profiles}


def main() -> None:
    quality = json.loads((ROOT / "out" / "project-quality-public.json").read_text(encoding="utf-8"))
    result = build(quality)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{len(result['drafts'])} fichas candidatas públicas auditadas; "
          "ninguna autorizada para autopublicación.")


if __name__ == "__main__":
    main()
