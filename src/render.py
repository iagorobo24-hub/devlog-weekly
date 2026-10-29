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
        return [], inactive, active

    pages.append({"heading": "Resumen de actividad", "subtitle": "Cambios registrados por GitHub, no éxitos de despliegue",
                  "lines": [
                      f"**{one_line(r['name'].split('/')[-1])}:** "
                      f"{int(r.get('activity_counts', {}).get('commits', 0))} commits; "
                      f"{int(r.get('activity_counts', {}).get('prs', 0))} PRs; "
                      f"{int(r.get('activity_counts', {}).get('issues', 0))} issues."
                      for r in active
                  ]})
    def weighted_lines(lines: list[str]) -> int:
        return sum(max(1, math.ceil(len(line) / 78)) for line in lines)

    for repo in active:
        name = one_line(repo["name"].split("/")[-1])
        pitch = one_line(repo.get("pitch") or "")
        chunks = paginated_bullets(repo.get("avances", []), max_units=6)
        first = ["### " + one_line(repo["titular"])] + (chunks[0] if chunks else [])
        section = {"heading": name, "subtitle": pitch, "lines": first}
        pages.append(section)
        for ix, part in enumerate(chunks[1:], start=2):
            pages.append({"heading": name + " · avances " + str(ix),
                          "subtitle": "", "lines": part})

        state = one_line(repo.get("estado", ""))
        if state:
            for ix, part in enumerate(paginated_bullets([state], max_units=5), start=1):
                target = pages[-1]["lines"]
                if weighted_lines(target + part) <= 8:
                    target.extend(["**Estado:**"] + part)
                else:
                    pages.append({"heading": name + " · estado " + str(ix),
                                  "subtitle": "", "lines": part})

        evidence = repo.get("verified_sources", [])
        if evidence:
            links = []
            for item in evidence[:5]:
                url = item["url"]
                if not re.fullmatch(r"https://github[.]com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/(?:commit/[0-9a-fA-F]+|pull/[0-9]+|issues/[0-9]+)", url):
                    raise ValueError("fuente de GitHub inválida")
                label = one_line(item["id"])
                title = one_line(item.get("title", ""))[:105]
                day = str(item.get("date") or "")[:10]
                links.append(f"• [{label}]({url}) · {day} · {title}")
            if len(evidence) > 5:
                links.append(f"**Y {len(evidence) - 5} eventos más** en GitHub.")
            # Short evidence fits on the existing project page; otherwise
            # use dedicated, pagination-safe evidence pages.
            if len(links) <= 2 and weighted_lines(pages[-1]["lines"] + links) <= 8:
                pages[-1]["lines"].extend(["**Evidencias:**"] + links)
            else:
                for ix in range(0, len(links), 3):
                    pages.append({"heading": name + " · evidencias " + str(1 + ix // 3),
                                  "subtitle": "Referencias verificables (selección)",
                                  "lines": links[ix:ix + 3]})
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
