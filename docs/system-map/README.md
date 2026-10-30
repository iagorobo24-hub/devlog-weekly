# Project System Map (PSM) — devlog-weekly (Profile: LITE)

> **Perfil:** `LITE` | **Estado histórico:** `active`, **no recertificado en HEAD** | **Target Commit histórico inaccesible:** `97a4319bba38bb5a09cfe8be89e58ead54f028a9` | **Framework:** `0.2.0-alpha`

> **Revisión actual:** [Auditoría semántica y mecánica del 30/10/2026](./CURRENT-REVIEW-2026-10-30.md). La verificación de hoy no cambia los estados históricos del manifiesto ni certifica el PSM frente a un commit inaccesible.

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
- **INV-01-GITHUB-API-RATE-LIMIT-AWARE:** La recolección implementa reintentos acotados para límites de tasa; la caché de respuestas de la redacción histórica **no está acreditada** por el código actual.
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

## Evidencia operativa posterior (29-10-2026, sin refrescar `psm.source.commit`)

La ejecución GitHub Actions [#14](https://github.com/iagorobo24-hub/devlog-weekly/actions/runs/40792023387) completó `tests` (5/5), recolección pública (4/4 repos), síntesis (4/4 con `openai/gpt-oss-20b` como fallback), renderizado y publicación en Drive de PDF semanal, portfolio PDF y vídeo, seguido del commit de estado [e2b0ae8](https://github.com/iagorobo24-hub/devlog-weekly/commit/e2b0ae8f3b9c2a0eb6dc4fa3d9ed08e9154237fe).

Cambios operativos observados: `src/collect.py` falla al no acceder a cualquier repo y bloquea repositorios privados; `src/synthesize.py` no permite que una síntesis parcial avance a publicación; el workflow usa `GITHUB_TOKEN` para los cuatro repos públicos y requiere tests antes del pipeline; `src/publish.py` admite credenciales opcionales de cliente OAuth propio vía entorno.

**Validación PSM:** esta evidencia comprueba el flujo principal, no certifica todas las invariantes ni la deriva histórica contra `97a4319`. Sigue pendiente reconciliar el baseline existente, validar gestión de rate limits y completar la migración OAuth de Drive. No se modifica `manifest.yaml` ni el commit de fuente auditada.

### Separación de CI, cron y generación histórica (29-10-2026)

Se incorpora `src/backfill.py` como nueva entrada de consulta pública
(sin escritura sobre `state/` o Drive), `ci.yml` para pruebas aisladas
en push/PR y `backfill.yml` para obtener archivos descargables.
El flujo semanal mantiene cron/disparo manual y serialización mediante
concurrency, con el único permiso de escritura reservado al job de
persistencia. La cronología histórica no depende de narrativas actuales.

**PSM:** registro de cambio material para revisión posterior.
No se actualiza `manifest.yaml` ni se afirma certificar la línea base
antigua hasta ejecutar reconciliación y validación suficiente.

### Archivo histórico duradero (29-10-2026)

`src/publish_backfill.py` valida manifiesto y existencia de todos los
archivos antes de publicar en ruta separada `Portfolio/historico-verificable/`.
La subida es inmutable: no reemplaza los resultados del cron. Este cambio
amplía el dominio `dom-publisher` sin cambiar la línea base auditada.


### Cambio material de informes: revisión P0 y P1 (octubre 2026)

- El histórico src/backfill.py pagina de manera determinista todos
  los eventos y conserva vínculos verificables.
- src/synthesize.py incorpora SHA/fecha en el contexto del LLM,
  controles de coherencia temporal y fuentes desde eventos reales.
- src/render.py reduce páginas de repos sin actividad, añade resumen
  objetivo y reparte textos largos entre diapositivas.
- src/render_master.py normaliza saltos literales sin alterar el estado.
- El workflow histórico impide subidas a Drive sin opt-in explícito.
  CI admite muestras visuales independientes de producción.

No se actualiza manifest.yaml ni se certifica el PSM histórico con
commit fuente inaccesible. Las pruebas de PDF y la revisión manual de
las narrativas siguen siendo condiciones de aceptación.

### Mitigación de rate limits en recolección — 2026-10-30 (sin recertificar PSM)

La recolección semanal y el histórico vuelven a consultar **el repositorio completo**
si GitHub devuelve 429 o un 403 identificable como límite de tasa. El mecanismo
respeta `Retry-After`, `X-RateLimit-Remaining` y `X-RateLimit-Reset`
(incluso cuando aparecen simultáneamente), realiza backoff exponencial y limita
los reintentos a tres y la espera acumulada a 60 segundos. Si faltan
cabeceras fiables, se espera al menos 60 segundos antes de un primer reintento;
si la siguiente espera exponencial excede el presupuesto, se aborta. Si la API requiere
más tiempo, o el límite persiste, la operación falla expresamente: no crea
un snapshot incompleto, no publica y no confirma `state/last_run.json`.

Los 401/403 de permisos que **no** indican rate limit no se reintentan. El
tratamiento anterior de errores de comparación, lenguajes y README sigue
permitiendo la ausencia legítima, pero ya no disfraza los límites de tasa
como estadísticas o contenido vacíos. Comprobación local: casos sintéticos
reproducibles en `tests/test_collector_rate_limits.py`, además de regresión
integrada; **no** se han inducido límites de tasa reales sobre GitHub.

La línea base del mapa continúa inaccesible; `psm.source.commit` y
`verified_at` no se actualizan. El resto de `INV-01` (incluida la supuesta
caché de respuestas) **no queda certificado** por estos tests.

### Confirmación única y coherencia del cursor semanal (30-10-2026)

La recolección declara `github_run_id` en GitHub Actions. La síntesis
conserva ese identificador y un `source_collected_sha256` de los bytes
exactos utilizados. `src/confirm_pipeline_state.py` comprueba ambos
resultados y las ventanas de cada repositorio respecto a `config/repos.yml`
antes de confirmar `state/last_run.json` y `state/narrative/*.md`.
Rechaza resultados de otro run, nombres ausentes o duplicados, regresiones
de fecha y narrativas vacías. El workflow semanal usa una sola confirmación;
los antiguos flags `--commit-state` delegan en ese mismo validador.

Las escrituras se preparan antes de reemplazar archivos; los fallos de E/S
ordinarios tienen rollback ensayado con datos sintéticos. Esto **no**
equivale a una transacción atómica entre varios archivos frente a la caída
súbita del proceso: el workflow solo intenta el commit/push de Git después
de que la confirmación complete correctamente. No se han actualizado
manifiestos PSM antiguos ni publicado artefactos.


### Orden final de publicación y recuperación ante E/S — 2026-10-30

El cron confirma `state/` **después** de publicar el PDF semanal y
completar la generación y publicación del portfolio maestro (cuando proceda).
De este modo no mueve el cursor ni reescribe las narrativas si el maestro
falla. Las publicaciones externas anteriores al error pueden haberse
realizado: el flujo no garantiza transacciones remotas entre Drive y Git.

Si falla una escritura local y también falla el rollback, el sistema
**conserva los respaldos anteriores** en ficheros temporales restringidos
(`0600`) y señala sus rutas para recuperación manual. Ya no elimina
las únicas copias recuperables. Las pruebas inyectan ambos fallos y verifican
los bytes previos. No se ha ensayado una desconexión eléctrica real ni se
afirma atomicidad de varias escrituras frente a caída súbita.

### Publicación semanal y maestra comprobada — 2026-10-30

La publicación de `out/deck.pdf` utiliza una versión inmutable bajo
`Portfolio/semanal/<semana-ISO>/versions/<run-id>-<attempt>/devlog.pdf`.
Antes de sustituir el alias `Portfolio/semanal/<semana-ISO>/devlog.pdf`,
descarga la versión y comprueba su SHA-256 frente al PDF local; después
descarga el alias para contrastarlo de nuevo. En GitHub Actions el
identificador procede de `GITHUB_RUN_ID` y `GITHUB_RUN_ATTEMPT`.
La ejecución manual sin esas variables utiliza un identificador temporal
distinto (sin hacer que `--dry-run` publique nada).

El portfolio maestro V2 conserva la verificación de versiones y ahora
comprueba también los alias PDF/vídeo/subtítulos tras actualizarlos.
Los archivos fuente se revisan antes de cualquier escritura remota y se
contrastan otra vez con sus hashes iniciales. Ante una discrepancia la
publicación se considera fallida y el workflow **no confirma el estado**.

**Límites:** varias escrituras remotas no son una transacción atómica;
una actualización de alias que falla durante o después del reemplazo puede
haber cambiado parte de Drive. Las versiones ya verificadas se conservan
para recuperación; no hay reversión automática de alias remotos. Las
pruebas incluyen simulación de fallos de Drive y una comprobación
de escritura/lectura real con rclone sobre un backend **local temporal**,
sin red ni acceso a Google. Falta una comprobación real de lectura/escritura
en Google Drive con las credenciales OAuth propias del titular.
El portfolio editorial V4 sigue sin autorización de publicación.

### Puerta de prepublicación y verificación de baseline PSM (30-10-2026)

Antes de renderizar o publicar un devlog semanal, el workflow ejecuta
`python -m src.confirm_pipeline_state --check-only`. Reutiliza **el mismo
validador** que la confirmación final: comprueba el conjunto exacto de
repositorios, ventanas, identificador de ejecución, SHA-256 entre recolección
y síntesis, destino de los archivos de estado y retrocesos de fechas.
No escribe `state/` ni realiza ninguna operación en Drive. Si detecta
datos inconsistentes, bloquea el renderizado y la publicación, en vez de
actualizar Drive para descubrir el error durante el cierre. La confirmación
definitiva se ejecuta después de publicar, y vuelve a validar la entrada.

**Incidencia PSM confirmada:** la consulta a la API oficial GitHub
`GET /repos/iagorobo24-hub/devlog-weekly/commits/97a4319bba38bb5a09cfe8be89e58ead54f028a9`
devuelve `422 No commit found for SHA`. La copia Git aislada tampoco tiene
ese objeto. No se puede reconstruir una auditoría de deriva a partir de un
commit de procedencia inaccesible; el resultado es
`RECONCILIATION_REQUIRED / BASE_COMMIT_NOT_FOUND`. El mapa sigue siendo
**histórico**, no certificado contra el HEAD. No se cambian
`psm.source.commit`, `verified_at`, `status` ni las etiquetas de evidencia.
La reconciliación futura debe partir de un baseline recuperado o de una nueva
auditoría semántica exhaustiva sobre una revisión validada y confirmada.

### Procedencia comprobable del PDF semanal — 30-10-2026

El render semanal ahora genera `out/deck-provenance.json` **solo después**
de que Marp produzca un PDF válido. Registra hashes SHA-256 de los bytes
exactos de `out/summaries.json`, `out/deck.md`, `out/deck.pdf`,
`templates/deck.md.j2` y `templates/theme.css`, además de la
marca `generated_at` y el `github_run_id` de la síntesis.

Si el render falla, si se utiliza `--no-pdf` o se repite sin llegar a
producir el PDF, la atestación anterior se invalida. Antes de cualquier
escritura remota del **PDF semanal**, `src/publish.py` comprueba que el
manifiesto y los archivos siguen coincidiendo; en Actions comprueba además
el ID de ejecución. Un PDF anterior, una plantilla editada o una síntesis
posterior no pasan por un simple archivo válido o por el resultado exitoso
de `rclone`. Se rechazan las rutas de artefactos mediante enlaces simbólicos
en el punto de renderizado, y un manifiesto enlazado en la verificación.

Esta comprobación detecta mezclas y modificaciones **accidentales**.
No es una firma digital ni protege contra un actor con permisos para
reescribir simultáneamente todos los archivos locales y el propio
manifiesto. No supone autorización para publicar el editorial V4
ni certificación del PSM histórico.

### Extensión de procedencia hasta la recolección original — 2026-10-30

La acreditación de PDF semanal incorpora ahora los bytes exactos de
`out/collected.json`. Antes de renderizar y **otra vez antes de publicar**,
`src/deck_provenance.py` compara su SHA-256 con el
`source_collected_sha256` de la síntesis; comprueba también fecha de
generación, ID de ejecución, cobertura de repositorios, nombres únicos y
ventanas por repositorio. El manifiesto `out/deck-provenance.json` añade
`digests.collected` y el SHA de origen declarado, vinculando
recolección → síntesis → plantilla → Markdown → PDF. Si la recolección se
edita después del preflight, la publicación se rechaza antes de contactar
Drive. Las comprobaciones son de integridad local, no firma criptográfica
contra un atacante que controle todos los archivos. El gate editorial V4 y
la aprobación del propietario siguen fuera de esta automatización.

### Cierre de publicación master V2 con recibo de generación — 2026-10-30

La generación del portfolio maestro invalida al comienzo cualquier recibo
anterior `out/portfolio-master-release-proof.json`. Si no hay actividad
showcase, si falla el renderizado o si alguno de los controles de calidad
rechaza PDF, vídeo o subtítulos, **no se emite recibo**. Un conjunto
residual de `portfolio.pdf/.mp4/.srt` ya no puede superar por sí solo el
paso de publicación V2.

Cuando `run_portfolio_v2.prepare()` termina correctamente, registra un
recibo con el `GITHUB_RUN_ID` (cuando existe) y SHA-256 de siete elementos:
fuente editorial YAML, manifiesto y Markdown V2, CSS, PDF, MP4 y SRT.
El publicador, antes de cualquier operación sobre Drive, recomputa todas
esas huellas y exige el recibo de **esa misma ejecución**. El chequeo es
independiente de la integridad posterior de las versiones remotas.

**Límites explícitos:** el recibo es evidencia local de procedimiento,
no firma contra un actor con escritura completa del directorio. No resuelve
la atomicidad de las tres rutas públicas en Drive: si la actualización
remota se interrumpe, los alias podrían quedar mezclados, aunque la
publicación termine con error y el estado Git no avance. No se ha probado
contra Google Drive real; tampoco implica aprobación del editorial V4.

### Recuperación por puntero de publicación V2 — 30-10-2026

Existe una ruta recuperable `Portfolio/master/current.json`, escrita
después de verificar los tres alias; apunta a versiones inmutables de
PDF, MP4 y SRT con hash por archivo. Los lectores que necesitan un conjunto
coherente deben seguir el puntero, no los tres alias mutables.
El procedimiento de recuperación comprobable y sus limitaciones están
descritos en [Recuperación del portfolio maestro](../master-release-recovery.md).
Esto **no** hace atómica la sustitución de alias en Google Drive.
