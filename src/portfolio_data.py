"""Editorial portfolio: checked, reproducible source data, never unverified AI prose."""
from __future__ import annotations

import re
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
