"""Readable PUBLIC content proposal, intentionally not a portfolio PDF.

Uses only public verified metadata, provisional priorities and pinned
repository citations. It never accesses the local private reports.
"""
from __future__ import annotations

import json
from pathlib import Path

try:
    from src.select_projects import ROOT
    from src.strategic_selection import OUTPUT as STRATEGY
    from src.candidate_profiles import REPORT as DRAFTS
except ModuleNotFoundError:
    from select_projects import ROOT
    from strategic_selection import OUTPUT as STRATEGY
    from candidate_profiles import REPORT as DRAFTS

OUTPUT = ROOT / "out" / "portfolio-content-proposal.md"


def clean(s: object) -> str:
    value = str(s or "")
    return value.replace("|", r"\|").replace("\n", " ").replace("\r", " ").strip()


def render(strategy: dict, drafts: dict) -> str:
    if (strategy.get("visibility") != "public"
            or drafts.get("visibility") != "public"
            or strategy.get("automatic_publication") is not False
            or drafts.get("automatic_publication") is not False):
        raise ValueError("solo propuesta editorial pública sin publicación automática")
    for p in strategy.get("proposed_slate", []):
        if p.get("visibility") != "public" or p.get("publishable") is not False:
            raise ValueError("dato privado o publicado indebidamente")
    for d in drafts.get("drafts", []):
        if d.get("visibility") != "public" or d.get("publication_allowed") is not False:
            raise ValueError("borrador privado o autopublicado")
    for row in strategy.get("historical_watchlist", []):
        if row.get("visibility") != "public" or row.get("publishable") is not False:
            raise ValueError("seguimiento privado o publicado indebidamente")
    draft_map = {d["repo"]: d for d in drafts.get("drafts", [])}
    content = [
        "# Propuesta de contenido del Portfolio Maestro — NO PUBLICAR",
        "",
        "Selección pública preliminar basada en actividad, CI actual, pruebas y",
        "prioridades editoriales **provisionales**. No sustituye el PDF actual.",
        "Ni una CI correcta ni un README prueban por sí solos que el producto",
        "funcione de extremo a extremo.",
        "",
        "| Proyecto | Prioridad propuesta | CI en HEAD | Decisión editorial |",
        "|---|---:|---|---|",
    ]
    for p in strategy.get("proposed_slate", []):
        priority = f"{p['strategic_priority']}/5" if p.get("strategic_priority") is not None else "sin definir"
        content.append("| " + " | ".join((
            clean(p["title"]), priority, clean(p["ci_status"]), clean(p["editorial_tier"])
        )) + " |")
    historical = strategy.get("historical_watchlist", [])
    if historical:
        content += ["", "## Proyectos históricos que requieren evidencia nueva", "",
                    "No se consideran activos ni validados: se conservan para revisión,",
                    "sin reemplazar automáticamente los proyectos destacados.", "",
                    "| Proyecto | Prioridad propuesta | Motivo de seguimiento |",
                    "|---|---:|---|"]
        for item in historical:
            content.append("| " + " | ".join((
                clean(item["title"]),
                f"{item['strategic_priority']}/5",
                clean(item["watch_reason"]),
            )) + " |")
    content += ["", "## Fichas públicas preparadas", ""]
    for row in strategy.get("proposed_slate", []):
        draft = draft_map.get(row["repo"])
        if draft is None:
            continue
        content += [f"### {clean(draft['title'])}", ""]
        content += [
            f"- **Revisión Git fijada:** [{clean(draft['revision'][:10])}](https://github.com/{clean(draft['repo'])}/tree/{clean(draft['revision'])})",
            f"- **Estado:** {clean(row['editorial_tier'])}; no aprobado para publicación.",
        ]
        if draft.get("warnings"):
            content += ["- **Pendientes:** " + "; ".join(clean(w) for w in draft["warnings"])]
        content.append("- **Afirmaciones con referencias versionadas:**")
        for source in draft["sources"]:
            content.append(
                "  - " + clean(source["statement"]) + " — "
                f"[evidencia]({source['url']})"
            )
        content += ["", "Limitaciones: falta validación funcional y aprobación editorial,",
                    "incluso cuando los controles de CI del HEAD son correctos.", ""]
    content += [
        "## Pendiente antes de reemplazar el Portfolio Maestro",
        "",
        "1. Revisar importancia estratégica real y corregir prioridades propuestas.",
        "2. Contrastar funcionalidad y pruebas de extremo a extremo de cada candidato.",
        "3. Confirmar autorización y contenido para cualquier proyecto privado.",
        "4. Aprobar fichas, capturas y límites de lo que puede afirmarse públicamente.",
        "5. Generar vista previa PDF con el diseño ya estabilizado y revisar todas las páginas.",
        "",
        "No se ha consultado ni exportado ningún repositorio privado.",
        "",
    ]
    return "\n".join(content)


def main() -> None:
    strategy = json.loads(STRATEGY.read_text(encoding="utf-8"))
    drafts = json.loads(DRAFTS.read_text(encoding="utf-8"))
    result = render(strategy, drafts)
    if OUTPUT.is_symlink() or OUTPUT.parent.resolve() != (ROOT / "out").resolve():
        raise ValueError("ruta de salida no autorizada")
    OUTPUT.write_text(result, encoding="utf-8")
    print("Propuesta de contenido pública creada, sin PDF ni publicación.")


if __name__ == "__main__":
    main()
