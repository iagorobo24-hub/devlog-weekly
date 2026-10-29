<div align="center">

<img src="docs/img/banner.svg" alt="devlog-weekly: de los commits de la semana a un deck de portfolio" width="100%">

<br>

![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)
![GitHub Actions](https://img.shields.io/badge/GitHub%20Actions-cron%20semanal-2088FF?logo=githubactions&logoColor=white)
![Marp](https://img.shields.io/badge/Marp-PDF-0288D1)
![NVIDIA NIM](https://img.shields.io/badge/LLM-NVIDIA%20NIM-76B900?logo=nvidia&logoColor=white)
![Estado](https://img.shields.io/badge/estado-uso%20personal-F5A623)

**Cada lunes lee la actividad de tus repositorios de GitHub, la resume con un modelo de lenguaje
y genera un deck semanal en PDF, más un deck «maestro» de portfolio con vídeo narrado.**
Corre en GitHub Actions y sube los resultados a Google Drive.

[Qué hace](#qué-hace) ·
[Cómo funciona](#cómo-funciona) ·
[Estado](#estado-del-proyecto) ·
[Inicio rápido](#inicio-rápido) ·
[Configuración](#configuración) ·
[Límites](#límites-conocidos)

</div>

---

## Qué hace

| | |
|---|---|
| 📥 **Recoge** | Por cada repo de `config/repos.yml`: commits, estadísticas de diff, issues y PRs cerrados, tags nuevos, lenguajes y el arranque del README. Sin IA. |
| 🧠 **Resume** | Una llamada al modelo por repo con actividad, con el historial ya contado para que escriba *qué cambió* y no *qué es el proyecto*. |
| 📄 **Deck semanal** | Plantilla fija (Jinja2 + Marp) con el texto del modelo: un PDF con los avances de la semana. |
| 🗂️ **Deck maestro** | Portfolio editorial V2 con casos de estudio, capturas, estado verificable y enlaces de evidencia por proyecto. |
| 🎙️ **Vídeo narrado** | Guiones por diapositiva, voz edge-tts y montaje FFmpeg con subtítulos SRT. |
| ☁️ **Publica** | Sube los PDF y el vídeo a Google Drive con `rclone`, en carpetas por semana ISO. |

Pensado para quien mantiene varios repositorios y quiere un registro semanal y un portfolio al día sin
escribirlos a mano. Es un proyecto personal: la configuración incluida apunta a los repositorios de su autor.

## Cómo funciona

<img src="docs/img/pipeline.svg" alt="Cadena semanal: recoger, sintetizar, renderizar y publicar. Cadena del deck maestro: maquetar, vídeo narrado y publicar" width="100%">

Cada script lee un fichero y escribe otro, así que cualquier paso se puede ejecutar suelto mientras se desarrolla.

### Orden del workflow y estado

<img src="docs/img/estado.svg" alt="Los diez pasos del workflow; el estado se confirma después de publicar y se guarda en git al final" width="100%">

El estado (`state/last_run.json` y `state/narrative/*.md`) no se actualiza al recoger ni al sintetizar, sino con
`--commit-state` después de publicar. Si algo falla antes, el workflow se detiene y la semana se puede reintentar sin
perder la ventana ni duplicar narrativa.

## Estado del proyecto

| Pieza | Estado | Nota |
|---|:---:|---|
| Recolección desde la API de GitHub | ✅ | Verificado 4/4 repos en W44; fallos de autorización y privacidad bloqueantes. |
| Síntesis con LLM (cadena de modelos de NVIDIA NIM) | 🟡 | Implementada. Solo se comprueba que la respuesta traiga las cuatro claves esperadas; no se valida el contenido. |
| Deck semanal (Marp → PDF) | ✅ | Generado y publicado en la ejecución W44. |
| Deck maestro y vídeo narrado | ✅ | V2 editorial con PDF/MP4/SRT validados en vista previa; publicación final en Drive se comprueba por separado. |
| Publicación en Drive con rclone | 🟡 | W44 e histórico publicados; pendiente sustituir el cliente compartido por OAuth propio (#1). |
| Workflow semanal en GitHub Actions | 🟡 | Definido (lunes 07:00 UTC y disparo manual). El pipeline se recuperó el 29-10-2026: ejecución real W44 con 4/4 repos sintetizados, publicación de PDF semanal, PDF maestro y vídeo, y commit de estado en main. Las semanas W36–W43 se reconstruyeron y archivaron, preservando sus eventos originales. |
| Tests automáticos | ✅ | Pruebas de regresión y controles CI de legibilidad, enlaces, imágenes, subtítulos y vídeo. Cobertura externa parcial. |

✅ probado · 🟡 implementado, pendiente de validar · 🚧 en construcción. El flujo W44 y los tests están verificados; la cobertura sigue siendo parcial.

## Inicio rápido

Requisitos para ejecutarlo en local: **Python 3.11+**, [`uv`](https://docs.astral.sh/uv/), y según el paso:
[Marp CLI](https://github.com/marp-team/marp-cli) (PDF), `ffmpeg` y `ffprobe` (vídeo) y `rclone` (publicar).

```bash
uv sync
export GH_PAT=...            # token de GitHub con acceso de lectura a los repos de la lista
uv run python src/collect.py --since 7d     # escribe out/collected.json
uv run python src/synthesize.py --dry-run   # solo imprime los prompts, sin llamar al modelo
```

`synthesize.py --dry-run` no necesita `NVIDIA_API_KEY` y es la forma segura de ver qué se enviaría al modelo.
Para ejecutarlo de verdad, define `NVIDIA_API_KEY` y quita `--dry-run`.

<details>
<summary><b>Resto de pasos y opciones</b></summary>

```bash
uv run python src/synthesize.py                 # out/summaries.json (--repo NOMBRE, --model ID, --no-state)
uv run python src/render.py --no-pdf            # solo out/deck.md; sin --no-pdf genera out/deck.pdf con Marp
uv run python src/publish.py --dry-run          # muestra el destino en Drive sin subir nada
uv run --with pymupdf python src/run_portfolio_v2.py --force  # generación editorial V2 sin Drive
uv run python src/render_video_v2.py --smoke-tone  # montaje aislado sin servicio TTS
uv run python src/publish.py --target master  # publicación versionada en modo V2
```

Los comandos `--commit-state` (`collect.py` y `synthesize.py`) confirman el estado a partir de `out/`; en el workflow
se ejecutan tras publicar. Ojo: escriben en `state/`.

</details>

<details>
<summary><b>Ponerlo en marcha en tu propia cuenta (GitHub Actions)</b></summary>

1. Haz un fork o copia del repositorio y edita `config/repos.yml` con tus repos (`showcase: true` y `pitch` a mano
   para los de escaparate; esa decisión no la toma el modelo).
2. Añade los secretos del repositorio: `NVIDIA_API_KEY` y `RCLONE_CONF` (contenido de un `rclone.conf` con
   un remote de Google Drive ya autorizado; el nombre del remote por defecto es `gdrive`, o `RCLONE_REMOTE`).
3. Lanza el workflow `devlog semanal` a mano (`workflow_dispatch`) antes de fiarte del cron.

El workflow necesita permiso `contents: write` para guardar `state/`. El token temporal de GitHub Actions sustituye al PAT caducado para los repos públicos.

</details>

## Configuración

| Dónde | Para qué |
|---|---|
| `config/repos.yml` | Repos a seguir, `defaults.since_days` (ventana de la primera ejecución, 7 por defecto), `showcase` y `pitch`. |
| `GITHUB_TOKEN` / `GH_PAT` | Actions usa token temporal para cuatro repos públicos; `GH_PAT` es alternativa local. El recolector bloquea repos privados. |
| `NVIDIA_API_KEY` | Clave de NVIDIA NIM (API compatible con OpenAI). `NIM_MODEL` o `--model` fuerzan un único modelo. |
| `RCLONE_CONF`, `RCLONE_REMOTE` | Configuración de rclone y nombre del remote de Drive. |
| `templates/` | Plantillas Jinja2 de los decks y tema Marp `theme.css`. |

Los secretos van en variables de entorno o en los secretos de Actions, nunca en el repositorio.

## Límites conocidos

- **Cobertura de tests:** regresiones automatizadas y validación PDF, imágenes y vídeo; CI de proyectos origen y Drive requieren evidencias de cada ejecución.
- **El texto lo escribe un modelo y nadie lo revisa.** Las narrativas y los titulares pueden contener errores o
  valoraciones no respaldadas por los commits. Revísalos antes de enseñarlos o publicarlos.
- **Qué sale de tu máquina.** Al sintetizar se envían a NVIDIA NIM el título de los commits, issues y PRs, los tags y
  la narrativa acumulada; se bloquean explícitamente los repositorios privados para evitar publicarlos. La narración del
  vídeo se envía al servicio de edge-tts (Microsoft) y el tema Marp carga fuentes de Google Fonts. El resultado se sube a
  tu Drive.
- **El modelo ve títulos, no diffs.** Recibe los títulos de commits y las cifras agregadas, no el código.
- **Síntesis incompleta bloqueante.** El proceso falla sin publicar ni actualizar estado cuando falte cualquier resumen.
- **Dependencia de servicios externos.** Los modelos listados pueden no estar habilitados para tu cuenta de NIM; si
  uno falla, se prueba el siguiente de la cadena.
- **El estado se guarda al final.** Si falla un paso después de confirmar el estado (deck maestro, vídeo, publicación
  maestra), el último paso de guardado no llega a ejecutarse y esa ventana se repetiría la semana siguiente.
- **Sin gestión explícita de límites de tasa** de la API de GitHub en `collect.py`.
- **Sin licencia.** El repositorio no incluye un archivo de licencia.

## Estructura del proyecto

```
src/
  collect.py        GitHub API -> out/collected.json (sin IA)
  synthesize.py     JSON + historial -> out/summaries.json (llamada al LLM)
  render.py         summaries -> out/deck.md -> out/deck.pdf (Marp)
  render_portfolio_v2.py  fichas auditadas -> out/portfolio-v2.pdf
  render_video_v2.py  guiones -> MP4 y SRT
  publish.py        PDF / vídeo -> Google Drive (rclone)
templates/          deck.md.j2 y theme.css (semanal); portfolio_v2.md.j2 y portfolio.css (editorial)
config/repos.yml    repos a seguir
state/              last_run.json y narrative/*.md, versionados por el workflow
.github/workflows/  weekly.yml (cron semanal, disparo manual y validación por push)
tests/              tests de regresión con unittest
docs/               gráficos del README y mapa del sistema (PSM)
```

## Documentación

- [`AGENTS.md`](AGENTS.md): directrices para agentes de IA que trabajan en el repositorio.
- [`docs/system-map/README.md`](docs/system-map/README.md): mapa del sistema (Project System Map). Parte de su contenido
  describe intenciones de diseño que no están todas implementadas.
- [`devlog-weekly-skeleton.md`](devlog-weekly-skeleton.md): brief original de diseño; algunas decisiones han cambiado
  (por ejemplo, el modelo usado ahora es NVIDIA NIM y no Anthropic).

---

<div align="center">

<sub>Proyecto personal. Las narrativas generadas por IA no están verificadas: revísalas antes de usarlas.</sub>

</div>

## Operación y recuperación (octubre de 2026)

- **Origen público:** el workflow usa `GITHUB_TOKEN` de GitHub Actions para leer exclusivamente los cuatro repos de `config/repos.yml`. El secreto `GH_PAT` anterior no se utiliza en Actions.
- **Fallos visibles:** errores de acceso a cualquier repo y síntesis incompleta terminan el job con error, sin publicar ni avanzar `state/`. El job `tests` es requisito del pipeline.
- **NVIDIA NIM:** la cadena antigua expiró en agosto de 2026. El 29-10-2026 se comprobó que `openai/gpt-oss-20b` funciona con esta cuenta y se situó como primer modelo. Las alternativas todavía requieren validación. Puede configurarse `NIM_MODEL` en el entorno de ejecución para fijar un modelo probado.
- **Drive:** `RCLONE_CONF` sigue siendo necesario. Se admiten los secretos opcionales `RCLONE_DRIVE_CLIENT_ID` y `RCLONE_DRIVE_CLIENT_SECRET` para usar OAuth propio, sin publicar los valores. Hasta configurarlos, la publicación dependerá del cliente compartido que rclone retirará en 2026.
- **Reprocesamiento:** el cursor se actualizó en `e2b0ae8` (29-10-2026). El informe W44 agrega lo pendiente desde agosto. El archivo W36 (parcial) a W43 se genera en un workflow independiente con metadatos fechados, sin modificar `state/` ni Drive.
- **Pruebas:** `uv run python -m unittest discover -s tests -v`.

La ejecución de GitHub Actions programada para los lunes sigue habilitada. Los cambios de código disparan únicamente CI; publicar el devlog semanal sigue reservado al cron de los lunes o al disparo manual. La vista previa no modifica el estado ni Drive.

## Histórico verificable (sin reescritura)

La reconstrucción W36 parcial–W43 utiliza **fechas reales** de commits,
issues y PRs cerradas de los cuatro repositorios públicos configurados.
No reinterpreta títulos con IA ni asigna etiquetas a una fecha histórica
sin evidencia. W36 empieza el 31-08-2026 a las 14:38:32 UTC, tras el
último run válido; el límite superior es exclusivo: 26-10-2026 00:00 UTC.

El módulo `src/backfill.py` crea informes Markdown y PDF (con Marp)
en `out/backfill/` y un `manifest.json` con los conteos reales.
No cambia `state/`, no toca los informes actuales de Drive y no utiliza
credenciales NVIDIA ni Google. El workflow `devlog histórico verificable`
los deja como artefactos de Actions descargables, con retención de 90 días.
Los informes históricos se deben revisar antes de distribuirlos.

El cron semanal y el disparo manual son los únicos que ejecutan
publicación de producción. Los cambios en archivos de código ejecutan
únicamente `devlog CI`, que no lleva secretos de servicios externos.
Las ejecuciones semanales están serializadas para no pisar el estado.

### Pendiente externo: OAuth propio de Google Drive

El servicio de Drive funcionó en la prueba W44, pero rclone emitió un
aviso sobre la retirada del `client_id` compartido. El código acepta
`RCLONE_DRIVE_CLIENT_ID` y `RCLONE_DRIVE_CLIENT_SECRET` como secretos
de Actions, sin exponer sus valores. Para activar la migración se necesita
crear/autorizar ese cliente en la cuenta Google; el conector de GitHub
no proporciona las credenciales ni permite escribir secretos de Actions.

## Archivo histórico durable en Drive

La reconstrucción crea primero un artefacto descargable de GitHub Actions.
Tras validarlo, `src/publish_backfill.py` archiva los 8 PDF, sus 8 Markdown
y el manifiesto en `Portfolio/historico-verificable/2026-W36__2026-W43/`.
Se utiliza `rclone copyto --immutable` para impedir sustituir otros
archivos. En particular NO se modifica `Portfolio/semanal/`,
`Portfolio/master/` ni el estado persistido de los repositorios.
Las credenciales OAuth siguen viniendo exclusivamente de Actions Secrets.

## Cierre de recuperación y pendientes documentados (29-10-2026)

- [W44 real](https://github.com/iagorobo24-hub/devlog-weekly/actions/runs/40792023387): 4/4 repos, PDF semanal, portfolio maestro PDF/MP4 y commit de estado.
- [Histórico](https://github.com/iagorobo24-hub/devlog-weekly/actions/runs/40794818343): ocho semanas, 17 archivos, subida con rclone inmutable a `Portfolio/historico-verificable/2026-W36__2026-W43/`.
- [CI (16 pruebas aprobadas)](https://github.com/iagorobo24-hub/devlog-weekly/actions/runs/40795276188).
- [Pendiente #1](https://github.com/iagorobo24-hub/devlog-weekly/issues/1): cliente OAuth propio de Google Drive y secretos GitHub.
- [Pendiente #2](https://github.com/iagorobo24-hub/devlog-weekly/issues/2): baseline PSM inaccesible (GitHub 404); pendiente reconciliación y recertificación.

La transferencia a Drive está comprobada mediante los registros de rclone. No se ha hecho todavía una lectura posterior independiente con comparación de hashes.


## Informe de calidad: paginación, fuentes y vista previa

- El histórico pagina todos los commits, PR e issues. El parámetro
  --max-items controla entradas por página, no eventos totales.
  Cada referencia incluye URL verificable y fecha obtenida de GitHub.
- El semanal agrupa proyectos sin actividad en portada, aporta métricas
  reales de actividad y ofrece enlaces a eventos observados. Los textos
  extensos se distribuyen por páginas; no se finge haber validado un
  despliegue sólo porque un commit lo mencione.
- La síntesis recibe SHA, fechas y títulos. Se validan los tipos y
  fechas explícitas fuera de ventana en los avances antes de publicar.
  No se recertifican automáticamente narrativas históricas antiguas.
- El workflow histórico ya no sube archivos a Drive automáticamente
  al cambiar código: para publicar exige opt-in manual publicar_drive=true.
  Por defecto sólo construye artefactos descargables.
- Una ejecución manual de devlog CI genera un PDF de prueba sintético
  sin acceso a los secretos de producción ni escritura de state o Drive.

La mejora se contrasta con los PDF históricos originales y con una
vista previa renderizada por GitHub Actions antes de habilitar el nuevo
código en producción.
