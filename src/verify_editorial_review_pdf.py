"""Strict checks for V4 editorial source and rendered PDF; never publishes."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "out"
MD = OUT / "portfolio-editorial-closure-v4.md"
MANIFEST = OUT / "portfolio-editorial-closure-v4-manifest.json"
PDF = OUT / "portfolio-editorial-closure-v4.pdf"
QA = OUT / "portfolio-editorial-closure-v4-pdf-qa.json"

KEYWORDS = (
    ("SELECCIÓN EDITORIAL",),
    ("TIA Portal RocaRoibas", "PFC Tools", "GuiaIA"),
    ("TIA Portal RocaRoibas", "44 scripts"),
    ("PFC Tools", "siete"),
    ("GuiaIA", "Cuatro herramientas"),
    ("Awesome TIA Portal",),
    ("ATM10", "6.462"),
    ("AUTOMATON",),
    ("PUBLICACIÓN",),
)
REPO = re.compile(r"^iagorobo24-hub/[A-Za-z0-9_.-]+$")
PINNED = re.compile(r"^/iagorobo24-hub/[A-Za-z0-9_.-]+/blob/[0-9a-f]{40}/[A-Za-z0-9_./-]+$")
CI_RUN = re.compile(r"^/iagorobo24-hub/[A-Za-z0-9_.-]+/actions/runs/[0-9]+$")
CI_STATES = {"success_at_head", "failure_or_cancelled", "unknown",
             "pending", "inconclusive", "unavailable"}
ANCHOR = re.compile(r'<a\b[^>]*\bhref="([^"]+)"', re.IGNORECASE)


def verified_link(url: str, expected_repo: str) -> bool:
    """Only canonical GitHub evidence for the owning case slide is allowed."""
    parsed = urlparse(url)
    if (parsed.scheme != "https" or parsed.netloc != "github.com"
            or parsed.query or parsed.fragment or not expected_repo
            or not parsed.path.startswith("/" + expected_repo + "/")
            or any(x in (".", "..") for x in parsed.path.split("/"))):
        return False
    return bool(PINNED.fullmatch(parsed.path) or CI_RUN.fullmatch(parsed.path))


def validate_source(md: str, manifest: dict) -> dict:
    if (not isinstance(manifest, dict) or manifest.get("schema") != 1
            or manifest.get("visibility") != "public"
            or manifest.get("selection_status") != "frozen_editorial_scope_not_release_approval"
            or manifest.get("curated_portfolio_unchanged") is not True
            or manifest.get("publication_approved") is not False
            or manifest.get("automatic_publication") is not False):
        raise ValueError("Origen editorial no autorizado")
    buckets = [manifest.get(k) for k in ("main_cases", "supporting_cases", "excluded_cases")]
    if any(not isinstance(bucket, list) for bucket in buckets) or [len(x) for x in buckets] != [3, 2, 1]:
        raise ValueError("Composición editorial incorrecta")
    names = [r for bucket in buckets for r in bucket]
    if len(set(names)) != 6 or any(not isinstance(n, str) or not REPO.fullmatch(n) for n in names):
        raise ValueError("Repositorio privado o duplicado")
    observed = manifest.get("observed_ci_by_repo")
    expected = names[:5]
    if (manifest.get("ci_evidence_synced") is not True
            or not isinstance(manifest.get("evidence_report_sha256"), str)
            or re.fullmatch(r"[0-9a-f]{64}", manifest["evidence_report_sha256"]) is None
            or not isinstance(observed, dict) or set(observed) != set(expected)
            or any(status not in CI_STATES for status in observed.values())):
        raise ValueError("Informe PDF sin CI reconciliada en los cinco casos")
    if not isinstance(md, str) or len(md) > 120000:
        raise ValueError("Markdown inválido")
    sha = hashlib.sha256(md.encode("utf-8")).hexdigest()
    if sha != manifest.get("markdown_sha256"):
        raise ValueError("SHA256 del origen editorial no coincide")
    if (manifest.get("slide_count") != 9
            or md.count("<!-- _class: pf-closure-") != 9
            or md.count("BORRADOR INTERNO · NO PUBLICAR") != 9
            or not md.startswith("---\nmarp: true\n")
            or "theme: portfolio-v2" not in md[:200]):
        raise ValueError("Markdown de 9 diapositivas incompleto")
    if any(term not in md for group in KEYWORDS for term in group):
        raise ValueError("Falta contenido editorial esperado")
    # Capture every declared source link, keeping duplicate references
    # intentional. The PDF must render exactly this multiset per page.
    slides = md.split("<!-- _class: pf-closure-")[1:]
    if len(slides) != 9:
        raise ValueError("No se pueden atribuir las diapositivas a sus fuentes")
    expected_links = []
    for i, slide in enumerate(slides):
        repo = names[i - 2] if 2 <= i <= 6 else None
        links = ANCHOR.findall(slide)
        if any(not verified_link(url, repo) for url in links):
            raise ValueError(f"Página {i + 1}: enlace ajeno, no canónico o no fijado")
        expected_links.append(links)
    return {"sha256": sha, "pages": 9, "projects": names,
            "expected_page_links": expected_links}


def normalize_metadata(path: Path) -> None:
    """Set professional PDF metadata without changing visual content."""
    import pymupdf
    if not path.is_file() or path.is_symlink():
        raise ValueError("PDF for metadata update is missing")
    doc = pymupdf.open(path)
    try:
        metadata = dict(doc.metadata)
        metadata.update({
            "title": "Portfolio Maestro V4 | Revisión editorial",
            "subject": "Selección pública revisada; no autorizada para publicación",
            "creator": "Devlog Weekly · Marp",
            "keywords": "portfolio, revisión editorial, borrador interno, no publicar",
        })
        doc.set_metadata(metadata)
        doc.saveIncr()
    finally:
        doc.close()


def validate_pdf(path: Path, source: dict) -> dict:
    import pymupdf
    if not path.is_file() or path.is_symlink() or path.stat().st_size < 5000:
        raise ValueError("PDF no existe o inválido")
    expected = source.get("expected_page_links")
    if not isinstance(expected, list) or len(expected) != 9 or any(
            not isinstance(x, list) for x in expected):
        raise ValueError("No hay inventario de enlaces por diapositiva")
    doc = pymupdf.open(path)
    summaries = []
    links = 0
    try:
        if doc.is_encrypted or len(doc) != 9:
            raise ValueError("Número de páginas incorrecto")
        if doc.metadata.get("title") != "Portfolio Maestro V4 | Revisión editorial":
            raise ValueError("Título PDF temporal o sin normalizar")
        for index, page in enumerate(doc):
            rect = page.rect
            if rect.width < 500 or rect.height < 280 or abs(rect.width / rect.height - 16 / 9) > 0.03:
                raise ValueError(f"Página {index+1}: dimensiones incorrectas")
            text = page.get_text("text")
            if not text or len(text) < 145:
                raise ValueError(f"Página {index+1}: texto incompleto")
            # PDF extraction splits text across line boundaries; normalize
            # whitespace without weakening the per-page content requirements.
            normalized = " ".join(text.casefold().split())
            if any(" ".join(term.casefold().split()) not in normalized
                   for term in KEYWORDS[index]):
                raise ValueError(f"Página {index+1}: falta contenido clave")
            if "BORRADOR INTERNO" not in text or "NO PUBLICAR" not in text:
                raise ValueError(f"Página {index+1}: falta advertencia")
            urls = []
            for link in page.get_links():
                url = link.get("uri")
                if not url:
                    continue
                repo = source["projects"][index - 2] if 2 <= index <= 6 else None
                if not verified_link(url, repo):
                    raise ValueError(f"Página {index+1}: URL ajena o no versionada")
                urls.append(url)
            if Counter(urls) != Counter(expected[index]):
                raise ValueError(f"Página {index+1}: enlaces PDF distintos del original")
            # In the case-study slides evidence links are mandatory; if
            # markup is clipped, Marp may silently omit the entire link.
            required_links = 2 if index in (2, 3, 4) else (1 if index in (5, 6) else 0)
            if len(urls) < required_links:
                raise ValueError(f"Página {index+1}: evidencia recortada o no enlazada")
            links += len(urls)
            summaries.append({"page": index+1, "chars": len(text),
                              "pinned_links": len(urls),
                              "width": round(rect.width, 1),
                              "height": round(rect.height, 1)})
    finally:
        doc.close()
    if links < 7:
        raise ValueError("PDF sin suficientes enlaces versionados")
    return {"schema": 1, "visibility": "public", "review_only": True,
            "publication_approved": False, "automatic_publication": False,
            "automated_qa_passed": True, "visual_review_completed": False,
            "source_sha256": source["sha256"],
            "pdf_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "pages": summaries, "total_pinned_links": links,
            "generated_at": datetime.now(timezone.utc).isoformat()}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--preflight", action="store_true")
    p.add_argument("--fix-metadata", action="store_true")
    args = p.parse_args()
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    source = validate_source(MD.read_text(encoding="utf-8"), manifest)
    if args.preflight:
        print("V4 source validated:", source["sha256"][:16])
        return
    if args.fix_metadata:
        normalize_metadata(PDF)
        print("Professional PDF metadata set")
        return
    result = validate_pdf(PDF, source)
    if QA.is_symlink() or QA.parent.resolve() != OUT.resolve():
        raise ValueError("QA destination is unsafe")
    QA.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("PDF QA passed:", len(result["pages"]), "pages,", result["total_pinned_links"], "pinned links")


if __name__ == "__main__":
    main()
