"""narrativa acumulada -> deck maestro. Determinista, sin IA.

A diferencia de render.py (que muestra la actividad de ESTA semana por
repo), este script arma un portfolio permanente y curado: una slide por
repo con showcase: true, usando su narrativa acumulada de state/narrative/
(la que ya escribe synthesize.py cada semana). No hace ninguna llamada al
modelo — el trabajo de síntesis ya está hecho, esto solo recopila y
maqueta.

Lee config/repos.yml y state/narrative/*.md, escribe out/portfolio.md y lo
convierte a out/portfolio.pdf con Marp.

"Umbral": no tiene sentido resubir un portfolio idéntico cada semana si
ningún proyecto showcase se movió. Por defecto, el script se salta la
generación (sin error, solo un log y sale con éxito) si:
  - ningún repo tiene showcase: true en config/repos.yml, o
  - ninguno de esos showcase tiene narrativa acumulada todavía
    (state/narrative/<repo>.md no existe o está vacío), o
  - ninguno de esos showcase tuvo actividad no-trivial esta semana según
    out/summaries.json (el umbral en sí)

Flags:
  --force    ignora el umbral de actividad; genera igual si hay narrativa
  --no-pdf   solo genera out/portfolio.md; no llama a marp
"""

from __future__ import annotations

import argparse
import json
import logging
import shutil
import subprocess
import sys
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config" / "repos.yml"
NARRATIVE_DIR = ROOT / "state" / "narrative"
SUMMARIES_PATH = ROOT / "out" / "summaries.json"
TEMPLATE_DIR = ROOT / "templates"
TEMPLATE_NAME = "portfolio.md.j2"
THEME_PATH = ROOT / "templates" / "theme.css"
PORTFOLIO_MD_PATH = ROOT / "out" / "portfolio.md"
PORTFOLIO_PDF_PATH = ROOT / "out" / "portfolio.pdf"

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("render_master")


def narrative_path(repo_name: str) -> Path:
    safe_name = repo_name.split("/")[-1].replace("/", "_")
    return NARRATIVE_DIR / f"{safe_name}.md"


def load_showcase_repos() -> list[dict]:
    with CONFIG_PATH.open(encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    return [r for r in cfg.get("repos", []) if r.get("showcase")]


def load_narrative(repo_name: str) -> str:
    path = narrative_path(repo_name)
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8").replace(chr(92) + "n", chr(10)).strip()


def had_showcase_activity_this_week(showcase_names: set[str]) -> bool:
    if not SUMMARIES_PATH.exists():
        return False
    data = json.loads(SUMMARIES_PATH.read_text(encoding="utf-8"))
    return any(r["name"] in showcase_names and not r.get("trivial", True) for r in data["repos"])


def render_markdown(entries: list[dict]) -> str:
    env = Environment(loader=FileSystemLoader(TEMPLATE_DIR), trim_blocks=True, lstrip_blocks=True)
    template = env.get_template(TEMPLATE_NAME)
    return template.render(entries=entries)


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
    parser.add_argument("--force", action="store_true", help="Ignora el umbral de actividad; genera igual si hay narrativa.")
    parser.add_argument("--no-pdf", action="store_true", help="Solo genera out/portfolio.md; no llama a marp.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    showcase_repos = load_showcase_repos()
    if not showcase_repos:
        log.info("ningún repo marcado como showcase: true; no genero deck maestro")
        return

    entries = []
    for repo_cfg in showcase_repos:
        narrativa = load_narrative(repo_cfg["name"])
        if not narrativa:
            continue  # todavía sin historial acumulado
        entries.append({"name": repo_cfg["name"], "pitch": repo_cfg.get("pitch"), "narrativa": narrativa})

    if not entries:
        log.info("ningún repo showcase tiene narrativa acumulada todavía; no genero deck maestro")
        return

    if not args.force:
        showcase_names = {r["name"] for r in showcase_repos}
        if not had_showcase_activity_this_week(showcase_names):
            log.info("ningún repo showcase tuvo actividad esta semana; me salto el deck maestro (usa --force para generarlo igual)")
            return

    markdown = render_markdown(entries)
    PORTFOLIO_MD_PATH.parent.mkdir(parents=True, exist_ok=True)
    PORTFOLIO_MD_PATH.write_text(markdown, encoding="utf-8")
    log.info("escrito %s (%d repos showcase)", PORTFOLIO_MD_PATH, len(entries))

    if args.no_pdf:
        return

    convert_to_pdf(PORTFOLIO_MD_PATH, PORTFOLIO_PDF_PATH)
    log.info("escrito %s", PORTFOLIO_PDF_PATH)


if __name__ == "__main__":
    main()
