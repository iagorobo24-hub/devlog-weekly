"""Fail-closed local proof that a V2 master set passed the render/quality path.

This receipt is not a signature or a substitute for the content/visual gate.
It binds exact input, rendered preview and public alias bytes to one run.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import tempfile

ROOT = Path(__file__).resolve().parent.parent
RECEIPT_PATH = ROOT / "out" / "portfolio-master-release-proof.json"
PROJECTS_PATH = ROOT / "content" / "portfolio" / "projects.yml"
RENDER_MANIFEST_PATH = ROOT / "out" / "portfolio-v2-manifest.json"
MARKDOWN_PATH = ROOT / "out" / "portfolio-v2.md"
THEME_PATH = ROOT / "templates" / "portfolio.css"
PUBLIC_PDF = ROOT / "out" / "portfolio.pdf"
PUBLIC_MP4 = ROOT / "out" / "portfolio.mp4"
PUBLIC_SRT = ROOT / "out" / "portfolio.srt"
RUN_ID = re.compile(r"^[0-9]+$")


def _read(path: Path) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"artefacto master ausente o inseguro: {path.name}")
    return path.read_bytes()


def build_receipt(*, projects: Path = PROJECTS_PATH,
                  manifest: Path = RENDER_MANIFEST_PATH,
                  markdown: Path = MARKDOWN_PATH, theme: Path = THEME_PATH,
                  pdf: Path = PUBLIC_PDF, video: Path = PUBLIC_MP4,
                  subtitles: Path = PUBLIC_SRT,
                  run_id: str | None = None) -> dict:
    if run_id is not None and (not isinstance(run_id, str)
                               or not RUN_ID.fullmatch(run_id)):
        raise ValueError("GITHUB_RUN_ID master inválido")
    try:
        structured = json.loads(_read(manifest))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError("manifiesto master inválido") from exc
    if (not isinstance(structured, dict) or structured.get("schema") != 2
            or structured.get("published_to_drive") is not False
            or not isinstance(structured.get("slides"), list)
            or not structured["slides"]
            or not isinstance(structured.get("project_revisions"), dict)
            or not structured["project_revisions"]):
        raise ValueError("manifiesto master sin revisión/diapositivas válidas")

    inputs = {
        "projects": projects, "manifest": manifest,
        "markdown": markdown, "theme": theme,
        "pdf": pdf, "mp4": video, "srt": subtitles,
    }
    payload = {name: _read(path) for name, path in inputs.items()}
    if not payload["pdf"].startswith(b"%PDF-") or len(payload["pdf"]) <= 1000:
        raise ValueError("PDF master inválido")
    if len(payload["mp4"]) < 30_000 or not payload["srt"].strip():
        raise ValueError("vídeo o subtítulos master inválidos")
    return {
        "schema": 1, "github_run_id": run_id,
        "project_revisions": structured["project_revisions"],
        "sha256": {key: hashlib.sha256(value).hexdigest()
                   for key, value in payload.items()},
    }


def write_receipt(*, receipt: Path = RECEIPT_PATH, **sources) -> dict:
    if receipt.is_symlink():
        raise ValueError("recibo de publicación inseguro")
    data = build_receipt(**sources)
    receipt.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", prefix=".master-proof-",
            dir=receipt.parent, delete=False) as file:
        temporary = Path(file.name)
        json.dump(data, file, ensure_ascii=False, indent=2)
        file.write("\n")
        file.flush()
        os.fsync(file.fileno())
    try:
        os.replace(temporary, receipt)
    finally:
        temporary.unlink(missing_ok=True)
    return data


def verify_receipt(*, receipt: Path = RECEIPT_PATH,
                   expected_run_id: str | None = None, **sources) -> dict:
    try:
        stored = json.loads(_read(receipt))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError("recibo de publicación master ilegible") from exc
    actual = build_receipt(run_id=expected_run_id, **sources)
    if stored != actual:
        raise ValueError("portfolio master sin prueba válida de esta ejecución")
    return actual
