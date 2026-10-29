"""Reviewable drafts of PUBLIC project profiles. Never render automatically.

The draft revision must match the quality probe's default-branch HEAD. Every
claim links to a pinned revision; CI statements require an exact HEAD success.
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
        exact_ci = (quality is not None and quality.get("head") == revision
                    and quality.get("ci", {}).get("status") == "success_at_head")
        action = "tree" if claim["kind"] == "repository_directory" else "blob"
        citations.append({
            "statement": claim["text"], "evidence_kind": claim["kind"],
            "url": f"https://github.com/{repo}/{action}/{revision}/{quote(source, safe='/')}",
            "is_independently_verified": bool(exact_ci and claim["kind"] == "ci_at_head"),
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
        if (quality is None or quality.get("head") != revision
                or quality.get("ci", {}).get("status") != "success_at_head"):
            reasons.append("ci_statement_needs_recheck")
    return {
        "id": profile["id"], "title": profile["title"], "repo": repo,
        "revision": revision, "draft_only": True, "visibility": "public",
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
