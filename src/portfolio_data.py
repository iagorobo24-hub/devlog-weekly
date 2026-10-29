"""Editorial portfolio: checked, reproducible source data, never unverified AI prose."""
from __future__ import annotations

import re
import json
from pathlib import Path
from urllib.parse import urlparse

import yaml

ROOT = Path(__file__).resolve().parent.parent
DATA_PATH = ROOT / "content" / "portfolio" / "projects.yml"
ASSETS_ROOT = ROOT / "assets" / "portfolio"

SHA_RE = re.compile(r"^[0-9a-f]{40}$")
REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
IMG_FIELDS = ("hero_image", "detail_image", "second_image")
MAX_TEXT_LENGTH = 250
REQUIRED_TEXTS = (
    "title", "category", "statement", "pitch", "problem", "solution",
    "status", "status_detail", "repo_url", "status_source",
)


def require_text(value: object, label: str, limit: int = MAX_TEXT_LENGTH) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError(f"{label}: texto ausente o demasiado largo")
    if "<" in value or ">" in value:
        raise ValueError(f"{label}: no se permite HTML en datos editoriales")
    return value.strip()


def valid_link(value: str, repo: str, revision: str, *, external: bool = False) -> bool:
    uri = urlparse(value)
    if uri.scheme != "https" or not uri.netloc or uri.username or uri.password or uri.query or uri.fragment:
        return False
    if external:
        return uri.netloc in {"iagorobo24-hub.github.io", "proyecto-pfc-iago-duran.vercel.app"}
    if uri.netloc != "github.com":
        return False
    root = "/" + repo
    return uri.path == root or uri.path.startswith(root + "/blob/" + revision + "/") or uri.path.startswith(root + "/tree/" + revision + "/") or uri.path.startswith(root + "/actions/runs/")


def load_portfolio(path: Path = DATA_PATH) -> dict:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("version") != 2:
        raise ValueError("schema de portfolio desconocido")
    require_text(data.get("edition"), "edition")
    require_text(data.get("author"), "author", 100)
    require_text(data.get("title"), "title")
    require_text(data.get("subtitle"), "subtitle")
    require_text(data.get("editorial_note"), "editorial_note", 400)
    projects = data.get("projects")
    if not isinstance(projects, list) or not projects:
        raise ValueError("el portfolio necesita al menos un proyecto")
    seen = set()
    for project in projects:
        repo = project.get("repo", "")
        revision = project.get("revision", "")
        if not REPO_RE.fullmatch(repo) or not SHA_RE.fullmatch(revision):
            raise ValueError("identidad o SHA de repositorio no válido")
        if repo in seen:
            raise ValueError(f"proyecto duplicado: {repo}")
        seen.add(repo)
        for field in REQUIRED_TEXTS:
            require_text(project.get(field), f"{repo}.{field}", 350 if field == "status_detail" else 250)
        if not valid_link(project["repo_url"], repo, revision) or not valid_link(project["status_source"], repo, revision):
            raise ValueError(f"{repo}: enlace principal no verificable")
        demo = project.get("demo_url")
        if demo and not valid_link(demo, repo, revision, external=True):
            raise ValueError(f"{repo}: demo no autorizada")
        for field in ("stack", "capabilities", "limitations", "next_steps", "evidence"):
            if not isinstance(project.get(field), list) or not project[field]:
                raise ValueError(f"{repo}: lista vacía de {field}")
        for field in ("capabilities", "limitations", "next_steps", "stack"):
            for item in project[field]:
                require_text(item, f"{repo}.{field}", 170)
        for item in project["evidence"]:
            require_text(item.get("label"), "evidence.label", 75)
            require_text(item.get("description"), "evidence.description", 220)
            if not valid_link(item.get("url", ""), repo, revision):
                raise ValueError(f"{repo}: evidencia sin procedencia válida")
        for proof in project.get("proof_points", []):
            require_text(proof.get("label"), f"{repo}.proof.label", 70)
            require_text(proof.get("detail"), f"{repo}.proof.detail", 200)
            if not valid_link(proof.get("source", ""), repo, revision):
                raise ValueError(f"{repo}: prueba sin enlace versionado")
        walkthroughs = project.get("walkthroughs")
        if not isinstance(walkthroughs, list) or not 1 <= len(walkthroughs) <= 3:
            raise ValueError(f"{repo}: se exige un recorrido concreto (máximo tres)")
        for walk in walkthroughs:
            for field in ("title", "state", "description"):
                require_text(walk.get(field), f"{repo}.walk.{field}", 250)
            if walk.get("image_field") not in IMG_FIELDS or not project.get(walk["image_field"]):
                raise ValueError(f"{repo}: recorrido sin captura validable")
            if not valid_link(walk.get("source", ""), repo, revision):
                raise ValueError(f"{repo}: recorrido sin evidencia versionada")
            steps = walk.get("steps")
            if not isinstance(steps, list) or len(steps) != 3:
                raise ValueError(f"{repo}: recorrido exige tres pasos")
            for step in steps:
                require_text(step, f"{repo}.walk.step", 170)
        assets = project.get("asset_sources", {})
        for field in IMG_FIELDS:
            name = project.get(field)
            if not name:
                continue
            if not isinstance(name, str) or not name.startswith("assets/portfolio/"):
                raise ValueError(f"{repo}: imagen fuera de carpeta autorizada")
            image_path = (ROOT / name).resolve()
            if not image_path.is_relative_to(ASSETS_ROOT.resolve()) or not image_path.is_file():
                raise ValueError(f"{repo}: imagen no encontrada: {name}")
            if image_path.stat().st_size > 3_000_000:
                raise ValueError(f"{repo}: imagen superior al límite")
            if image_path.suffix.lower() not in {".png", ".jpg", ".svg"}:
                raise ValueError(f"{repo}: tipo de imagen inválido")
            if not valid_link(assets.get(field, ""), repo, revision):
                raise ValueError(f"{repo}: falta procedencia de la imagen {field}")
            require_text(project.get(field.replace("_image", "_caption")), field + ".caption")
    return data


