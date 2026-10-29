# Decisión de evidencias públicas — 29 de octubre de 2026

**Revisión editorial interna. No cambia el portfolio publicado.**

Se han contrastado los commits actuales de las cinco ramas predeterminadas
con GitHub. Se han consultado las rutas citadas por las cinco fichas y
ejecuciones públicas de GitHub Actions cuando existen. El hecho de que
un archivo esté en el repositorio **no** verifica el funcionamiento que
describe; una CI correcta tampoco equivale a pruebas con hardware,
simuladores o clientes de juego reales.

| Proyecto | Revisión | Evidencia externa contrastada | Decisión editorial provisional |
|---|---|---|---|
| TIA Portal RocaRoibas | `5bb539729772` en `master` | [Run de CI correcta al SHA](https://github.com/iagorobo24-hub/T-IA-Portal-RocaRoibas/actions/runs/40892526988) | Prioridad de revisión; ninguna certificación real de TIA/PLCSIM |
| GuiaIA | `685bd6d1f614` en `main` | QA de ramas feature separada de main, p. ej. [run](https://github.com/iagorobo24-hub/GuiaIA/actions/runs/40892081888) | Alta prioridad estratégica, **no** jugabilidad verificada en main |
| ATM10 Sky es_es | `1e0c648aafbf` en `main` | [Informe estático](https://github.com/iagorobo24-hub/atm10sky-es-es-localization/blob/1e0c648aafbf0204de1eaa2a191bcb7faf13b8c1/AUDIT_REPORT.md), archivo localizado; no constan runs de Actions | Candidato documental y visual; la candidata 191 necesita QA final |
| Awesome TIA Portal | `656213a21eed` en `main` | [Catálogo](https://github.com/iagorobo24-hub/awesome-tia-portal/blob/656213a21eed2646ff85ee0e330e6e1747bbc2d5/CATALOG.md) y [matriz](https://github.com/iagorobo24-hub/awesome-tia-portal/blob/656213a21eed2646ff85ee0e330e6e1747bbc2d5/MATRIZ-TRAZABILIDAD.md); run `dynamic` al HEAD, no push | Candidato técnico; reconciliar cifras y comprobar recursos individuales |
| AUTOMATON | `710179ba1d4d` en `main` | [CI fallida en HEAD](https://github.com/iagorobo24-hub/AUTOMATON/actions/runs/40444662334) y defectos descritos en README | Bloqueado para promoción hasta diagnóstico y correcciones |

## Corrección de interpretación de CI

La ficha de TIA Portal citaba `.github/workflows/ci.yml` y el
constructor la etiquetaba como `is_independently_verified=true` con
solo una señal `success_at_head`. Ese enlace muestra la **definición**
del workflow, no su ejecución. La versión corregida:

1. Mantiene las referencias al archivo de fuente versionado como evidencia
   **estructural no verificada semánticamente**.
2. Añade, separadamente, el URL de ejecución de CI para ese repositorio y
   HEAD, únicamente con estado exitoso, recuento de runs positivo y URL
   canónico del repositorio.
3. Rechaza URLs externas, de otro repositorio o malformadas y advierte
   cuando falta el enlace; nunca convierte CI en validación funcional.
4. Mantiene las cinco fichas como `draft_only` y las tres puertas de
   publicación obligatorias.

## Pendientes para selección y publicación

- Regenerar la cadena de auditoría pública programada con un inventario
  nuevo; la regresión de CI no ejecuta automáticamente ese workflow.
- Validar los comportamientos más importantes en entornos reales o con
  evidencias independientes, especialmente TIA, GuiaIA y ATM10.
- Revisar visualmente la comparativa completa y cerrar el reparto de
  espacio con aprobación explícita del propietario.
- No presentar AUTOMATON como aplicación estable ni usar cifras de
  Awesome TIA Portal hasta reconciliar su documentación contradictoria.

**Resultado:** decisión de prioridad preliminar, no aprobación definitiva.
