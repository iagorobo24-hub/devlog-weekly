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
import html
import math
import re
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
THEME_PATH = ROOT / "templates" / "theme.css"
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


def one_line(value: object) -> str:
    # The LLM and GitHub commit titles are untrusted Markdown/HTML inputs.
    text = " ".join(str(value or "").replace(chr(92) + "n", " ").split())
    return html.escape(text).replace("|", "/")


def split_long(text: object, limit: int = 160) -> list[str]:
    words = one_line(text).split()
    if not words:
        return []
    chunks: list[str] = []
    part = ""
    for word in words:
        if part and len(part) + len(word) + 1 > limit:
            chunks.append(part)
            part = word
        else:
            part = (part + " " + word).strip()
    if part:
        chunks.append(part)
    return chunks


def paginated_bullets(bullets: list[str], max_units: int = 6) -> list[list[str]]:
    """Paginate *all* text; no truncation, with a margin for line wrapping."""
    items: list[str] = []
    for raw in bullets:
        for index, text in enumerate(split_long(raw, 145)):
            items.append(("• " if index == 0 else "↳ ") + text)
    pages: list[list[str]] = []
    current: list[str] = []
    units = 0
    for item in items:
        cost = max(1, math.ceil(len(item) / 72))
        if current and units + cost > max_units:
            pages.append(current)
            current = []
            units = 0
        current.append(item)
        units += cost
    if current:
        pages.append(current)
    return pages


def build_sections(summaries: dict) -> tuple[list[dict], list[str], list[dict]]:
    repos = summaries["repos"]
    active = [r for r in repos if not r.get("trivial", True)]
    inactive = [r["name"].split("/")[-1] for r in repos if r.get("trivial", True)]
    pages = []
    if not active:
        return [{"heading": "Sin cambios verificados",
                 "subtitle": "Ninguno de los proyectos tuvo nuevos eventos de GitHub.",
                 "lines": ["No se ha llamado a la IA ni hay avances nuevos que presentar."]}], inactive, active

    pages.append({"heading": "Resumen de actividad", "subtitle": "Cambios registrados por GitHub, no éxitos de despliegue",
                  "lines": [
                      f"**{one_line(r['name'].split('/')[-1])}:** "
                      f"{int(r.get('activity_counts', {}).get('commits', 0))} commits; "
                      f"{int(r.get('activity_counts', {}).get('prs', 0))} PRs; "
                      f"{int(r.get('activity_counts', {}).get('issues', 0))} issues."
                      for r in active
                  ]})
    for repo in active:
        name = one_line(repo["name"].split("/")[-1])
        pages.append({"heading": name, "subtitle": one_line(repo.get("pitch") or ""),
                      "lines": ["### " + one_line(repo["titular"])]})
        for ix, part in enumerate(paginated_bullets(repo.get("avances", [])), start=1):
            pages.append({"heading": name + " · avances " + str(ix),
                          "subtitle": "", "lines": part})
        state = split_long(repo.get("estado", ""), 160)
        for ix, part in enumerate(paginated_bullets(state), start=1):
            pages.append({"heading": name + " · estado " + str(ix),
                          "subtitle": "", "lines": part})
        evidence = repo.get("verified_sources", [])
        if evidence:
            links = []
            for item in evidence[:5]:
                # URLs are provided by the verified-source builder, not the model.
                url = item["url"]
                if not re.fullmatch(r"https://github[.]com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/(?:commit/[0-9a-fA-F]+|pull/[0-9]+|issues/[0-9]+)", url):
                    raise ValueError("fuente de GitHub inválida")
                label = one_line(item["id"])
                title = one_line(item.get("title", ""))[:105]
                day = str(item.get("date") or "")[:10]
                links.append(f"• [{label}]({url}) · {day} · {title}")
            if len(evidence) > 5:
                links.append(f"**Y {len(evidence) - 5} eventos adicionales** en el historial de GitHub.")
            pages.append({"heading": name + " · evidencias", "subtitle": "Referencias verificables (selección)",
                          "lines": links})
    return pages, inactive, active


def render_markdown(summaries: dict) -> str:
    env = Environment(loader=FileSystemLoader(TEMPLATE_DIR), trim_blocks=True, lstrip_blocks=True)
    template = env.get_template(TEMPLATE_NAME)
    repos = summaries["repos"]
    since = min((r["since"] for r in repos), default="")
    until = max((r["until"] for r in repos), default="")
    pages, inactive, active = build_sections(summaries)
    return template.render(
        sections=pages, inactive=inactive, active_count=len(active), total_count=len(repos),
        periodo_desde=format_date(since) if since else "",
        periodo_hasta=format_date(until) if until else "",
        generado=format_date(summaries["generated_at"]),
    )


def convert_to_pdf(md_path: Path, pdf_path: Path) -> None:
    marp = shutil.which("marp")
    if marp is None:
        log.error("marp-cli no está instalado (npm install -g @marp-team/marp-cli)")
        sys.exit(1)
    subprocess.run(
        [marp, str(md_path), "--pdf", "--no-stdin", "--allow-local-files", "--theme-set", str(THEME_PATH), "-o", str(pdf_path)],
        check=True,
    )


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
