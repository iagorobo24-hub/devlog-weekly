"""narrativa -> deck. Determinista.

Lee out/summaries.json y templates/deck.md.j2, escribe out/deck.md, y lo
convierte a out/deck.pdf con Marp CLI. Nada de IA aquí: la plantilla es fija,
el texto ya lo puso el modelo en synthesize.py.

Flags:
  --no-pdf   solo genera out/deck.md; no llama a marp (para iterar la
             plantilla sin tener marp-cli instalado)
"""

from __future__ import annotations

import argparse
import json
import logging
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

ROOT = Path(__file__).resolve().parent.parent
SUMMARIES_PATH = ROOT / "out" / "summaries.json"
TEMPLATE_DIR = ROOT / "templates"
TEMPLATE_NAME = "deck.md.j2"
DECK_MD_PATH = ROOT / "out" / "deck.md"
DECK_PDF_PATH = ROOT / "out" / "deck.pdf"

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("render")


def load_summaries() -> dict:
    if not SUMMARIES_PATH.exists():
        log.error("%s no existe; corre synthesize.py primero", SUMMARIES_PATH)
        sys.exit(1)
    return json.loads(SUMMARIES_PATH.read_text(encoding="utf-8"))


def format_date(iso_str: str) -> str:
    return datetime.fromisoformat(iso_str).strftime("%d/%m/%Y")


def render_markdown(summaries: dict) -> str:
    env = Environment(loader=FileSystemLoader(TEMPLATE_DIR), trim_blocks=True, lstrip_blocks=True)
    template = env.get_template(TEMPLATE_NAME)

    repos = summaries["repos"]
    periodo_desde = min((r["since"] for r in repos), default=None)
    periodo_hasta = max((r["until"] for r in repos), default=None)

    return template.render(
        repos=repos,
        periodo_desde=format_date(periodo_desde) if periodo_desde else "",
        periodo_hasta=format_date(periodo_hasta) if periodo_hasta else "",
        generado=format_date(summaries["generated_at"]),
    )


def convert_to_pdf(md_path: Path, pdf_path: Path) -> None:
    marp = shutil.which("marp")
    if marp is None:
        log.error("marp-cli no está instalado (npm install -g @marp-team/marp-cli)")
        sys.exit(1)
    subprocess.run([marp, str(md_path), "--pdf", "--allow-local-files", "-o", str(pdf_path)], check=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--no-pdf", action="store_true", help="Solo genera out/deck.md; no llama a marp.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    summaries = load_summaries()
    markdown = render_markdown(summaries)

    DECK_MD_PATH.parent.mkdir(parents=True, exist_ok=True)
    DECK_MD_PATH.write_text(markdown, encoding="utf-8")
    log.info("escrito %s", DECK_MD_PATH)

    if args.no_pdf:
        return

    convert_to_pdf(DECK_MD_PATH, DECK_PDF_PATH)
    log.info("escrito %s", DECK_PDF_PATH)


if __name__ == "__main__":
    main()
