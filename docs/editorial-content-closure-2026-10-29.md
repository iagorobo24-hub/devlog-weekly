# Cierre editorial público — 29 de octubre de 2026

**Estado: SELECCIÓN FIJADA, PUBLICACIÓN NO APROBADA.**

## Objetivo de esta revisión
Sustituir la clasificación basada en número de commits por una selección
de casos profesionales, con contenido que explica problema, solución,
aportación técnica, evidencia y límites.

### Selección editorial

1. **TIA Portal RocaRoibas** — caso principal de ingeniería industrial.
   README al SHA \`5bb539729772\`: dos MCP, reglas Openness/seguridad,
   44 scripts de pruebas declarados, aceptación PLCSIM reportada.
   CI al HEAD verde observada; no sustituye TIA/PLCSIM runtime.
2. **PFC Tools** — caso principal de aplicación web con siete módulos
   documentados, dashboard y gateway de IA. Se conserva aunque su
   actividad de commits no esté en la ventana de 30 días; no se afirman
   CI actual ni despliegue verificado.
3. **GuiaIA** — caso principal de I+D y sistemas agénticos: cuatro
   herramientas MCP de consulta/diagnóstico/propuesta que el README
   identifica en main; sin compañero jugable validado. Las ramas feature
   no se presentan como producto integrado.
4. **Awesome TIA Portal** — complementario: catálogo, contratos y
   matriz de trazabilidad; no se proclama compatibilidad general ni
   cifra de recursos operativos hasta resolver divergencias documentales.
5. **ATM10 Sky es_es** — complementario: traducción con métricas de
   cobertura y pruebas estáticas **reportadas** en README y AUDIT_REPORT;
   capturas previas a candidata 191, sin QA visual completa de esta.
6. **AUTOMATON** — no incluir en el portfolio principal: CI fallida en
   HEAD y defectos reconocidos por el repositorio; en seguimiento como
   laboratorio de simulación, no como producto listo.

## Verificación realizada
- Los seis repositorios son públicos; los seis SHA fijados coincidían
  con sus ramas predeterminadas el 29/10/2026.
- Se contrastó la información pública del README de TIA, GuiaIA,
  PFC Tools, Awesome TIA y ATM10; los informes de CI y las fuentes de
  candidato proceden del pipeline GitHub Actions del mismo día.
- Las cifras descritas en esos README son **reportadas**, no medidas
  de nuevo por esta auditoría.
- La propuesta se genera desde
  \`content/portfolio/editorial-selection-public.yml\`. Esta selección
  no cambia cada semana con el ranking de commits.
- El generador V4 incorpora enlaces anclados a SHA y declara explícitos
  los límites, y preserva \`content/portfolio/projects.yml\`.
- Se ha excluido cualquier trabajo fuera de los nueve repositorios
  públicos examinados; para incluir proyectos locales, privados o
  de clientes se necesita un inventario y autorización separados.

## Qué significa cierre

La **decisión editorial dentro del alcance público** queda congelada,
revisable ante nueva evidencia. No significa que los casos ya estén
aprobados para distribución externa. Faltan:

1. Contraste funcional independiente y atribución de autoría específica.
2. Evidencia visual real con permiso de uso; no presentar dibujos
   conceptuales como capturas.
3. Exportación PDF, inspección de todas las páginas y calidad de enlaces.
4. Aprobación explícita para reemplazar el portfolio de producción.

La CI correcta es un indicio de calidad automatizada en el SHA, nunca
una certificación de hardware, juego o despliegue.
