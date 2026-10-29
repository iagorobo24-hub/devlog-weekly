# Cobertura editorial pública — 29/10/2026

**Documento de trabajo: NO PUBLICAR como portfolio final.**

La selección pública contenía cinco candidatos activos, pero sólo dos
tenían ficha versionada. Esta fase incorpora tres fichas adicionales,
sin alterar los dos proyectos aprobados del Portfolio Maestro ni los
controles de publicación.

| Candidato | SHA de referencia | Evidencia documental | Límites de revisión |
|---|---|---|---|
| TIA Portal RocaRoibas | `5bb539729772` | README, tests y workflow CI | CI no implica funcionamiento real de TIA/PLCSIM |
| GuiaIA | `685bd6d1f614` | README y tests presentes en main | QA verde de ramas *feature* no equivale a CI en main ni funcionalidad jugable |
| ATM10 Sky es_es | `1e0c648aafbf` | README, AUDIT_REPORT.md, es_es.snbt | Candidata 191 sin inspección visual exhaustiva; resultados estáticos no recalculados |
| AUTOMATON | `710179ba1d4d` | README, ARCHITECTURE.md, frontend/package.json | Defectos admitidos, CI no satisfactoria, sin operaciones reales ni resultados de rentabilidad probados |
| Awesome TIA Portal | `656213a21eed` | README, CATALOG.md, MATRIZ-TRAZABILIDAD.md | Mayoría de recursos documentados, no importables; cifras de verificación a reconciliar |

## Fuentes comprobadas

La existencia de los archivos citados se contrastó en GitHub público
bajo cada SHA fijo. Esa existencia no certifica la exactitud de las
afirmaciones del autor, la compilación o el comportamiento real.

- [ATM10: README](https://github.com/iagorobo24-hub/atm10sky-es-es-localization/blob/1e0c648aafbf0204de1eaa2a191bcb7faf13b8c1/README.md) y [AUDIT_REPORT.md](https://github.com/iagorobo24-hub/atm10sky-es-es-localization/blob/1e0c648aafbf0204de1eaa2a191bcb7faf13b8c1/AUDIT_REPORT.md).
- [AUTOMATON: README](https://github.com/iagorobo24-hub/AUTOMATON/blob/710179ba1d4de55c6ed3a81776d1521ad9581d09/README.md) y [ARCHITECTURE.md](https://github.com/iagorobo24-hub/AUTOMATON/blob/710179ba1d4de55c6ed3a81776d1521ad9581d09/ARCHITECTURE.md).
- [Awesome TIA Portal: catálogo](https://github.com/iagorobo24-hub/awesome-tia-portal/blob/656213a21eed2646ff85ee0e330e6e1747bbc2d5/CATALOG.md) y [matriz](https://github.com/iagorobo24-hub/awesome-tia-portal/blob/656213a21eed2646ff85ee0e330e6e1747bbc2d5/MATRIZ-TRAZABILIDAD.md).

## Criterio de cierre de esta fase

1. Las cinco fichas públicas son sólo borradores, no promociones.
2. Cada afirmación tiene archivo referenciado en un SHA y pasa el
   comprobador de presencia del pipeline al ejecutar una revisión.
3. El deck editorial separado puede incluir las cinco fichas, conservando
   íntegros los dos proyectos ya aprobados.
4. Sin prueba funcional independiente, capturas autorizadas y aprobación
   del propietario, el portfolio de producción permanece inalterado.

**Pendiente:** ejecutar el pipeline público completo con un snapshot nuevo
(y, cuando haya acceso a Penguin, exportar y revisar visualmente su PDF).
La CI del commit prueba los contratos locales; no sustituye las consultas
de fuentes en vivo de la revisión programada.
