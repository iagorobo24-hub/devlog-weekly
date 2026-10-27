# Project System Map (PSM) — devlog-weekly (Profile: LITE)

> **Perfil:** `LITE` | **Estado:** `active` | **Target Commit:** `97a4319bba38bb5a09cfe8be89e58ead54f028a9` | **Framework:** `0.2.0-alpha`

Memoria arquitectónica canónica de **devlog-weekly**: herramienta CLI y cron semanal en Python que analiza la actividad de repositorios GitHub y genera resúmenes y decks de portfolio.

---

## 1. Propósito y Estructura del Sistema

El sistema automatiza el pipeline de generación de devlogs:
1. **Recolección:** Consulta periódica de eventos de Git/GitHub (commits, pull requests, releases).
2. **Síntesis:** Extracción estructurada de hitos técnicos con modelos LLM.
3. **Renderizado:** Generación determinista de diapositivas y assets de vídeo.
4. **Publicación:** Exportación y distribución automatizada.

---

## 2. Catálogo de Componentes / Dominios

| Dominio | Responsabilidad Principal | Rutas Clave | Entrypoints |
|---|---|---|---|
| **`dom-github-collector`** | Recolección de actividad semanal de repositorios mediante GitHub API. | `src/collect.py` | `python -m src.collect` |
| **`dom-ai-synthesizer`** | Análisis semántico y resumen de hitos técnicos con LLM. | `src/synthesize.py` | `python -m src.synthesize` |
| **`dom-deck-renderer`** | Renderizado de diapositivas, layouts visuales y vídeos. | `src/render.py`<br/>`src/render_master.py`<br/>`src/render_video.py`<br/>`templates/` | `python -m src.render` |
| **`dom-publisher`** | Distribución y publicación de artefactos generados. | `src/publish.py` | `python -m src.publish` |

---

## 3. Invariantes y Reglas No Negociables

Las invariantes se detallan en [`invariants.md`](./invariants.md):
- **INV-01-GITHUB-API-RATE-LIMIT-AWARE:** La recolección respeta límites de tasa y cachea respuestas.
- **INV-02-DETERMINISTIC-DECK-OUTPUT:** Las plantillas de renderizado producen salidas idempotentes ante datos idénticos.
- **INV-03-NO-HARDCODED-SECRETS:** Los tokens de GitHub y claves API de IA se leen exclusivamente de variables de entorno.

---

## 4. Instrucciones de Enrutamiento para Agentes

- **Para orientación:** Consulte [`AGENTS.md`](../../AGENTS.md).
- **Antes de modificar código:** Invoque `psm-before-change`.
- **Al finalizar cambios:** Invoque `psm-maintain` para sincronizar documentación y verificar invariantes.

---

### Revisión remota de deriva — 2026-10-27

[Consultar el registro GitHub de cambios y validaciones pendientes](./REVIEW-2026-10-27.md). La revisión **no** recertifica el mapa al último HEAD; `psm.source.commit` y los estados de evidencia históricos permanecen sin modificación hasta completar reconciliación y validación independiente.
