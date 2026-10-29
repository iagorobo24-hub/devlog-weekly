"""Fail-closed pre-publication checks for the editorial portfolio PDF.

CI adds PyMuPDF on demand. This gate never modifies PDFs or remote state.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib.parse import urlparse

try:
    from src.portfolio_data import load_portfolio
except ModuleNotFoundError:
    from portfolio_data import load_portfolio


def validate_manifest(manifest_path: Path, expected_revisions: dict[str, str]) -> list[dict]:
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if payload.get("schema") != 2 or payload.get("published_to_drive") is not False:
        raise ValueError("manifiesto desconocido o marcado como publicado")
    if payload.get("project_revisions") != expected_revisions:
        raise ValueError("revisiones del manifiesto no coinciden con las fichas")
    slides = payload.get("slides")
    if not isinstance(slides, list) or not slides:
        raise ValueError("manifiesto sin diapositivas")
    if [s.get("index") for s in slides] != list(range(1, len(slides)+1)):
        raise ValueError("índices de diapositivas no consecutivos")
    if any(not isinstance(s.get("narration"), str) or not s["narration"].strip() for s in slides):
        raise ValueError("diapositiva sin guion de voz")
    return slides


def normalized_public_url(url: str) -> tuple[str, str] | None:
    """Treat only one harmless URL-renderer variant as equivalent: trailing '/'."""
    uri = urlparse(url)
    if uri.scheme != "https" or uri.username or uri.password or uri.query or uri.fragment:
        return None
    return uri.netloc.lower(), uri.path.rstrip("/")


def check_pdf(path: Path, manifest: Path) -> dict:
    try:
        import fitz
    except ImportError as exc:
        raise RuntimeError("instalar PyMuPDF para validar los PDF") from exc
    data = load_portfolio()
    expected_revisions = {p["repo"]: p["revision"] for p in data["projects"]}
    slides = validate_manifest(manifest, expected_revisions)
    if not path.is_file() or path.stat().st_size <= 1000:
        raise ValueError("PDF no generado o demasiado pequeño")
    with fitz.open(path) as doc:
        if not doc.is_pdf or doc.is_encrypted or len(doc) != len(slides):
            raise ValueError(f"páginas PDF inesperadas: {len(doc)} != {len(slides)}")
        text_all, links, image_total = [], [], 0
        for i, pg in enumerate(doc):
            words = pg.get_text("words")
            if not words:
                raise ValueError(f"diapositiva {i+1}: no hay texto extraíble")
            for x0, y0, x1, y1, *_ in words:
                # Guard against clipping; very small layout tolerance for PDFs.
                if x0 < -0.5 or y0 < -0.5 or x1 > pg.rect.width + 0.5 or y1 > pg.rect.height + 0.5:
                    raise ValueError(f"diapositiva {i+1}: texto fuera del lienzo")
            text_all.append(pg.get_text())
            image_total += len(pg.get_images())
            links.extend([l.get("uri", "") for l in pg.get_links() if l.get("uri")])
        full_text = "\n".join(text_all)
        for project in data["projects"]:
            if project["title"] not in full_text or project["status"] not in full_text:
                raise ValueError(f"falta la identidad o el estado de {project['repo']}")
            for ev in project["evidence"]:
                if ev["url"] not in links:
                    raise ValueError(f"enlace de evidencia ausente en PDF: {ev['label']}")
        if image_total < len(data["projects"]):
            raise ValueError("PDF sin suficientes capturas reales")
        if len(links) < sum(len(p["evidence"]) for p in data["projects"]):
            raise ValueError("faltan referencias clicables")
        approved_sites = {normalized_public_url(p["demo_url"]) for p in data["projects"]
                          if p.get("demo_url")}
        observed_sites = {normalized_public_url(url) for url in links}
        for project in data["projects"]:
            if project.get("demo_url") and normalized_public_url(project["demo_url"]) not in observed_sites:
                raise ValueError(f"enlace al sitio público ausente: {project['repo']}")
        for url in links:
            host = urlparse(url)
            if host.scheme != "https" or not (host.netloc == "github.com"
                                             or normalized_public_url(url) in approved_sites):
                raise ValueError(f"enlace externo inesperado: {url}")
        return {"status": "pass", "pages": len(doc), "links": len(links),
                "embedded_images": image_total, "projects": len(data["projects"])}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(check_pdf(args.pdf, args.manifest), ensure_ascii=False))