def recent_activity(projects: list[dict], path: Path = ROOT / "out" / "summaries.json") -> list[dict]:
    """Optional weekly metadata: only real GitHub URLs; no LLM prose or claims."""
    if not path.is_file():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        raise ValueError("summaries.json inválido para actividad reciente") from exc
    allow = {project["repo"]: project for project in projects}
    results = []
    for repo in payload.get("repos", []):
        name = repo.get("name")
        if name not in allow or repo.get("trivial", True):
            continue
        base = "https://github.com/" + name
        events = []
        for source in repo.get("verified_sources", []):
            kind = source.get("kind")
            url = source.get("url", "")
            pattern = (
                re.escape(base) + r"/commit/[0-9a-fA-F]{7,64}"
                if kind == "commit" else
                re.escape(base) + r"/pull/[0-9]+"
                if kind == "pr" else
                re.escape(base) + r"/issues/[0-9]+"
                if kind == "issue" else ""
            )
            if not pattern or not re.fullmatch(pattern, url):
                continue
            title = source.get("title", "")
            if not isinstance(title, str) or not title.strip():
                continue
            events.append({
                "kind": kind, "title": " ".join(title.split())[:105],
                "label": str(source.get("id", ""))[:24],
                "date": str(source.get("date") or "")[:10],
                "url": url,
            })
            if len(events) == 3:
                break
        if events:
            results.append({"repo": name, "title": allow[name]["title"], "events": events})
    return results


def revision_alerts(projects: list[dict], path: Path = ROOT / "out" / "collected.json") -> list[dict]:
    """Warn about collected commits beyond the curated source snapshot.

    Never auto-promote a claim or rewrite curated image/verification revisions.
    """
    if not path.is_file():
        return []
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError("collected.json no válido") from exc
    indexed = {p["repo"]: p for p in projects}
    changes = []
    for item in document.get("repos", []):
        repo = item.get("name")
        if repo not in indexed:
            continue
        for commit in item.get("commits", [])[:1]:
            sha = commit.get("sha", "")
            if isinstance(sha, str) and SHA_RE.fullmatch(sha) and sha != indexed[repo]["revision"]:
                changes.append({
                    "repo": repo, "title": indexed[repo]["title"],
                    "snapshot": indexed[repo]["revision"][:10],
                    "observed": sha[:10],
                    "url": "https://github.com/" + repo + "/commit/" + sha,
                })
    return changes
