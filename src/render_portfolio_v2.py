"""Editorial portfolio V2: semantic slides from audited profiles, never raw AI narrative."""
from __future__ import annotations

import argparse
import html
import json
import logging
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

try:
    from src.portfolio_data import ROOT, load_portfolio, recent_activity
except ModuleNotFoundError:
    from portfolio_data import ROOT, load_portfolio, recent_activity

TEMPLATE_DIR = ROOT / "templates"
THEME = TEMPLATE_DIR / "portfolio.css"
MD_PATH = ROOT / "out" / "portfolio-v2.md"
PDF_PATH = ROOT / "out" / "portfolio-v2.pdf"
MANIFEST_PATH = ROOT / "out" / "portfolio-v2-manifest.json"
LOG = logging.getLogger("portfolio-v2")


def esc(s: object) -> str:
    return html.escape(str(s), quote=True)


def asset_url(path: str) -> str:
    # Validated relative paths by src.portfolio_data.
    return "../" + path


def text_card(label: str, text: str, *, accent: bool = False) -> str:
    cls = "pf-card pf-card-accent" if accent else "pf-card"
    return (f'<div class="{cls}"><span class="pf-mini">{esc(label)}</span>'
            f'<p>{esc(text)}</p></div>')


def image_html(project: dict, field: str, css_class: str = "pf-shot") -> str:
    image = project.get(field)
    if not image:
        return ""
    caption = project.get(field.replace("_image", "_caption"), "")
    return (f'<figure class="{css_class}"><img src="{esc(asset_url(image))}" alt="{esc(caption)}">'
            f'<figcaption>{esc(caption)}</figcaption></figure>')


def page(kind: str, markup: str, narration: str, project: str | None = None) -> dict:
    return {"kind": kind, "markup": markup, "narration": narration, "repo": project}


