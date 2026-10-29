"""Independent 16:9 editorial comparison deck; no production PDF or Drive writes.

Uses already-audited PUBLIC reports and the existing portfolio visual theme.
It never upgrades a candidate's editorial status or claims runtime validation.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess

from src.candidate_profiles import REPORT as PROFILE_REPORT
from src.portfolio_data import ROOT, load_portfolio
from src.project_selection_core import SHA_RE
from src.portfolio_release_review import OUTPUT as RELEASE_REPORT, _pinned_sources
from src.render_portfolio_v2 import THEME, build_slides, esc, page, render_markdown

OUT = ROOT / "out"
MD = OUT / "portfolio-review-v2.md"
HTML = OUT / "portfolio-review-v2.html"
MANIFEST = OUT / "portfolio-review-v2-manifest.json"
WARNING_MARK = ('<span style="position:absolute;right:28px;bottom:14px;'
                'font:700 12px DejaVu Sans Mono,monospace;color:#ffd186;">'
                'BORRADOR INTERNO · NO PUBLICAR</span>')


def _verified_inputs(report: dict, profiles: dict) -> tuple[list, dict]:
    if (report.get("visibility") != "public" or profiles.get("visibility") != "public"
            or report.get("automatic_publication") is not False
            or report.get("safe_to_replace_public_portfolio") is not False
            or report.get("private_inputs_accessed") is not False
            or profiles.get("automatic_publication") is not False):
        raise ValueError("Informe público sin aislamiento editorial")
    candidates = report.get("candidates")
    if not isinstance(candidates, list):
        raise ValueError("Candidatos inválidos")
    available = {}
    for draft in profiles.get("drafts", []):
        if (draft.get("visibility") != "public" or draft.get("draft_only") is not True
                or draft.get("publication_allowed") is not False
                or draft.get("repo") in available):
            raise ValueError("Borrador editorial no seguro")
        available[draft["repo"]] = draft
    seen = set()
    for candidate in candidates:
        if (candidate.get("visibility") != "public"
                or candidate.get("approved_for_release") is not False
                or candidate.get("repo") in seen
                or not isinstance(candidate.get("blockers"), list)
                or not candidate["blockers"]):
            raise ValueError("Candidato incorrecto o promovido")
        sample_links = candidate.get("unmerged_commit_samples", [])
        if not isinstance(sample_links, list) or len(sample_links) > 5:
            raise ValueError("Muestra de commits de ramas sin límites")
        for sample in sample_links:
            sha = sample.get("sha") if isinstance(sample, dict) else None
            if (not isinstance(sha, str) or not SHA_RE.fullmatch(sha)
                    or sample.get("kind") not in ("code", "test")
                    or sample.get("url") !=
                    f"https://github.com/{candidate['repo']}/commit/{sha}"
                    or sample.get("commit_subject_only") is not True
                    or sample.get("not_merged_or_functionally_verified") is not True
                    or not isinstance(sample.get("subject"), str)):
                raise ValueError("Muestra de commits ajena o no versionada")
        ci_checks = candidate.get("feature_branch_ci", [])
        if not isinstance(ci_checks, list) or len(ci_checks) > 5:
            raise ValueError("CI de ramas sin límite")
        for check in ci_checks:
            tip = check.get("tip_sha") if isinstance(check, dict) else None
            if not isinstance(tip, str) or not SHA_RE.fullmatch(tip):
                raise ValueError("SHA de CI de ramas inválido")
            urls = check.get("sample_run_urls")
            if not isinstance(urls, list) or len(urls) > 3:
                raise ValueError("Enlaces CI de ramas inválidos")
            prefix = f"https://github.com/{candidate['repo']}/actions/runs/"
            if any(not isinstance(url, str) or not url.startswith(prefix)
                   or not url[len(prefix):].isdigit() for url in urls):
                raise ValueError("Enlace CI ajeno al repositorio público")
            if check.get("not_main_or_runtime_evidence") is not True:
                raise ValueError("CI de ramas confunde main o ejecución")
        seen.add(candidate["repo"])
    return candidates, available


def build_review_slides(report: dict, profiles: dict, portfolio: dict,
                        *, stamp: str = "Vista previa editorial") -> list:
    candidates, available = _verified_inputs(report, profiles)
    slides = build_slides(portfolio, generation_stamp=stamp)
    expected = {x["repo"]: x.get("pinned_revision") for x in report.get("current_portfolio", [])}
    actual = {p["repo"]: p["revision"] for p in portfolio["projects"]}
    if expected != actual or len(expected) != len(report.get("current_portfolio", [])):
        raise ValueError("El portfolio actual no coincide con la revisión")
    slides.insert(0, page(
        "review-intro",
        '<div class="pf-meta">REVISIÓN EDITORIAL / DOCUMENTO LOCAL</div>'
        '<h1>Portfolio Maestro: selección en revisión</h1>'
        '<p class="pf-lead">Comparativa de contenidos versionados. '
        'La actividad de GitHub no acredita funcionamiento ni autoriza publicación.</p>'
        f'<div class="pf-status">NO PUBLICAR · {len(candidates)} CANDIDATOS PÚBLICOS</div>'
        '<p class="pf-bottom-note">Se conserva la selección anterior completa. '
        'Los candidatos nuevos son anexos de revisión, no casos de estudio aprobados. '
        'No contiene información privada ni sustituye al PDF de producción.</p>',
        "Copia de revisión separada del portfolio público; requiere validación manual."))
    rows = []
    for c in candidates:
        status = str(c.get("ci_status", "unknown"))
        unmerged = c.get("unmerged_code_7d", 0) + c.get("unmerged_tests_7d", 0)
        extra = (f" · {unmerged} commits en ramas no fusionadas (no en main)"
                 if unmerged else "")
        rows.append(
            '<div style="border:1px solid #275064;border-radius:9px;padding:10px 15px;'
            'background:#102438;margin-bottom:8px;">'
            f'<span style="font-size:20px;font-weight:700;color:#e8f2fb;">{esc(c.get("title") or c["repo"])}</span>'
            f'<span style="float:right;font-size:13px;color:#ffd186;">{esc(status)}</span>'
            f'<p style="font-size:14px;color:#a3b9c9;margin-top:3px;">'
            f'{len(c["blockers"])} comprobaciones pendientes · '
            f'{esc(c["repo"])}{esc(extra)}</p></div>')
    slides.insert(-1, page(
        "review-index",
        '<div class="pf-meta">PROPUESTA / PRIORIZACIÓN NO DEFINITIVA</div>'
        '<h2>Actividad reciente frente a evidencia comprobable</h2>'
        f'<p class="pf-lead">{len(candidates)} candidatos activos; CI en HEAD, no garantía funcional.</p>'
        + "".join(rows)
        + '<p class="pf-bottom-note">Solo se preparan fichas ampliadas cuando hay'
        ' referencias versionadas. Las demás permanecen en evaluación.</p>',
        "Candidatos públicos de la selección actual. Las pruebas y la publicación "
        "de cada proyecto requieren evaluación independiente."))
    for c in candidates:
        d = available.get(c["repo"])
        if (not d or d.get("revision") != c.get("head")
                or c.get("source_presence_verified_at_revision") is not True):
            continue
        if not _pinned_sources(d, c["repo"], d["revision"]):
            continue
        # Factual source citations are not claims of successful runtime execution.
        links = "".join(
            '<a class="pf-evidence" href="' + esc(source["url"]) + '">'
            '<strong>AFIRMACIÓN DOCUMENTADA</strong>'
            '<span>' + esc(source["statement"]) + '</span>'
            '<b>↗</b></a>'
            for source in d["sources"][:3])
        state = esc(c.get("ci_status", "unknown"))
        actual_ci = c.get("ci_run_url_at_head")
        ci_proof = ('<p class="pf-state"><a href="' + esc(actual_ci) +
                    '">Ver ejecución CI correcta en el HEAD ↗</a></p>'
                    if actual_ci else
                    '<p class="pf-limit">No se ha demostrado CI correcta en el HEAD.</p>')
        warnings = ", ".join(d.get("warnings", [])) or "Fuentes presentes en SHA; CI revisada por separado"
        markup = (
            '<div class="pf-meta">CANDIDATO / FICHA NO APROBADA</div>'
            '<h2>' + esc(d["title"]) + '</h2>'
            '<p class="pf-lead">Referencias de código y documentación; '
            'no equivalen a demostración de ejecución.</p>'
            '<div class="pf-evidence-grid"><div>'
            '<div class="pf-status">BORRADOR · CI: ' + state + '</div>'
            '<p class="pf-state">Commit de revisión: ' + esc(d["revision"][:12]) + '</p>'
            + ci_proof
            + '<p class="pf-limit">Pendiente: ' + esc(warnings) + '</p>'
            '<p class="pf-limit">Faltan pruebas funcionales, capturas reales '
            'autorizadas y aprobación editorial.</p>'
            '</div><div class="pf-evidence-list">'
            '<span class="pf-mini">FUENTES EN COMMIT INMUTABLE</span>'
            + links + '</div></div>')
        slides.insert(-1, page(
            "review-candidate", markup,
            "Ficha preliminar de " + d["title"] +
            ". No está aprobada para publicación. Deben verificarse pruebas funcionales.",
            c["repo"]))
    for c in candidates:
        examples = c.get("unmerged_commit_samples", [])
        if not examples:
            continue
        def path_note(sample):
            if "path_category_status" not in sample:
                return "Archivos modificados aún no auditados"
            if sample.get("path_scan_complete") is not True:
                return "Inspección de rutas incompleta"
            if sample.get("declared_kind_has_corresponding_path") is True:
                return "Rutas compatibles identificadas; ejecución NO verificada"
            return "No se identificaron rutas compatibles con el asunto"
        checks = c.get("feature_branch_ci", [])
        feature_links = "".join(
            '<a href="' + esc(check["sample_run_urls"][0]) + '">'
            + esc(check["branch"][:48]) + ': ' + esc(check["status"]) +
            ' (' + str(check["observed_workflow_count"]) + ' ejecuciones observadas)</a>'
            for check in checks[:2] if check.get("sample_run_urls")
        )
        evidence_links = "".join(
            '<a class="pf-evidence" href="' + esc(sample["url"]) + '">'
            '<strong>ASUNTO DECLARADO: ' + ('CÓDIGO' if sample["kind"] == "code" else 'TEST') + '</strong>'
            '<span>' + esc(sample["subject"][:145]) + '</span>'
            '<span>' + esc(path_note(sample)) + '</span>'
            '<b>SHA ' + esc(sample["sha"][:10]) + ' ↗</b></a>'
            for sample in examples[:3]
        )
        slides.insert(-1, page(
            "review-branch-evidence",
            '<div class="pf-meta">ACTIVIDAD NO INTEGRADA / EVIDENCIA DE COMMITS</div>'
            '<h2>' + esc(c.get("title") or c["repo"]) + '</h2>'
            '<p class="pf-lead">Muestra de commits públicos pendientes de integración: '
            'sus asuntos no acreditan pruebas exitosas ni funciones operativas.</p>'
            '<div class="pf-evidence-list">' + evidence_links + '</div>'
            '<p class="pf-limit">CI de puntas de ramas (no main): ' +
            (feature_links if feature_links else 'Sin ejecución confirmada') +
            '</p><p class="pf-bottom-note">Se desconoce la cobertura total de workflows. '
            'Sin aprobación editorial ni prueba funcional independiente.</p>',
            "Muestra de asuntos de commits en ramas públicas; no equivale "
            "a trabajo integrado ni funcionalidades verificadas.",
            c["repo"]))
    return [
        {**slide, "markup": slide["markup"] + WARNING_MARK}
        for slide in slides
    ]


def render(*, stamp: str | None = None, html_output: bool = True) -> dict:
    report = json.loads(RELEASE_REPORT.read_text(encoding="utf-8"))
    profiles = json.loads(PROFILE_REPORT.read_text(encoding="utf-8"))
    data = load_portfolio()
    if stamp is None:
        stamp = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")
    slides = build_review_slides(report, profiles, data, stamp=stamp)
    OUT.mkdir(parents=True, exist_ok=True)
    markdown = render_markdown(slides)
    MD.write_text(markdown, encoding="utf-8")
    manifest = {
        "schema": 1, "visibility": "public",
        "review_only": True, "automatic_publication": False,
        "production_unchanged": True, "private_inputs_accessed": False,
        "source_selection_generated_at": report["selection_generated_at"],
        "curated": [p["repo"] for p in data["projects"]],
        "candidate_slides": [s["repo"] for s in slides if s["kind"] == "review-candidate"],
        "slide_count": len(slides),
        "markdown_sha256": hashlib.sha256(markdown.encode("utf-8")).hexdigest(),
        "html_created": bool(html_output),
    }
    if html_output:
        subprocess.run(
            ["marp", str(MD), "--no-stdin", "--html", "--theme-set", str(THEME), "-o", str(HTML)],
            check=True)
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-html", action="store_true",
                        help="Solo Markdown y manifiesto para CI sin navegador")
    args = parser.parse_args()
    result = render(html_output=not args.no_html)
    print(f"Comparativa no publicable: {result['slide_count']} diapositivas, "
          f"{len(result['candidate_slides'])} fichas candidatas; "
          "portfolio y Drive sin cambios.")
