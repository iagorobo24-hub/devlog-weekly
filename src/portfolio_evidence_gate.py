"""Evidence inventory of editorial project claims and visual files.

GitHub file existence and a green CI run are structural observations only.
No GitHub image is automatically authorized, and no external project is
modified. Stable selection is separate from its weekly ranking.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import tempfile

from github import Auth, Github
from github.GithubException import GithubException
import yaml

from src.portfolio_data import ROOT, load_portfolio
from src.project_quality import assess_head_ci
from src.select_projects import credentials

SOURCE = ROOT / "content/portfolio/evidence-inventory-public.yml"
SELECTION = ROOT / "content/portfolio/editorial-selection-public.yml"
RELEASE = ROOT / "out/portfolio-release-review.json"
OUTPUT = ROOT / "out/portfolio-evidence-public.json"
MARKDOWN = ROOT / "out/portfolio-evidence-public.md"
NAME_RE = re.compile(r"^iagorobo24-hub/[a-zA-Z0-9_.-]+$")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
PATH_RE = re.compile(r"^[a-zA-Z0-9_.-]+(?:/[a-zA-Z0-9_.-]+)*$")
MEDIA = {".svg", ".png", ".jpg", ".jpeg", ".webp"}
KINDS = {"conceptual_diagram", "conceptual_illustration", "e2e_repository_image",
         "repository_runtime_claimed_image", "screenshot_previous_candidate"}
MAX_VISUALS = 4
UNKNOWN = {401, 403, 429, 500, 502, 503, 504}


def path_ok(path: object) -> bool:
    return (isinstance(path, str) and PATH_RE.fullmatch(path) is not None
            and all(x not in (".", "..") for x in path.split("/")))


def validate_inventory(spec: dict, editorial: dict, release: dict,
                       published: dict) -> list[dict]:
    if (not isinstance(spec, dict) or spec.get("version") != 1
            or spec.get("visibility") != "public"
            or spec.get("release_approved") is not False
            or spec.get("allow_publication") is not False
            or spec.get("reports_runtime_verification") is not False
            or spec.get("owner_image_use_approval") is not False):
        raise ValueError("Inventario no autorizado o con publicación implícita")
    if (not isinstance(editorial, dict) or editorial.get("visibility") != "public"
            or editorial.get("status") != "frozen_editorial_scope_not_release_approval"):
        raise ValueError("Selección editorial no fijada")
    if (not isinstance(release, dict) or release.get("visibility") != "public"
            or release.get("automatic_publication") is not False
            or release.get("safe_to_replace_public_portfolio") is not False
            or release.get("private_inputs_accessed") is not False):
        raise ValueError("Informe editorial ajeno o promovido")
    entries = spec.get("projects")
    if not isinstance(entries, list) or len(entries) != 5:
        raise ValueError("Se exige inventario de cinco casos públicos")
    selected = editorial.get("main_cases", []) + editorial.get("supporting_cases", [])
    if (not isinstance(selected, list) or len(selected) != 5
            or {p["repo"] for p in selected} != {p["repo"] for p in entries}):
        raise ValueError("Inventario no coincide con los casos fijados")
    published_sha = {p["repo"]: p["revision"] for p in published["projects"]}
    if published_sha != {p["repo"]: p["pinned_revision"]
                         for p in release.get("current_portfolio", [])}:
        raise ValueError("Revisión no coincide con portfolio publicado")
    candidates = {p["repo"]: p for p in release.get("candidates", [])}
    seen = set()
    for entry in entries:
        repo, rev = entry.get("repo"), entry.get("revision")
        if (not isinstance(repo, str) or not NAME_RE.fullmatch(repo)
                or not isinstance(rev, str) or not SHA_RE.fullmatch(rev)
                or repo in seen):
            raise ValueError("Repositorio privado, duplicado o SHA inválido")
        seen.add(repo)
        frozen = next(p for p in selected if p["repo"] == repo)
        if (rev != frozen.get("revision")
                or entry.get("role") != ("main" if frozen in editorial["main_cases"]
                                         else "supporting")):
            raise ValueError("Snapshot de evidencia no coincide con selección")
        candidate = candidates.get(repo)
        if (candidate and (candidate.get("head") != rev
                           or candidate.get("visibility") != "public"
                           or candidate.get("approved_for_release") is not False)):
            raise ValueError("Preflight público no coincide con inventario")
        if not candidate and published_sha.get(repo) != rev:
            raise ValueError("Proyecto no incluido en auditoría ni cartera vigente")
        claim = entry.get("claim")
        if (not isinstance(claim, dict) or not path_ok(claim.get("source_path"))
                or claim.get("basis") != "documented_by_repository"
                or not isinstance(claim.get("note"), str)
                or not 30 <= len(claim["note"]) <= 260):
            raise ValueError("Afirmación editorial sin fuente o alcance")
        visuals = entry.get("visuals")
        if not isinstance(visuals, list) or not 1 <= len(visuals) <= MAX_VISUALS:
            raise ValueError("Capturas o diagramas fuera de límites")
        paths = set()
        for visual in visuals:
            path = visual.get("path") if isinstance(visual, dict) else None
            if (not path_ok(path) or Path(path).suffix.lower() not in MEDIA
                    or path in paths or visual.get("kind") not in KINDS
                    or visual.get("approved_for_public_use") is not False
                    or visual.get("applies_to_current_release") not in (True, False, "unknown")):
                raise ValueError("Imagen no segura, duplicada o aprobada sin permiso")
            paths.add(path)
        pending = entry.get("missing_validation")
        if (not isinstance(pending, list) or not 2 <= len(pending) <= 5
                or any(not isinstance(x, str) or not 15 <= len(x) <= 250
                       for x in pending)):
            raise ValueError("Faltan límites de validación funcional")
    return entries


def _status(repo, path: str, revision: str) -> dict:
    try:
        result = repo.get_contents(path, ref=revision)
        valid = (not isinstance(result, list) and result.type == "file"
                 and isinstance(result.size, int) and result.size > 0)
        if not valid:
            return {"status": "type_mismatch"}
        return {"status": "present_at_revision", "git_blob_sha": result.sha,
                "bytes": result.size}
    except GithubException as exc:
        if exc.status == 404:
            return {"status": "missing"}
        if exc.status in UNKNOWN:
            return {"status": "unavailable", "github_http_status": exc.status}
        raise


def build(spec: dict, editorial: dict, release: dict, published: dict,
          client, *, now: datetime) -> dict:
    if now.tzinfo is None:
        raise ValueError("Timestamp must be timezone aware")
    entries = validate_inventory(spec, editorial, release, published)
    results = []
    for entry in entries:
        name, revision = entry["repo"], entry["revision"]
        availability = "available"
        try:
            remote = client.get_repo(name)
            if remote.private is not False:
                raise ValueError("Private repository blocked BEFORE reading files or CI")
            branch = remote.default_branch
            head = remote.get_branch(branch).commit.sha
        except GithubException as exc:
            if exc.status not in UNKNOWN:
                raise
            remote = None
            branch = None
            head = None
            availability = "github_unavailable"
        snapshot_current = bool(remote and head == revision)
        ci = {"status": "unknown", "run_count_at_head": 0, "run_url": None}
        if snapshot_current:
            try:
                runs = []
                from itertools import islice
                for run in islice(remote.get_workflow_runs(
                        event="push", branch=branch, head_sha=revision), 25):
                    runs.append({
                        "id": run.id, "head_sha": run.head_sha,
                        "head_branch": run.head_branch, "event": run.event,
                        "created_at": run.created_at.isoformat() if run.created_at else None,
                        "conclusion": run.conclusion,
                        "url": getattr(run, "html_url", None),
                    })
                ci = assess_head_ci(head=revision, branch=branch, runs=runs, now=now)
            except GithubException as exc:
                if exc.status not in UNKNOWN:
                    raise
                ci = {"status": "unavailable", "run_count_at_head": 0, "run_url": None}
        claim = entry["claim"]
        claim_probe = _status(remote, claim["source_path"], revision) if snapshot_current else {
            "status": "revision_outdated" if remote else "unavailable"}
        images = []
        for v in entry["visuals"]:
            state = _status(remote, v["path"], revision) if snapshot_current else {
                "status": "revision_outdated" if remote else "unavailable"}
            images.append({
                "path": v["path"], "kind": v["kind"],
                "source_url": f"https://github.com/{name}/blob/{revision}/{v['path']}",
                **state,
                "visual_content_inspected": False,
                "runtime_or_screen_capture_authenticity_verified": False,
                "image_use_permission_confirmed": False,
                "approved_for_public_use": False,
                "applies_to_current_release": v["applies_to_current_release"],
            })
        blockers = list(entry["missing_validation"])
        if not snapshot_current:
            blockers.insert(0, "Revisión del proyecto no coincide con HEAD o GitHub no está accesible.")
        if ci["status"] == "failure_or_cancelled":
            blockers.insert(0, "La CI de push de la revisión principal está fallida.")
        if ci["status"] not in ("success_at_head", "failure_or_cancelled"):
            blockers.insert(0, "La CI de push del SHA principal no queda confirmada.")
        if claim_probe["status"] != "present_at_revision":
            blockers.insert(0, "La fuente de afirmaciones no ha sido localizada en el commit fijado.")
        if any(v["status"] != "present_at_revision" for v in images):
            blockers.insert(0, "No se han localizado todos los ficheros visuales versionados.")
        blockers.insert(0, "No consta aprobación de uso de capturas ni validación funcional independiente.")
        results.append({
            "repo": name, "revision": revision, "role": entry["role"],
            "visibility": "public", "default_branch": branch,
            "head_matches_revision": snapshot_current,
            "availability": availability, "ci": ci,
            "claim": {"source_path": claim["source_path"],
                      "description": claim["note"],
                      "basis": claim["basis"], **claim_probe,
                      "semantic_and_runtime_verification": False},
            "visuals": images,
            "blockers": blockers,
            "ready_for_publication": False, "independent_runtime_validated": False,
            "owner_permission_confirmed": False,
        })
    return {
        "schema": 1, "visibility": "public",
        "generated_at": now.isoformat(),
        "source_selection_generated_at": release.get("selection_generated_at"),
        "selection_status": editorial["status"],
        "public_projects_only": True,
        "private_sources_inspected": False,
        "automatic_publication": False,
        "safe_to_replace_public_portfolio": False,
        "all_claims_semantically_verified": False,
        "all_visuals_approved": False,
        "cases": results,
    }


def reconcile_ci_evidence(report: dict, quality: dict) -> dict:
    """Flag contradictory HEAD/CI probes without implying either proves runtime."""
    if (not isinstance(quality, dict) or quality.get("schema") != 1
            or quality.get("visibility") != "public"
            or quality.get("source_selection_generated_at")
            != report.get("source_selection_generated_at")):
        raise ValueError("Quality and evidence reports have different public snapshots")
    indexed = {}
    for item in quality.get("records", []):
        if not isinstance(item, dict) or item.get("visibility") != "public":
            raise ValueError("Private quality data cannot be reconciled")
        repo = item.get("repo")
        if not isinstance(repo, str) or not NAME_RE.fullmatch(repo) or repo in indexed:
            raise ValueError("Quality data has invalid or duplicate identity")
        indexed[repo] = item
    differences = []
    for item in report["cases"]:
        other = indexed.get(item["repo"])
        if not other:
            continue   # PFC Tools is curated but not in active selector ranking.
        left = other.get("ci", {}).get("status", "unknown")
        right = item["ci"]["status"]
        if other.get("head") == item["revision"] and left != right:
            differences.append({"repo": item["repo"], "quality_ci": left,
                                "evidence_ci": right,
                                "not_runtime_evidence": True})
    report["ci_reports_consistent"] = not bool(differences)
    report["ci_report_disagreements"] = differences
    return report


def render_md(report: dict) -> str:
    rows = [
        "# Portfolio Maestro — auditoría de evidencias y capturas (no publicar)",
        "",
        "Comprobación estructural de archivos y CI en **SHA de main**. No valida",
        "funcionamiento real, contenido visual, derechos de imagen ni autoriza publicación.",
        "",
        "| Proyecto | Push CI en HEAD | Fuentes | Archivos visuales | Publicable |",
        "|---|---|---|---:|---|",
    ]
    if report.get("ci_report_disagreements"):
        rows.extend(["", "## Inconsistencias de CI entre consultas", ""])
        for item in report["ci_report_disagreements"]:
            rows.append("- " + item["repo"] + ": evaluación " + item["quality_ci"] +
                        " / auditoría exacta " + item["evidence_ci"])
        rows.append("Revisar antes de considerar coherentes las evidencias.")
    for p in report["cases"]:
        found = sum(v["status"] == "present_at_revision" for v in p["visuals"])
        rows.append(f"| {p['repo']} | {p['ci']['status']} | "
                    f"{p['claim']['status']} | {found}/{len(p['visuals'])} | No |")
    for p in report["cases"]:
        rows.extend(["", "## " + p["repo"], "",
                     "CI en rama predeterminada: " + p["ci"]["status"]])
        if p["ci"].get("run_url"):
            rows.append("Ejecución CI exacta: " + p["ci"]["run_url"])
        rows.extend(["", "Fuentes de imagen observadas (existencia, no autenticidad):"])
        for v in p["visuals"]:
            rows.append(f"- [{v['path']}]({v['source_url']}) · {v['kind']} · "
                        f"{v['status']} · autorizado para publicar: **no**")
        rows.extend(["", "### Pendientes contrastables"])
        rows.extend("- " + item for item in p["blockers"])
    rows.extend(["", "## Estado editorial",
                 "",
                 "Cero proyectos aprobados automáticamente. Los proyectos fuera del",
                 "inventario público no se inspeccionaron. El PDF oficial permanece intacto.",
                 ""])
    return "\n".join(rows)


def run(*, client=None) -> dict:
    spec = yaml.safe_load(SOURCE.read_text(encoding="utf-8"))
    editorial = yaml.safe_load(SELECTION.read_text(encoding="utf-8"))
    release = json.loads(RELEASE.read_text(encoding="utf-8"))
    portfolio = load_portfolio()
    if client is None:
        with Github(auth=Auth.Token(credentials()), per_page=100) as gh:
            report = build(spec, editorial, release, portfolio, gh,
                           now=datetime.now(timezone.utc))
    else:
        report = build(spec, editorial, release, portfolio, client,
                       now=datetime.now(timezone.utc))
    quality = json.loads((ROOT / "out/project-quality-public.json").read_text(encoding="utf-8"))
    report = reconcile_ci_evidence(report, quality)
    OUT = ROOT / "out"
    OUT.mkdir(parents=True, exist_ok=True)
    for target, payload in ((OUTPUT, json.dumps(report, ensure_ascii=False, indent=2) + "\n"),
                            (MARKDOWN, render_md(report))):
        if target.is_symlink() or target.parent.resolve() != OUT.resolve():
            raise ValueError("Salida no autorizada")
        fd, name = tempfile.mkstemp(prefix=".evidence-", dir=OUT)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(payload)
            os.replace(name, target)
        finally:
            if os.path.exists(name):
                os.unlink(name)
    return report


if __name__ == "__main__":
    result = run()
    print("Evidencia pública:", len(result["cases"]), "proyectos;",
          sum(len(x["visuals"]) for x in result["cases"]), "archivos visuales;",
          "publicaciones aprobadas:", sum(x["ready_for_publication"] for x in result["cases"]),
          "CI coherente:", result["ci_reports_consistent"])
