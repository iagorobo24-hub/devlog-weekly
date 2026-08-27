# AGENTS.md — Directrices para agentes de IA

## Misión del Proyecto

`devlog-weekly` es un pipeline automatizado en Python para recolectar la actividad de desarrollo semanal de los repositorios de GitHub del usuario, sintetizarla mediante IA y generar presentaciones y decks visuales.

## Convenciones y Ejecución

- Lenguaje: Python 3.11+
- Estructura modular en `src/`:
  - `src/collect.py`: Recolección de commits y PRs.
  - `src/synthesize.py`: Resumen semántico con LLM.
  - `src/render.py`, `src/render_master.py`, `src/render_video.py`: Renderizado visual.
  - `src/publish.py`: Publicación de reportes.

<!-- PSM:MANAGED_BLOCK:START (v0.2.0-alpha) -->
## Project System Map (PSM) Routing Instructions

- **Cold start / orientation request:** invoke `psm-orient` (or consult the System Map README at `docs/system-map/README.md` directly).
- **Before a material product change:** invoke `psm-before-change` and produce the Pre-Change Impact Contract first.
- **After code implementation:** invoke `psm-maintain`. `psm-maintain` coordinates the following when applicable:
  - `psm-host-docs` — host canonical-document synchronization.
  - `psm-validate` — final validation gate before any `psm.source.commit` refresh.
- `psm-validate` may be invoked independently at any time (CI, periodic audit, or explicit user request).

All five PSM skills (`psm-orient`, `psm-before-change`, `psm-maintain`, `psm-validate`, `psm-host-docs`) are available in this pack; the routing above prescribes when each is invoked.
<!-- PSM:MANAGED_BLOCK:END -->
