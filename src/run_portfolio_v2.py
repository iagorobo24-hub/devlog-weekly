"""Production bridge for editorial V2. Expose legacy names only after validation."""
from __future__ import annotations

import argparse
import hashlib
import logging
import os
import shutil

try:
    from src.portfolio_data import ROOT, load_portfolio
    from src import master_release_provenance as master_proof
    from src.render_portfolio_v2 import PDF_PATH, MANIFEST_PATH, MD_PATH, THEME, write_preview
    from src.render_video_v2 import VIDEO_PATH, SRT_PATH, render
    from src.quality_gate import check_pdf
    from src.render_master import had_showcase_activity_this_week
except ModuleNotFoundError:
    from portfolio_data import ROOT, load_portfolio
    import master_release_provenance as master_proof
    from render_portfolio_v2 import PDF_PATH, MANIFEST_PATH, MD_PATH, THEME, write_preview
    from render_video_v2 import VIDEO_PATH, SRT_PATH, render
    from quality_gate import check_pdf
    from render_master import had_showcase_activity_this_week

LOG = logging.getLogger("portfolio-v2-release")
PUBLIC_PDF = ROOT / "out" / "portfolio.pdf"
PUBLIC_MP4 = ROOT / "out" / "portfolio.mp4"
PUBLIC_SRT = ROOT / "out" / "portfolio.srt"


def should_build(force: bool = False) -> bool:
    if force:
        return True
    names = {p["repo"] for p in load_portfolio()["projects"]}
    return had_showcase_activity_this_week(names)


def prepare(*, force: bool = False, smoke: bool = False) -> bool:
    # No prior run may authorize a later skipped or failed release.
    receipt = master_proof.RECEIPT_PATH
    if receipt.is_symlink():
        raise ValueError("recibo de publicación master inseguro")
    receipt.unlink(missing_ok=True)
    if not should_build(force):
        LOG.info("Sin cambios en proyectos destacados; no regenerar portfolio")
        return False
    for existing in (PUBLIC_PDF, PUBLIC_MP4, PUBLIC_SRT):
        if existing.is_file():
            raise RuntimeError(f"salida final preexistente: {existing}")
    source_inputs = (ROOT / "content" / "portfolio" / "projects.yml", THEME)
    if any(not src.is_file() or src.is_symlink() for src in source_inputs):
        raise ValueError("fuente editorial master ausente o insegura")
    frozen_sources = {src: src.read_bytes() for src in source_inputs}
    write_preview(pdf=True)
    report = check_pdf(PDF_PATH, MANIFEST_PATH)
    LOG.info("Control PDF previo a publicación: %s", report)
    report_video = render(smoke=smoke)
    if not VIDEO_PATH.is_file() or VIDEO_PATH.stat().st_size < 30_000:
        raise ValueError("vídeo V2 inválido")
    if not SRT_PATH.is_file() or SRT_PATH.stat().st_size == 0:
        raise ValueError("subtítulos V2 no generados")
    LOG.info("Control vídeo previo a publicación: %s", report_video)
    for source, target in ((PDF_PATH, PUBLIC_PDF), (VIDEO_PATH, PUBLIC_MP4), (SRT_PATH, PUBLIC_SRT)):
        temporary = target.with_suffix(target.suffix + ".tmp")
        shutil.copy2(source, temporary)
        # The uploaded/exported copy must be the exact bytes which passed the PDF gate.
        if hashlib.sha256(source.read_bytes()).digest() != hashlib.sha256(temporary.read_bytes()).digest():
            raise ValueError(f"copia con contenido modificado: {source.name}")
        os.replace(temporary, target)
    check_pdf(PUBLIC_PDF, MANIFEST_PATH)
    if any(src.read_bytes() != expected for src, expected in frozen_sources.items()):
        raise RuntimeError("fuente editorial master alterada durante la generación")
    master_proof.write_receipt(
        receipt=receipt, projects=ROOT / "content" / "portfolio" / "projects.yml",
        manifest=MANIFEST_PATH, markdown=MD_PATH, theme=THEME,
        pdf=PUBLIC_PDF, video=PUBLIC_MP4, subtitles=PUBLIC_SRT,
        run_id=os.environ.get("GITHUB_RUN_ID"))
    LOG.info("Portfolio V2 preparado: PDF + MP4 + SRT con recibo verificable")
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--smoke-tone", action="store_true", help="Sólo pruebas aisladas")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    prepare(force=args.force, smoke=args.smoke_tone)
