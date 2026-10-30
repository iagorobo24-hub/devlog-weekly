# Devlog Weekly — integración candidata y pruebas de extremo a extremo

Fecha de verificación: **2026-10-30**. Rama de origen: `main`, commit
`2f79343ea2fd9fdfd613f3fe81ac3d34cf20136a`.

## Alcance realmente ejecutado

- Reconstrucción en carpeta aislada de un archivo Git de `main` y del
  parche acumulado, seguida de comparación byte a byte de código, pruebas y
  documentación respecto a la copia local de desarrollo.
- Suite **397/397** correcta desde la candidata reconstruida. La suite se
  ejecutó sin llamadas de GitHub Actions ni gasto de minutos CI.
- Smoke semanal totalmente aislado con **cuatro repositorios sintéticos**:
  síntesis real de JSON y comprobación de estado, generación PDF con Marp y
  Chrome headless reales, procedencia desde los bytes originales, carga y
  verificación SHA-256 con rclone *local*, confirmación de estado después
  de publicar y repetición idempotente.
  PDF generado de 52.802 bytes. El modelo se sustituyó por una respuesta
  sintética; ningún evento artificial se publicó.
- Smoke del portfolio maestro **V2**, forzando generación en un directorio
  temporal: PDF con Marp/Chromium, control PDF con PyMuPDF
  (`pass`: 12 páginas, 21 enlaces, tres imágenes, dos proyectos),
  render real del vídeo con FFmpeg/ffprobe y **tono sintético offline**
  (12 clips, vídeo de aproximadamente 14,424 s, ~852 KB), SRT, recibo
  de procedencia, publicación versionada V2 con rclone local, manifiesto
  `current.json` y descarga coherente byte a byte de PDF/MP4/SRT.
- Pruebas negativas anteriores de publicación parcial, recuperación y
  reintentos correctas. No se ha utilizado Google Drive, Edge TTS online
  ni la API de NVIDIA en estas pruebas de integración.

El primer intento de smoke maestro ejercitó accidentalmente la ruta
heredada porque el lanzador de prueba no definió
`PORTFOLIO_V2_RELEASE=1`; no certificaba el puntero V2 y fue corregido
en el lanzador aislado. La repetición con la variable que utiliza el
workflow real pasó todos los pasos. El primer intento de render semanal
no disponía de navegador en Crostini; se descargó uno temporal y el
render real posterior fue satisfactorio.

## Bloqueos pendientes, no maquillados por la suite verde

1. **Integración remota de cambios:** la copia de desarrollo y el parche
   todavía no se han incorporado a GitHub. No se ejecutaron commit, push,
   PR, merge ni publicación automática.
2. **Google Drive/OAuth propio:** prueba real de permisos, token OAuth,
   reintentos y lectura remota aún pendiente.
3. **GitHub Actions:** no se ejecutó el cron/workflow alojado, para evitar
   consumir minutos CI. Una ejecución real deberá acreditar GitHub API,
   NVIDIA NIM, PDF, Drive y persistencia en el repositorio.
4. **Contenido editorial:** el V2 integrado y ejecutable muestra **dos**
   proyectos; la propuesta V4 revisa también GuiaIA. Esto no demuestra
   que ambas políticas editoriales estén conciliadas ni autoriza
   publicación del V4.
5. **PSM:** fuente de referencia histórica no reconciliada, sin
   modificación de `psm.source.commit` ni de estados históricos.
6. **Limitaciones de consistencia:** los tres alias mutables de Drive
   siguen sin ser transaccionales, aunque el lector que utiliza
   `current.json` y las versiones inmutables puede recuperar un
   conjunto verificable. Tampoco hay firma digital de los manifiestos.
7. **Calidad humana:** el gate PDF automatizado no equivale a inspección
   visual completa y la voz sintética no valida la calidad del narrador.

## Artefactos reproducibles en el Chromebook

- Candidata integrada: `/home/iagui/.cache/devlog-integration-candidate-20261030`
- Generador de smoke semanal:
  `/home/iagui/.cache/devlog-offline-smoke-20261030.py`
- Generador de smoke maestro V2:
  `/home/iagui/.cache/devlog-master-v2-real-smoke-20261030.py`

Ambos scripts usan copias temporales y borran los resultados al terminar.
La carpeta candidata no es un repositorio Git nuevo: no contiene trabajo
ajeno ni una nueva rama. Esta verificación **no** constituye autorización
de publicación.

## Corrección posterior: dependencias Python reproducibles

El 30/10/2026 se ha incorporado `uv.lock` (39 paquetes resueltos),
sin modificar las restricciones declaradas en `pyproject.toml`.
Se han cambiado los nueve pasos de instalación `uv sync` de los seis
workflows para utilizar `uv sync --locked`: una discrepancia de
dependencias debe fallar explícitamente en vez de recalcular la
resolución durante CI. Los YAML de los seis workflows se han podido
analizar sin error.

Una copia aislada instaló el grafo desde `uv.lock` con `uv sync --locked`
y pasó **408/408 tests**, también bajo `uv run --locked`, con Python
3.11.2 del Chromebook. Una modificación artificial de `pyproject.toml`
en un directorio de prueba hizo fallar `uv lock --check`; sobre la
candidata original el chequeo pasó.

**Límite:** este lock hace reproducible la resolución del conjunto
Python del proyecto en las plataformas admitidas; no fija versiones
de `npm install -g @marp-team/marp-cli`, el instalador remoto de
`rclone`, `ffmpeg`, ni el `uv run --with pymupdf` usado por
ciertos jobs. Esas dependencias operativas aún requieren control
de versiones y pruebas reales antes de proclamar CI plenamente
reproducible. No se ha ejecutado GitHub Actions.

## Cadena de herramientas externas — 30/10/2026

Se han fijado Marp CLI 4.5.0 con package-lock.json, Node 22 en los cinco workflows de render y rclone 1.75.0 mediante instalador con SHA-256. Instalaciones reales correctas sobre el Chromebook. El informe y los límites están en docs/toolchain-reproducibility-2026-10-30.md. No se han ejecutado Actions ni publicado artefactos.
