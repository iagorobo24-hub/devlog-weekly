"""Auditable local provenance for weekly PDF outputs; no network or secrets.

A manifest binds the exact summary JSON, generated Markdown, PDF, Jinja
template and Marp CSS bytes. This detects stale/mixed artifacts, not malicious
editing by someone with write access to both files and the manifest.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
import tempfile

ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = ROOT / "out" / "deck-provenance.json"
MARKDOWN_PATH = ROOT / "out" / "deck.md"
PDF_PATH = ROOT / "out" / "deck.pdf"
SUMMARIES_PATH = ROOT / "out" / "summaries.json"
COLLECTED_PATH = ROOT / "out" / "collected.json"
TEMPLATE_PATH = ROOT / "templates" / "deck.md.j2"
THEME_PATH = ROOT / "templates" / "theme.css"

SOURCES = ("collected", "summary", "markdown", "pdf", "template", "theme")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _read(path: Path) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"artefacto de procedencia ausente o inseguro: {path.name}")
    return path.read_bytes()


def _digest(path: Path) -> str:
    return hashlib.sha256(_read(path)).hexdigest()


def _read_summary(path: Path) -> dict:
    try:
        result = json.loads(_read(path))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError("síntesis no válida para procedencia") from exc
    if not isinstance(result, dict):
        raise ValueError("síntesis no válida para procedencia")
    return result


def verify_collected_source(collected: Path = COLLECTED_PATH,
                            summary: Path = SUMMARIES_PATH) -> str:
    """Verify the actual collection bytes used for synthesis, not only its PDF.

    The state-confirmation preflight also checks configured repositories and
    cursor chronology. This verifies provenance again at render and publish
    boundaries, closing the gap between those separate steps.
    """
    report = _read_summary(summary)
    try:
        collected_bytes = _read(collected)
        original = json.loads(collected_bytes)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError("recolección JSON inválida") from exc
    if not isinstance(original, dict):
        raise ValueError("recolección JSON inválida")
    fingerprint = hashlib.sha256(collected_bytes).hexdigest()
    claimed = report.get("source_collected_sha256")
    if (not isinstance(claimed, str) or not SHA256_RE.fullmatch(claimed)
            or claimed != fingerprint):
        raise ValueError("síntesis desacoplada de los bytes de recolección")
    if (original.get("generated_at") != report.get("generated_at")
            or original.get("github_run_id") != report.get("github_run_id")):
        raise ValueError("síntesis de otro intervalo o GITHUB_RUN_ID")

    def spans(doc: dict) -> dict:
        records = doc.get("repos")
        if not isinstance(records, list) or not records:
            raise ValueError("recolección o síntesis sin repositorios")
        found = {}
        for entry in records:
            if not isinstance(entry, dict):
                raise ValueError("registro de repositorio inválido")
            name = entry.get("name")
            if not isinstance(name, str) or not name or name in found:
                raise ValueError("identidad duplicada o ausente")
            pair = (entry.get("since"), entry.get("until"))
            if not all(isinstance(x, str) and x for x in pair):
                raise ValueError("intervalo de repositorio ausente")
            found[name] = pair
        return found

    if spans(original) != spans(report):
        raise ValueError("síntesis y recolección no cubren los mismos intervalos")
    return fingerprint


def _paths(collected: Path, summary: Path, markdown: Path, pdf: Path,
           template: Path, theme: Path) -> dict[str, Path]:
    return {"collected": collected, "summary": summary, "markdown": markdown,
            "pdf": pdf, "template": template, "theme": theme}


def prepare_manifest(summary: Path = SUMMARIES_PATH,
                     collected: Path = COLLECTED_PATH,
                     markdown: Path = MARKDOWN_PATH, pdf: Path = PDF_PATH,
                     template: Path = TEMPLATE_PATH, theme: Path = THEME_PATH) -> dict:
    result = _read_summary(summary)
    if not isinstance(result.get("generated_at"), str) or not result["generated_at"]:
        raise ValueError("fecha de síntesis ausente")
    if not isinstance(result.get("repos"), list) or not result["repos"]:
        raise ValueError("síntesis sin repositorios")
    run_id = result.get("github_run_id")
    if run_id is not None and (not isinstance(run_id, str) or not run_id.isdecimal()):
        raise ValueError("identificador de ejecución inválido")
    collected_sha = verify_collected_source(collected, summary)
    pdf_bytes = _read(pdf)
    if len(pdf_bytes) < 20 or not pdf_bytes.startswith(b"%PDF-"):
        raise ValueError("PDF semanal inválido")
    return {
        "schema": 1,
        "generated_at": result["generated_at"],
        "github_run_id": run_id,
        "source_collected_sha256": collected_sha,
        "digests": {name: _digest(path) for name, path in
                    _paths(collected, summary, markdown, pdf, template, theme).items()},
    }


def write_manifest(summary: Path = SUMMARIES_PATH,
                   collected: Path = COLLECTED_PATH,
                   markdown: Path = MARKDOWN_PATH, pdf: Path = PDF_PATH,
                   template: Path = TEMPLATE_PATH, theme: Path = THEME_PATH,
                   manifest: Path = MANIFEST_PATH) -> dict:
    if manifest.is_symlink():
        raise ValueError("manifiesto de procedencia es enlace simbólico")
    document = prepare_manifest(summary=summary, collected=collected,
                                markdown=markdown, pdf=pdf,
                                template=template, theme=theme)
    manifest.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", prefix=".deck-provenance-",
            dir=manifest.parent, delete=False) as f:
        pending = Path(f.name)
        json.dump(document, f, ensure_ascii=False, indent=2)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())
    try:
        os.replace(pending, manifest)
    finally:
        pending.unlink(missing_ok=True)
    return document


def verify_manifest(summary: Path = SUMMARIES_PATH,
                    collected: Path = COLLECTED_PATH,
                    markdown: Path = MARKDOWN_PATH, pdf: Path = PDF_PATH,
                    template: Path = TEMPLATE_PATH, theme: Path = THEME_PATH,
                    manifest: Path = MANIFEST_PATH,
                    expected_run_id: str | None = None) -> dict:
    try:
        stored = json.loads(_read(manifest))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError("manifiesto de procedencia inválido") from exc
    actual = prepare_manifest(summary=summary, collected=collected,
                              markdown=markdown, pdf=pdf,
                              template=template, theme=theme)
    if stored != actual:
        raise ValueError("PDF semanal no corresponde a la síntesis/plantilla de esta ejecución")
    if expected_run_id and (actual["github_run_id"] != expected_run_id
                            or not expected_run_id.isdecimal()):
        raise ValueError("PDF semanal asociado a otro GITHUB_RUN_ID")
    return actual
