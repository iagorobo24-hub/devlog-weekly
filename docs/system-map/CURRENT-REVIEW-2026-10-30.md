# PSM — revisión independiente del estado actual (30/10/2026)

**Alcance:** copia aislada del repositorio `iagorobo24-hub/devlog-weekly`
en base `main@2f79343ea2fd9fdfd613f3fe81ac3d34cf20136a`,
más los cambios locales aún **sin commit ni publicación**.
Inspección de archivos y contratos, auditoría pública de GitHub y
pruebas del pipeline previamente ejecutadas. No se ha accedido a secretos
ni se ha ejecutado el cron real en esta revisión.

## Dictamen

| Elemento | Clasificación | Evidencia y límite |
| --- | --- | --- |
| Baseline histórico del PSM | **BLOQUEADO** | `97a4319bba38bb5a09cfe8be89e58ead54f028a9` no es objeto local; GitHub REST `GET /repos/iagorobo24-hub/devlog-weekly/commits/{sha}` respondió **HTTP 422 No commit found** el 30/10/2026. No se puede calcular deriva contra ese origen |
| Alcance de dominios | **DESACTUALIZADO** | Los cuatro dominios descritos en `manifest.yaml` sí resuelven a archivos, pero ya existen selección editorial, confirmación y procedencia con contratos independientes |
| Invariante 01, rate limits | **PARCIALMENTE VERIFICADO** | `src/collect.py` gestiona 429/403 de límite, `Retry-After` y `X-RateLimit-Reset`, con ensayos de inyección en `tests/test_collector_rate_limits.py`. La documentación anterior aseguraba que también **cachea respuestas**, cosa no demostrada por el código; no se encontró un mecanismo explícito de caché. No se provocó rate limit real |
| Invariante 02, render determinista | **VERIFICADO PARA ESTRUCTURA Y MARKDOWN; NO PARA BYTES PDF** | `render.render_markdown` construye la estructura desde síntesis y plantilla fijas. Se verificó render real con Marp/Chromium, pero los metadatos, versión del navegador, fuentes y fecha pueden impedir identidad byte a byte del PDF sin un experimento adicional |
| Invariante 03, sin secretos estáticos | **COMPROBACIÓN PARCIAL, NO AUDITORÍA DE SECRETOS** | API GitHub y NVIDIA se leen de variables de entorno o credenciales autorizadas, Drive usa `RCLONE_CONF` y variables opcionales. Un escaneo de patrones literales comunes en `src/`, `config/` y workflows no encontró coincidencias; eso no prueba ausencia de secretos en todas las formas |
| Cobertura semanal | **VERIFICADO LOCALMENTE** | Siete repositorios públicos configurados; collector PyGithub real 7/7, vista previa con tres activos y cuatro sin avances sustanciales. `state/last_run.json` sin cambios |
| Estado/publicación | **VERIFICADO LOCALMENTE; PRODUCCIÓN PENDIENTE** | `src/confirm_pipeline_state.py`, `src/deck_provenance.py`, `src/master_release_provenance.py`, `src/publish.py`. Hay SHA-256, preflight, versiones inmutables, puntero `current.json` para recuperación. Comprobado con rclone **local**, no Drive real |

### Mapa de dominios observado en el código

1. **Ingesta pública:** `config/repos.yml` → `src/collect.py` → `out/collected.json`. Los errores reales de GitHub bloquean resultados parciales. `src/backfill.py` ofrece archivo histórico separado.
2. **Síntesis:** `src/synthesize.py` → `out/summaries.json`; filtra mantenimiento/PSM como avance y retiene referencias verificables. NVIDIA solo fue probado con datos reales en un run remoto anterior; los cambios recientes usan simulación de IA.
3. **Render semanal:** `src/render.py`, `templates/` y `src/deck_provenance.py` → Markdown, PDF y manifiesto de hashes asociados al JSON original.
4. **Estado y cierre:** `src/confirm_pipeline_state.py` valida cobertura, intervalos, run id y digest antes de preparar escritura del estado. El workflow confirma **después** de publicación, con rollback ordinario pero sin transacción de múltiples archivos frente a apagado.
5. **Publicación:** `src/publish.py` verifica PDF semanal y portfolio maestro V2 antes de publicar con rclone. Mantiene alias clásicos no atómicos y un puntero de recuperación `Portfolio/master/current.json` a versiones inmutables.
6. **Portfolio maestro:** `src/run_portfolio_v2.py`, `src/render_portfolio_v2.py`, `src/render_video_v2.py`, `src/master_release_provenance.py` y checks de PDF/vídeo/subtítulos. V2 sigue usando fichas congeladas de dos proyectos. La propuesta V4 no está aprobada.
7. **Selección y evidencia editorial:** `src/project_selection_core.py`, `src/select_projects.py` y controles de calidad/perfiles. Las vistas previas de candidatos no promocionan automáticamente proyectos al PDF maestro. La partición privada permanece separada del cron público.

Los puntos 4, 6 y 7 no están representados adecuadamente como contratos
independientes en el manifiesto antiguo. Se recomienda actualizar la
topología **al certificar una nueva línea base real**, no atribuir
`VERIFIED` retrospectivamente a un commit inaccesible.

### Credenciales y despliegue remoto

Lectura de los **nombres**, sin sus valores, de secretos GitHub Actions:
`GH_PAT`, `NVIDIA_API_KEY`, `RCLONE_CONF`.
No se encontraron secretos independientes llamados
`RCLONE_DRIVE_CLIENT_ID` y `RCLONE_DRIVE_CLIENT_SECRET`.
**Importante:** `RCLONE_CONF` puede contener configuración de OAuth
propia, lo cual no se puede inferir solo de sus nombres; sigue pendiente
comprobarlo con una prueba de Drive autorizada.

La última CI de `main` consultada figura correcta, pero es anterior
al parche local. No se conocen los minutos disponibles de GitHub Actions:
la API de facturación devolvió 404 por falta de alcance `user`.
No se ejecutó ninguna acción de escritura ni workflow de prueba.

### Condición para cerrar definitivamente la reconciliación

Mantener por ahora en `manifest.yaml` los **valores históricos**
`psm.source.commit`, `psm.verified_at`, `psm.status`,
`psm.coverage` y estados por dominio; no inferir su validez presente.
Después de integrar y probar el código propuesto:

1. Recuperar con evidencia el commit original, **o** declarar
   formalmente no recuperable esa baseline y hacer una auditoría
   de línea base nueva desde un SHA real alcanzable.
2. Rehacer mapa, invariantes y coberturas en función de los siete
   dominios efectivos; distinguir controles sintéticos, pruebas
   locales y validación de producción.
3. Ejecutar tests, reconstrucción del parche, inspección de workflow,
   controles editoriales y una validación externa donde corresponda.
4. Solo después actualizar en un cambio explícito y trazable el
   manifiesto y sus estados de evidencia. Ninguna etiqueta `VERIFIED`
   debe usarse para ocultar las pruebas pendientes.

**Cierre de esta revisión:** inventario y deriva semántica del estado
local auditados; reconciliación histórica **no completada**.

## Anexo: reproducibilidad de Python (30/10/2026)

La candidata local incluye `uv.lock` y los nueve pasos `uv sync` de
los seis workflows han pasado a `uv sync --locked`. Se verificó
resolución de 39 paquetes, ejecución local de 408/408 tests con ese
grafo y rechazo de un lock obsoleto inyectado en un directorio
temporal. No se certifican todavía dependencias externas de
`npm`/Marp, `rclone`, `ffmpeg` o extras `--with pymupdf`.
No hubo gasto de CI.
