"""Editorial 16:9 composition proposal; no release, private data, or PDF writes.

The approved portfolio remains untouched. Candidate narratives are restricted
to public, SHA-pinned sources whose file paths passed the independent audit.
Priorities are explicitly provisional: they are NOT functional validation.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import yaml

from src.candidate_profiles import REPORT as PROFILES
from src.portfolio_data import ROOT, load_portfolio
from src.portfolio_release_review import OUTPUT as RELEASE, _pinned_sources
from src.project_selection_core import configured_projects
from src.render_portfolio_review import _verified_inputs, WARNING_MARK
from src.render_portfolio_v2 import esc, page, render_markdown

OUT = ROOT / "out"
MD = OUT / "portfolio-proposal-v3.md"
MANIFEST = OUT / "portfolio-proposal-v3-manifest.json"
CONFIG = ROOT / "config/project-selection.yml"


def priority_index(config: dict) -> dict:
    return {name: p["priority"] for p in configured_projects(config)
            for name in p["repos"]}


def build_slides(report: dict, profiles: dict, portfolio: dict, priorities: dict,
                 *, stamp: str = "Propuesta editorial") -> list[dict]:
    candidates, available = _verified_inputs(report, profiles)
    if (not isinstance(priorities, dict)
            or any(not isinstance(k, str) or type(v) is not int
                   or not 0 <= v <= 5 for k, v in priorities.items())):
        raise ValueError("Prioridades editoriales inválidas")
    published = {p["repo"]: p["revision"] for p in portfolio["projects"]}
    pinned = {p["repo"]: p.get("pinned_revision")
              for p in report.get("current_portfolio", [])}
    if published != pinned or len(published) != len(report.get("current_portfolio", [])):
        raise ValueError("El portfolio vigente no coincide con la revisión")
    featured, supporting, blocked = [], [], []
    for c in candidates:
        ci = c.get("ci_status", "unknown")
        if ci not in ("success_at_head", "unknown", "pending", "inconclusive",
                      "not_checked", "failure_or_cancelled"):
            raise ValueError("Estado CI no reconocido")
        repo = c["repo"]
        priority = priorities.get(repo, 1)
        draft = available.get(repo)
        ready_source = bool(
            draft and draft.get("revision") == c.get("head")
            and c.get("source_presence_verified_at_revision") is True)
        if ready_source and not _pinned_sources(draft, repo, draft["revision"]):
            raise ValueError("Fuentes no versionadas en propuesta")
        entry = {"row": c, "draft": draft if ready_source else None,
                 "priority": priority, "source_ready": ready_source}
        if ci == "failure_or_cancelled":
            blocked.append(entry)
        elif priority >= 4:
            featured.append(entry)
        else:
            supporting.append(entry)
    featured.sort(key=lambda x: (-x["priority"], x["row"]["repo"]))
    supporting.sort(key=lambda x: (-x["priority"], x["row"]["repo"]))
    blocked.sort(key=lambda x: x["row"]["repo"])

    def name(entry):
        d = entry["draft"]
        return (d or entry["row"]).get("title") or entry["row"]["repo"]

    def pitch(entry):
        d = entry["draft"]
        return (d.get("pitch") if d else "") or "Pendiente de contrastar fuentes y narrativa."

    def source_links(entry):
        d = entry["draft"]
        if not d:
            return '<p class="pf-limit">Sin referencias auditadas en la revisión actual.</p>'
        return "".join(
            '<a class="pf-evidence" href="' + esc(ref["url"]) + '">'
            '<strong>FUENTE VERSIONADA, NO PRUEBA FUNCIONAL</strong>'
            '<span>' + esc(ref["statement"][:165]) + '</span></a>'
            for ref in d["sources"][:2])

    def limits(entry):
        d = entry["draft"]
        if d and d.get("limitations"):
            return esc(d["limitations"][0][:235])
        return "Requiere validación funcional independiente y aprobación editorial."

    def ci_label(entry):
        ci = entry["row"]["ci_status"]
        return ("CI correcta en HEAD; no acredita ejecución funcional"
                if ci == "success_at_head" else
                "CI fallida en HEAD; publicación bloqueada"
                if ci == "failure_or_cancelled" else
                "CI de la rama principal sin confirmar")

    slides = [
        page("proposal-cover",
             '<div class="pf-line"></div>'
             '<p class="pf-eyebrow">PORTFOLIO MAESTRO / PROPUESTA V3</p>'
             f'<p class="pf-byline">{esc(portfolio["author"])}</p>'
             '<h1>Proyectos que merecen ser contados.</h1>'
             '<p class="pf-cover-subtitle">Ingeniería industrial, software y desarrollo '
             'en evaluación. Historias seleccionadas según evidencias, no ruido de commits.</p>'
             f'<div class="pf-status">BORRADOR · NO PUBLICAR · {len(candidates)} CANDIDATOS</div>'
             '<p class="pf-bottom-note">Mantiene intactos los casos ya publicados. '
             f'Revisión {esc(stamp)}; no equivale a aprobación técnica.</p>',
             "Propuesta de estructura, no una versión publicada del portfolio."),
    ]
    def mini(entry, label):
        return ('<div class="pf-project-summary"><span class="pf-mini">'
                + esc(label) + '</span><h3>' + esc(name(entry))
                + '</h3><p>' + esc(pitch(entry)[:168]) + '</p>'
                '<span class="pf-tech">' + esc(ci_label(entry)) + '</span></div>')
    slides.append(page(
        "proposal-editorial-map",
        '<div class="pf-meta">01 / DECISIONES EDITORIALES PROVISIONALES</div>'
        '<h2>Protagonismo según relevancia y evidencia.</h2>'
        '<p class="pf-lead">Prioridad declarada y actividad auditada no significan '
        'producto terminado.</p>'
        '<div class="pf-two">'
        + "".join(mini(entry, "FOCO PROPUESTO · PENDIENTE DE VALIDAR")
                  for entry in featured[:2])
        + "".join(mini(entry, "COMPLEMENTARIO · EN REVISIÓN")
                  for entry in supporting[:2])
        + '</div>'
        f'<p class="pf-bottom-note">{len(blocked)} candidato(s) con CI fallida '
        'se mantienen fuera del protagonismo. No se modifica la selección vigente.</p>',
        "Mapa editorial provisional, no una decisión de publicación."
    ))
    for entry in featured[:2]:
        c, d = entry["row"], entry["draft"]
        repo = c["repo"]
        ci_url = c.get("ci_run_url_at_head")
        prefix = f"https://github.com/{repo}/actions/runs/"
        if ci_url is not None and (not isinstance(ci_url, str)
                                  or not ci_url.startswith(prefix)
                                  or not ci_url[len(prefix):].isdigit()):
            raise ValueError("Enlace CI de proyecto ajeno")
        ci_html = ('<a href="' + esc(ci_url) + '">Ejecución CI al HEAD</a>'
                   if ci_url else esc(ci_label(entry)))
        unmerged = c.get("unmerged_code_7d", 0) + c.get("unmerged_tests_7d", 0)
        if type(unmerged) is not int or unmerged < 0:
            raise ValueError("Recuento de ramas inválido")
        slides.append(page(
            "proposal-featured",
            '<div class="pf-meta">02 / FOCO PROPUESTO · DOCUMENTACIÓN AUDITADA</div>'
            '<h2>' + esc(name(entry)) + '</h2>'
            '<p class="pf-lead">' + esc(pitch(entry)[:260]) + '</p>'
            '<div class="pf-evidence-grid"><div>'
            '<div class="pf-card"><span class="pf-mini">ESTADO DE EVIDENCIA</span>'
            '<p>' + ci_html + '</p>'
            f'<p>Revisión principal: {esc(str(c.get("head") or "no disponible")[:12])}</p>'
            f'<p>Commits recientes en ramas no fusionadas: {unmerged} '
            '(no equivalen a main ni a pruebas funcionales).</p></div>'
            '<div class="pf-card"><span class="pf-mini">LÍMITE CONOCIDO</span>'
            '<p>' + limits(entry) + '</p></div></div>'
            '<div class="pf-evidence-list"><span class="pf-mini">EVIDENCIAS EN SHA FIJO</span>'
            + source_links(entry) + '</div></div>'
            '<p class="pf-bottom-note">Sin captura de ejecución independiente ni aprobación '
            'editorial. Este caso NO está autorizado para publicación.</p>',
            f"Posible historia principal de {name(entry)}; faltan evidencias reales.",
            repo
        ))
    if supporting:
        slides.append(page(
            "proposal-supporting",
            '<div class="pf-meta">03 / PROYECTOS COMPLEMENTARIOS</div>'
            '<h2>Valor documental sin exagerar el estado.</h2>'
            '<p class="pf-lead">Una ficha verificable no es una demostración funcional.</p>'
            '<div class="pf-two">' + "".join(
                '<div class="pf-project-summary"><span class="pf-mini">EN EVALUACIÓN</span>'
                '<h3>' + esc(name(x)) + '</h3>'
                '<p>' + esc(pitch(x)[:195]) + '</p>'
                '<p class="pf-limit">' + limits(x) + '</p>'
                '<span class="pf-tech">' + esc(ci_label(x)) + '</span></div>'
                for x in supporting[:4]) + '</div>'
            '<p class="pf-bottom-note">Sin inclusión definitiva ni promesas de '
            'compatibilidad o funcionamiento no verificadas.</p>',
            "Candidatos complementarios sujetos a comprobaciones.",
        ))
    if blocked:
        slides.append(page(
            "proposal-blocked",
            '<div class="pf-meta">04 / LABORATORIOS Y BLOQUEOS TÉCNICOS</div>'
            '<h2>La transparencia también forma parte del portfolio.</h2>'
            '<p class="pf-lead">Una CI fallida impide presentar una aplicación como estable.</p>'
            '<div class="pf-two">' + "".join(
                '<div class="pf-card"><span class="pf-mini">CI FALLIDA · NO PROMOVER</span>'
                '<h3>' + esc(name(x)) + '</h3><p>' + esc(pitch(x)[:180]) + '</p>'
                '<p class="pf-limit">' + limits(x) + '</p></div>'
                for x in blocked[:4]) + '</div>'
            '<p class="pf-bottom-note">Se preserva la evidencia de problemas, '
            'sin afirmar que estén corregidos.</p>',
            "Proyectos experimentales que necesitan estabilización técnica."
        ))
    slides.append(page(
        "proposal-existing",
        '<div class="pf-meta">05 / PORTFOLIO PUBLICADO · PRESERVADO</div>'
        '<h2>Conservar no significa ignorar.</h2>'
        '<p class="pf-lead">Los casos existentes se mantienen hasta que la nueva '
        'selección sea aprobada con fuentes y capturas autorizadas.</p>'
        '<div class="pf-two">' + "".join(
            '<div class="pf-project-summary"><span class="pf-mini">CASO VIGENTE</span>'
            '<h3>' + esc(p["title"]) + '</h3><p>' + esc(p["statement"][:185])
            + '</p><span class="pf-tech">SHA ' + esc(p["revision"][:12])
            + '</span></div>' for p in portfolio["projects"])
        + '</div>'
        '<p class="pf-bottom-note">No se ha escrito ni publicado sobre '
        'content/portfolio/projects.yml ni sobre el PDF oficial.</p>',
        "Los dos proyectos existentes no se eliminan de forma automática."
    ))
    slides.append(page(
        "proposal-approval",
        '<div class="pf-meta">06 / PUERTAS DE PUBLICACIÓN</div>'
        '<h2>Una buena historia exige pruebas reales.</h2>'
        '<p class="pf-lead">El diseño final solo se aprueba cuando el contenido '
        'y su evidencia coinciden.</p>'
        '<div class="pf-two">'
        '<div class="pf-card"><span class="pf-mini">ANTES DE PUBLICAR</span>'
        '<p>Pruebas funcionales independientes, capturas autorizadas, '
        'enlaces versionados y revisión de afirmaciones.</p></div>'
        '<div class="pf-card"><span class="pf-mini">ESTADO DE ESTA PROPUESTA</span>'
        '<p>Cero candidatos aprobados. Ninguna sustitución del portfolio, '
        'CI de ramas separada de CI principal.</p></div></div>'
        '<p class="pf-bottom-note">BORRADOR INTERNO · NO PUBLICAR</p>',
        "La publicación queda expresamente bloqueada."
    ))
    return [{**slide, "markup": slide["markup"] + WARNING_MARK}
            for slide in slides]


def render(*, stamp: str | None = None) -> dict:
    report = json.loads(RELEASE.read_text(encoding="utf-8"))
    profiles = json.loads(PROFILES.read_text(encoding="utf-8"))
    portfolio = load_portfolio()
    priorities = priority_index(yaml.safe_load(CONFIG.read_text(encoding="utf-8")))
    stamp = stamp or datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")
    slides = build_slides(report, profiles, portfolio, priorities, stamp=stamp)
    text = render_markdown(slides)
    manifest = {
        "schema": 1, "visibility": "public", "proposal_only": True,
        "production_unchanged": True, "automatic_publication": False,
        "editorial_approval_granted": False,
        "source_selection_generated_at": report["selection_generated_at"],
        "existing_projects": [p["repo"] for p in portfolio["projects"]],
        "candidate_repos": [p["repo"] for p in report["candidates"]],
        "slide_count": len(slides),
        "slide_kinds": [p["kind"] for p in slides],
        "markdown_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
    }
    OUT.mkdir(parents=True, exist_ok=True)
    for target, payload in ((MD, text), (MANIFEST,
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")):
        if target.is_symlink() or target.parent.resolve() != OUT.resolve():
            raise ValueError("Salida de propuesta no autorizada")
        target.write_text(payload, encoding="utf-8")
    return manifest


if __name__ == "__main__":
    value = render()
    print("Composición editorial v3:", value["slide_count"],
          "diapositivas; solo propuesta, no PDF ni publicación.")
