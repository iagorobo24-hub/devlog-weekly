"""Stable evidence-first PUBLIC editorial closure, isolated from release.

The weekly ranking informs review; it never silently changes editorial cases.
This generator uses pinned public repo narratives and a synchronized public
release-review snapshot. It does not perform runtime QA or publish anything.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

import yaml

from src.portfolio_data import ROOT, load_portfolio
from src.candidate_profiles import CANDIDATES
from src.portfolio_release_review import OUTPUT as RELEASE
from src.render_portfolio_v2 import esc, page, render_markdown

SELECTION = ROOT / "content/portfolio/editorial-selection-public.yml"
OUT = ROOT / "out"
MD = OUT / "portfolio-editorial-closure-v4.md"
MANIFEST = OUT / "portfolio-editorial-closure-v4-manifest.json"
EVIDENCE = OUT / "portfolio-evidence-public.json"
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
REPO_RE = re.compile(r"^iagorobo24-hub/[A-Za-z0-9_.-]+$")
PATH_RE = re.compile(r"^[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*$")
BASIS = {"repository_documentation", "repository_file_presence",
         "repository_reported_runtime", "repository_reported_static_checks"}
EXPECTED = (3, 2, 1)
DISCLAIMER = ('<span style="position:absolute;right:28px;bottom:14px;'
              'font:700 12px DejaVu Sans Mono,monospace;color:#ffd186;">'
              'BORRADOR INTERNO · NO PUBLICAR</span>')


def validate(selection: dict, report: dict, portfolio: dict) -> tuple[list, list, list, dict]:
    """Fail closed for private data, stale snapshots and unsupported comparisons."""
    if (not isinstance(selection, dict) or selection.get("version") != 1
            or selection.get("visibility") != "public"
            or selection.get("status") != "frozen_editorial_scope_not_release_approval"):
        raise ValueError("Selección pública sin decisión editorial fijada")
    policy = selection.get("policy")
    if (not isinstance(policy, dict) or policy.get("automatic_publication") is not False
            or policy.get("exclude_uninspected_nonpublic_work") is not True
            or policy.get("existing_portfolio_unchanged") is not True
            or policy.get("require_pinned_public_sources") is not True
            or policy.get("do_not_infer_runtime_from_ci") is not True):
        raise ValueError("Controles editoriales insuficientes")
    if (not isinstance(report, dict) or report.get("visibility") != "public"
            or report.get("automatic_publication") is not False
            or report.get("safe_to_replace_public_portfolio") is not False
            or report.get("private_inputs_accessed") is not False):
        raise ValueError("Preflight privado o no seguro")
    current = portfolio.get("projects")
    if not isinstance(current, list) or len(current) != 2:
        raise ValueError("Cartera aprobada inesperada")
    published = {p["repo"]: p["revision"] for p in current}
    reviewed = report.get("current_portfolio")
    if (not isinstance(reviewed, list) or
            {x.get("repo"): x.get("pinned_revision") for x in reviewed} != published
            or len(reviewed) != len(published)):
        raise ValueError("El portfolio publicado no coincide con preflight")
    candidates = report.get("candidates")
    if not isinstance(candidates, list):
        raise ValueError("Sin evaluación pública de candidatos")
    indexed = {}
    for candidate in candidates:
        repo = candidate.get("repo")
        if (candidate.get("visibility") != "public"
                or candidate.get("approved_for_release") is not False
                or not isinstance(repo, str) or not REPO_RE.fullmatch(repo)
                or repo in indexed):
            raise ValueError("Candidato privado, duplicado o aprobado")
        indexed[repo] = candidate
    buckets = []
    seen = set()
    for key, expected in zip(("main_cases", "supporting_cases", "excluded_cases"), EXPECTED):
        rows = selection.get(key)
        if not isinstance(rows, list) or len(rows) != expected:
            raise ValueError("Composición editorial inestable")
        result = []
        for item in rows:
            repo, sha = item.get("repo"), item.get("revision")
            if (not isinstance(repo, str) or not REPO_RE.fullmatch(repo)
                    or not isinstance(sha, str) or not SHA_RE.fullmatch(sha)
                    or repo in seen):
                raise ValueError("Identidad editorial no pública o duplicada")
            seen.add(repo)
            if repo not in indexed and published.get(repo) != sha:
                raise ValueError("Proyecto sin auditoría pública ni caso aprobado")
            if repo in indexed and indexed[repo].get("head") != sha:
                raise ValueError("Revisión editorial desactualizada; revisar antes de generar")
            if key != "excluded_cases":
                for label in ("title", "field", "problem", "solution", "limits",
                              "takeaway"):
                    value = item.get(label)
                    if (not isinstance(value, str) or not (3 if label == "title" else 12) <= len(value) <= 360
                            or any(x in value for x in ("<", ">"))):
                        raise ValueError("Narrativa editorial ausente o excesiva")
                contributions = item.get("contributions")
                evidence = item.get("evidence")
                if (not isinstance(contributions, list)
                        or not 2 <= len(contributions) <= 4
                        or any(not isinstance(x, str) or not 15 <= len(x) <= 230
                               for x in contributions)
                        or not isinstance(evidence, list) or not 1 <= len(evidence) <= 3):
                    raise ValueError("Logros editoriales sin alcance comprobable")
                for proof in evidence:
                    path = proof.get("source_path")
                    if (proof.get("basis") not in BASIS
                            or not isinstance(path, str)
                            or not PATH_RE.fullmatch(path)
                            or any(part in (".", "..") for part in path.split("/"))
                            or not isinstance(proof.get("claim"), str)
                            or not 20 <= len(proof["claim"]) <= 275):
                        raise ValueError("Afirmación sin fuente pública fijada")
                    source_url = f"https://github.com/{repo}/blob/{sha}/{path}"
                    if not source_url.startswith(f"https://github.com/{repo}/blob/{sha}/"):
                        raise ValueError("Enlace no fijado")
                if repo in indexed:
                    # Verify that each claim's source path was in the independently
                    # scanned candidate source inventory, not added ad hoc here.
                    candidate_files = sorted(CANDIDATES.glob("*.yml"))
                    matched = []
                    for candidate_file in candidate_files:
                        if candidate_file.is_symlink():
                            raise ValueError("Fuente candidata simbólica")
                        candidate_data = yaml.safe_load(
                            candidate_file.read_text(encoding="utf-8"))
                        if candidate_data.get("repo") == repo:
                            matched.append(candidate_data)
                    if (len(matched) != 1 or matched[0].get("revision") != sha
                            or matched[0].get("visibility") != "public"):
                        raise ValueError("Sin ficha candidata pública coincidente")
                    audited_paths = {x.get("source_path")
                                     for x in matched[0].get("statements", [])}
                    if any(proof["source_path"] not in audited_paths
                           for proof in evidence):
                        raise ValueError("Afirmación sin ruta incluida en auditoría de candidato")
                    if indexed[repo].get("source_presence_verified_at_revision") is not True:
                        raise ValueError("Falta auditoría de rutas de candidato")
            else:
                if repo not in indexed or indexed[repo].get("ci_status") != "failure_or_cancelled":
                    raise ValueError("Exclusión por fallo CI no demostrada")
                if (not isinstance(item.get("reason"), str)
                        or not 30 <= len(item["reason"]) <= 350):
                    raise ValueError("Exclusión sin causa documental")
            result.append(item)
        buckets.append(result)
    if len(seen) != sum(EXPECTED):
        raise ValueError("Cobertura editorial incompleta")
    return (*buckets, indexed)


CI_STATES = {"success_at_head", "failure_or_cancelled", "unknown",
             "pending", "inconclusive", "unavailable"}


def validate_evidence_feed(feed: dict, selection: dict, release: dict) -> dict:
    """Read-only CI evidence must refer to the same five pinned public cases."""
    if (not isinstance(feed, dict) or feed.get("schema") != 1
            or feed.get("visibility") != "public"
            or feed.get("automatic_publication") is not False
            or feed.get("safe_to_replace_public_portfolio") is not False
            or feed.get("public_projects_only") is not True
            or feed.get("private_sources_inspected") is not False
            or feed.get("ci_reports_consistent") is not True
            or feed.get("ci_report_disagreements") != []
            or feed.get("source_selection_generated_at")
            != release.get("selection_generated_at")):
        raise ValueError("CI pública no reconciliada con la selección")
    cases = feed.get("cases")
    selected = selection["main_cases"] + selection["supporting_cases"]
    expected = {p["repo"]: p["revision"] for p in selected}
    if not isinstance(cases, list) or len(cases) != len(expected):
        raise ValueError("Cobertura de CI de cinco proyectos incompleta")
    lookup = {}
    for p in cases:
        if not isinstance(p, dict):
            raise ValueError("Fila CI pública inválida")
        repo, sha = p.get("repo"), p.get("revision")
        if (repo not in expected or sha != expected[repo] or repo in lookup
                or p.get("visibility") != "public"
                or p.get("head_matches_revision") is not True
                or p.get("ready_for_publication") is not False
                or p.get("owner_permission_confirmed") is not False
                or p.get("independent_runtime_validated") is not False):
            raise ValueError("CI con identidad, revisión o autorización inválida")
        ci = p.get("ci")
        if not isinstance(ci, dict) or ci.get("status") not in CI_STATES:
            raise ValueError("Estado CI público inválido")
        url = ci.get("run_url")
        prefix = f"https://github.com/{repo}/actions/runs/"
        if url is not None and (
                not isinstance(url, str) or not url.startswith(prefix)
                or not url[len(prefix):].isdigit()):
            raise ValueError("Enlace CI ajeno o no canónico")
        lookup[repo] = ci
    return lookup


def build_slides(selection: dict, report: dict, portfolio: dict, *,
                 stamp: str = "Revisión editorial",
                 evidence: dict | None = None) -> list[dict]:
    main, supporting, excluded, checked = validate(selection, report, portfolio)
    verified_ci = validate_evidence_feed(evidence, selection, report) if evidence is not None else {}

    def source_link(project: dict, proof: dict) -> str:
        url = ("https://github.com/" + project["repo"] + "/blob/" +
               project["revision"] + "/" + proof["source_path"])
        return ('<a class="pf-evidence" href="' + esc(url) + '">'
                '<strong>FUENTE VERSIONADA · ' + esc(proof["basis"]) + '</strong>'
                '<span>' + esc(proof["claim"]) + '</span></a>')

    def evidence_label(project: dict) -> str:
        if project["repo"] in verified_ci:
            ci = verified_ci[project["repo"]]
            status = ci["status"]
            if status == "success_at_head":
                label = "CI de push en HEAD correcta · no acredita funcionamiento real"
            elif status == "failure_or_cancelled":
                label = "CI de push en HEAD fallida · no presentar como estable"
            else:
                label = "CI en HEAD no confirmada · no implica fallo"
            if ci.get("run_url"):
                return ('<a href="' + esc(ci["run_url"]) + '">' +
                        esc(label) + '</a>')
            return esc(label)
        row = checked.get(project["repo"])
        if not row:
            return esc("Caso ya publicado · CI no reexaminada en este ciclo")
        ci = row.get("ci_status")
        if ci == "success_at_head":
            return esc("CI al HEAD correcta · no sustituye ejecución con hardware")
        if ci == "failure_or_cancelled":
            return esc("CI al HEAD fallida · no promover")
        return esc("CI en rama predeterminada no confirmada · no implica fallo")

    def story_card(project: dict, label: str) -> str:
        return ('<div class="pf-project-summary"><span class="pf-mini">' +
                esc(label) + '</span><h3>' + esc(project["title"]) +
                '</h3><p>' + esc(project["solution"]) +
                '</p><span class="pf-tech">' + esc(project["field"]) + '</span></div>')

    slides = [
        page("closure-cover",
             '<div class="pf-line"></div>'
             '<p class="pf-eyebrow">PORTFOLIO MAESTRO · SELECCIÓN EDITORIAL V4</p>'
             '<h1>Ingeniería que se puede explicar y comprobar.</h1>'
             '<p class="pf-cover-subtitle">Tres casos principales y dos complementarios. '
             'Actividad reciente como contexto, no como medida de valor profesional.</p>'
             '<div class="pf-status">SELECCIÓN FIJADA · PUBLICACIÓN NO AUTORIZADA</div>'
             '<p class="pf-bottom-note">' + esc(stamp) +
             ' · Repositorios públicos únicamente; otros trabajos fuera de inventario.</p>',
             "Selección editorial estable, con revisión funcional pendiente."),
        page("closure-map",
             '<div class="pf-meta">01 / ESTRUCTURA EDITORIAL</div>'
             '<h2>Una selección por utilidad, alcance y evidencia.</h2>'
             '<p class="pf-lead">Los commits semanales no eliminan casos profesionales consolidados.</p>'
             '<div class="pf-two">' +
             "".join(story_card(p, "CASO PRINCIPAL") for p in main[:2]) +
             '</div><div class="pf-two">' +
             "".join(story_card(p, "IA E INVESTIGACIÓN" if p["repo"].endswith("GuiaIA")
                                  else "COMPLEMENTARIO") for p in main[2:] + supporting[:1]) +
             '</div><p class="pf-bottom-note">ATM10 complementa esta selección; '
             'AUTOMATON sigue fuera de la edición principal por CI fallida.</p>',
             "Orden profesional propuesto basado en casos documentados."),
    ]
    for index, project in enumerate(main, 1):
        bullets = "".join('<div class="pf-card"><span class="pf-mini">CAPACIDAD DOCUMENTADA</span>'
                          '<p>' + esc(value) + '</p></div>'
                          for value in project["contributions"][:3])
        refs = "".join(source_link(project, item) for item in project["evidence"][:2])
        slides.append(page(
            "closure-main",
            '<div class="pf-meta">0' + str(index + 1) + ' / CASO PRINCIPAL</div>'
            '<h2>' + esc(project["title"]) + '</h2>'
            '<p class="pf-lead">' + esc(project["problem"]) + '</p>'
            '<div class="pf-two">' +
            '<div class="pf-card pf-card-accent"><span class="pf-mini">SOLUCIÓN</span>'
            '<p>' + esc(project["solution"]) + '</p></div>' +
            '<div class="pf-card"><span class="pf-mini">VALOR DEL CASO</span>'
            '<p>' + esc(project["takeaway"]) + '</p></div></div>'
            '<div class="pf-two">' + bullets[:6000] + '</div>'
            '<div class="pf-evidence-grid"><div><span class="pf-mini">ESTADO</span>'
            '<p class="pf-limit">' + evidence_label(project) + '</p>'
            '<p class="pf-limit">' + esc(project["limits"]) + '</p></div>'
            '<div class="pf-evidence-list">' + refs + '</div></div>',
            "Historia principal documentada, pendiente de validación funcional.",
            project["repo"]))
    for index, project in enumerate(supporting, start=5):
        refs = "".join(source_link(project, item) for item in project["evidence"][:1])
        slides.append(page(
            "closure-supporting",
            '<div class="pf-meta">0' + str(index) + ' / CASO COMPLEMENTARIO</div>'
            '<h2>' + esc(project["title"]) + '</h2>'
            '<p class="pf-lead">' + esc(project["problem"]) + '</p>'
            '<div class="pf-two"><div class="pf-card pf-card-accent">'
            '<span class="pf-mini">SOLUCIÓN</span><p>' + esc(project["solution"]) +
            '</p></div><div class="pf-card"><span class="pf-mini">APORTACIÓN</span>'
            '<p>' + esc(project["takeaway"]) + '</p></div></div>'
            '<div class="pf-two">' + "".join(
                '<div class="pf-card"><span class="pf-mini">APORTACIÓN DOCUMENTADA</span>'
                '<p>' + esc(item) + '</p></div>'
                for item in project["contributions"][:2]) + '</div>'
            '<div class="pf-evidence-list">' + refs + '</div>'
            '<p class="pf-limit">' + esc(project["limits"]) + '</p>',
            "Aportación complementaria con límites y fuentes explícitos.",
            project["repo"]))
    slides.append(page(
        "closure-exclusions",
        '<div class="pf-meta">07 / DESCARTES Y ALCANCE</div>'
        '<h2>Lo que decidimos no exagerar.</h2>'
        '<div class="pf-two"><div class="pf-card">'
        '<span class="pf-mini">PROYECTO EN SEGUIMIENTO</span>'
        '<h3>' + esc(excluded[0]["repo"].split("/")[-1]) + '</h3>'
        '<p>' + esc(excluded[0]["reason"]) + '</p></div>'
        '<div class="pf-card"><span class="pf-mini">UNIVERSO ANALIZADO</span>'
        '<p>' + esc(selection["scope_note"]) + '</p></div></div>'
        '<p class="pf-bottom-note">No se infiere rentabilidad, estabilidad, '
        'funcionalidad jugable ni compatibilidad industrial a partir de CI o README.</p>',
        "Exclusiones y alcance para impedir conclusiones falsas."))
    slides.append(page(
        "closure-gates",
        '<div class="pf-meta">08 / CIERRE DE SELECCIÓN, NO DE PUBLICACIÓN</div>'
        '<h2>Contenido seleccionado; evidencias de publicación pendientes.</h2>'
        '<div class="pf-two"><div class="pf-card pf-card-accent">'
        '<span class="pf-mini">SELECCIÓN EDITORIAL</span>'
        '<p>Tres casos principales, dos complementarios y un laboratorio excluido. '
        'Se preservan los dos casos del portfolio anterior.</p></div>'
        '<div class="pf-card"><span class="pf-mini">SIGUIENTE PUERTA</span>'
        '<p>Contrastar resultados funcionales, atribución del trabajo y capturas '
        'autorizadas antes de sustituir el PDF oficial.</p></div></div>'
        '<p class="pf-bottom-note">No publicar automáticamente. Las métricas '
        'tomadas de README/AUDIT_REPORT son declaradas, no recalculadas aquí.</p>',
        "La decisión de inclusión está fijada pero la publicación requiere QA independiente."))
    return [{**slide, "markup": slide["markup"] + DISCLAIMER} for slide in slides]


def render() -> dict:
    selection = yaml.safe_load(SELECTION.read_text(encoding="utf-8"))
    release = json.loads(RELEASE.read_text(encoding="utf-8"))
    portfolio = load_portfolio()
    if not EVIDENCE.is_file() or EVIDENCE.is_symlink():
        raise ValueError("Falta auditoría CI independiente para el PDF V4")
    evidence_bytes = EVIDENCE.read_bytes()
    evidence = json.loads(evidence_bytes)
    statuses = validate_evidence_feed(evidence, selection, release)
    slides = build_slides(
        selection, release, portfolio, evidence=evidence,
        stamp=datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC"))
    markdown = render_markdown(slides)
    manifest = {
        "schema": 1, "visibility": "public",
        "source_selection_generated_at": release["selection_generated_at"],
        "selection_status": selection["status"],
        "main_cases": [p["repo"] for p in selection["main_cases"]],
        "supporting_cases": [p["repo"] for p in selection["supporting_cases"]],
        "excluded_cases": [p["repo"] for p in selection["excluded_cases"]],
        "curated_portfolio_unchanged": True,
        "publication_approved": False, "automatic_publication": False,
        "ci_evidence_synced": True,
        "evidence_report_sha256": hashlib.sha256(evidence_bytes).hexdigest(),
        "observed_ci_by_repo": {repo: ci["status"] for repo, ci in sorted(statuses.items())},
        "slide_count": len(slides),
        "markdown_sha256": hashlib.sha256(markdown.encode("utf-8")).hexdigest(),
    }
    OUT.mkdir(parents=True, exist_ok=True)
    for target, content in (
        (MD, markdown),
        (MANIFEST, json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"),
    ):
        if target.is_symlink() or target.parent.resolve() != OUT.resolve():
            raise ValueError("Salida editorial fuera de carpeta controlada")
        target.write_text(content, encoding="utf-8")
    return manifest


if __name__ == "__main__":
    value = render()
    print("Selección editorial V4:", len(value["main_cases"]),
          "principales;", len(value["supporting_cases"]), "complementarios;",
          value["slide_count"], "páginas; sin publicación.")
