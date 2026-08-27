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