def build_slides(data: dict, latest: list[dict] | None = None) -> list[dict]:
    projects = data["projects"]
    slides = [
        page("cover",
             '<div class="pf-line"></div>'
             '<p class="pf-eyebrow">PORTFOLIO · ENGINEERING / SOFTWARE</p>'
             f'<h1>{esc(data["title"])}</h1>'
             f'<p class="pf-cover-subtitle">{esc(data["subtitle"])}</p>'
             f'<div class="pf-cover-footer"><span>{len(projects)} PROYECTOS DESTACADOS</span>'
             '<span>EDICIÓN DOCUMENTADA · FUENTES EN GITHUB</span></div>',
             f'Presentamos una selección de {len(projects)} proyectos públicos de ingeniería y desarrollo de software, con capacidades documentadas y límites explícitos.'),
        page("overview",
             '<div class="pf-meta">01 / MAPA DE PROYECTOS</div>'
             '<h2>Dos áreas. Una forma de construir.</h2>'
             '<p class="pf-lead">Automatización industrial y productos web con trazabilidad.</p>'
             '<div class="pf-two">'
             + "".join('<div class="pf-project-summary">'
                       f'<span class="pf-mini">{esc(p["category"])}</span>'
                       f'<h3>{esc(p["title"])}</h3><p>{esc(p["statement"])}</p>'
                       f'<span class="pf-tech">{esc(" · ".join(p["stack"][:3]))}</span>'
                       '</div>' for p in projects)
             + '</div>'
             f'<p class="pf-bottom-note">{esc(data["editorial_note"])}</p>',
             "El portfolio reúne proyectos de automatización industrial y aplicaciones web. Cada caso muestra el problema abordado, la solución documentada y las evidencias disponibles."),
    ]
    for index, p in enumerate(projects, start=1):
        repo = p["repo"]
        slides.append(page(
            "project",
            f'<div class="pf-meta">0{index+1} / CASO DE ESTUDIO · {esc(p["category"])}</div>'
            f'<h2>{esc(p["title"])}</h2>'
            f'<p class="pf-lead">{esc(p["statement"])}</p>'
            '<div class="pf-hero-grid"><div class="pf-hero-copy">'
            + text_card("EL PROBLEMA", p["problem"])
            + text_card("LA SOLUCIÓN", p["solution"], accent=True)
            + '<div class="pf-pills">' + "".join(f'<span>{esc(t)}</span>' for t in p["stack"][:4]) + '</div>'
            + '</div>' + image_html(p, "hero_image", "pf-shot pf-hero-shot") + '</div>',
            f'{p["title"]}. {p["problem"]} {p["solution"]}', repo))
        gallery = image_html(p, "detail_image", "pf-shot pf-gallery-image")
        if p.get("second_image"):
            gallery += image_html(p, "second_image", "pf-shot pf-gallery-image")
        slides.append(page(
            "capabilities",
            f'<div class="pf-meta">0{index+1} / {esc(p["title"].upper())} · PRODUCTO</div>'
            '<h2>Qué ofrece y cómo se utiliza</h2>'
            '<div class="pf-cap-grid">'
            '<div class="pf-cap-list">'
            + "".join(f'<div class="pf-cap"><span>0{i}</span><p>{esc(item)}</p></div>'
                      for i, item in enumerate(p["capabilities"], start=1))
            + '</div><div class="pf-gallery">' + gallery + '</div></div>'
            f'<p class="pf-bottom-note">Capturas versionadas · No se presentan como prueba de despliegue actual.</p>',
            f'Entre las capacidades documentadas de {p["title"]} destacan: '
            + "; ".join(p["capabilities"]) + ".", repo))
        evidences = "".join(
            f'<a class="pf-evidence" href="{esc(x["url"])}">'
            f'<strong>{esc(x["label"])}</strong><span>{esc(x["description"])}</span>'
            '<b>↗</b></a>' for x in p["evidence"][:3])
        slides.append(page(
            "evidence",
            f'<div class="pf-meta">0{index+1} / {esc(p["title"].upper())} · EVIDENCIAS</div>'
            '<h2>Qué está acreditado y qué falta</h2>'
            '<div class="pf-evidence-grid"><div>'
            f'<div class="pf-status">{esc(p["status"])}</div>'
            f'<p class="pf-state">{esc(p["status_detail"])}</p>'
            f'<a class="pf-source" href="{esc(p["status_source"])}">Consultar la fuente del estado ↗</a>'
            '<h3 class="pf-limits-title">Límites actuales</h3>'
            + "".join(f'<p class="pf-limit">— {esc(t)}</p>' for t in p["limitations"][:2])
            + '</div><div class="pf-evidence-list"><span class="pf-mini">REFERENCIAS PÚBLICAS</span>'
            + evidences + '</div></div>',
            f'El estado documentado de {p["title"]} es: {p["status"]}. '
            + p["status_detail"] + " Limitaciones: " + "; ".join(p["limitations"]) + ".", repo))
    if latest:
        recent_cards = []
        for item in latest:
            events = "".join(
                f'<a class="pf-recent-row" href="{esc(event["url"])}">'
                f'<span class="pf-recent-id">{esc(event["label"])} · {esc(event["date"])}</span>'
                f'<span class="pf-recent-title">{esc(event["title"])}</span></a>'
                for event in item["events"]
            )
            recent_cards.append(
                f'<div class="pf-recent-card"><span class="pf-mini">{esc(item["title"])}</span>'
                + events + '</div>')
        slides.append(page(
            "recent",
            '<div class="pf-meta">ACTIVIDAD RECIENTE / FUENTES GITHUB</div>'
            '<h2>Eventos nuevos, sin conclusiones inventadas.</h2>'
            '<p class="pf-lead">Referencias de la última recolección; no acreditan despliegue ni funcionamiento.</p>'
            '<div class="pf-two">' + "".join(recent_cards) + '</div>',
            "Estos son los eventos públicos de GitHub registrados en la última recolección para los proyectos seleccionados. "
            "Los títulos describen cambios declarados por sus autores; sus resultados deben validarse por separado."))

    cards = "".join(
        f'<div class="pf-project-summary"><span class="pf-mini">{esc(p["title"])}</span>'
        + "".join(f'<p class="pf-next-item">↗ {esc(step)}</p>' for step in p["next_steps"][:2])
        + f'<a href="{esc(p["repo_url"])}">Código y documentación ↗</a>'
        + '</div>' for p in projects
    )
    slides.append(page(
        "close",
        '<div class="pf-meta">CIERRE / PRÓXIMOS PASOS</div>'
        '<h2>El portfolio también muestra lo pendiente.</h2>'
        '<p class="pf-lead">La transparencia es parte de la ingeniería.</p>'
        '<div class="pf-two">' + cards + '</div>'
        '<p class="pf-bottom-note">Documento generado a partir de un snapshot versionado. '
        'No certifica sistemas reales ni sustituye pruebas de ejecución.</p>',
        "La evolución continuará con evidencias de ejecución reproducibles, mejoras de las pruebas y actualización de los recursos visuales. Cada afirmación puede revisarse desde las fuentes enlazadas."))
    return slides


def render_markdown(slides: list[dict]) -> str:
    env = Environment(loader=FileSystemLoader(TEMPLATE_DIR), trim_blocks=False, lstrip_blocks=False)
    return env.get_template("portfolio_v2.md.j2").render(slides=slides)


def write_preview(*, pdf: bool = True) -> tuple[list[dict], Path]:
    data = load_portfolio()
    slides = build_slides(data, recent_activity(data["projects"]))
    markdown = render_markdown(slides)
    MD_PATH.parent.mkdir(parents=True, exist_ok=True)
    MD_PATH.write_text(markdown, encoding="utf-8")
    manifest = {
        "schema": 2,
        "source": "content/portfolio/projects.yml",
        "project_revisions": {p["repo"]: p["revision"] for p in data["projects"]},
        "slides": [{"index": index, "kind": s["kind"], "repo": s["repo"], "narration": s["narration"]}
                   for index, s in enumerate(slides, 1)],
        "published_to_drive": False,
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if pdf:
        marp = shutil.which("marp")
        if not marp:
            raise RuntimeError("marp no instalado")
        subprocess.run([marp, str(MD_PATH), "--pdf", "--no-stdin", "--html",
                        "--allow-local-files", "--theme-set", str(THEME),
                        "-o", str(PDF_PATH)], check=True)
    LOG.info("%d diapositivas documentadas en %s", len(slides), MD_PATH)
    return slides, MD_PATH


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-pdf", action="store_true", help="Escribe Markdown y manifiesto, no PDF")
    args = parser.parse_args()
    write_preview(pdf=not args.no_pdf)
