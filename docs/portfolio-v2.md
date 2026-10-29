# Portfolio editorial 2.0 — Fuente de verdad y controles

## Objetivo y procedencia

El portfolio presenta capacidades y evidencias públicas; no es un volcado de commits ni certifica despliegues.
Las dos fichas editoriales de `content/portfolio/projects.yml` indican revisión Git fija, finalidad, arquitectura,
capacidades documentadas, límites y enlaces verificables. Las capturas de `assets/portfolio/` proceden
de commits identificados y deben etiquetarse como capturas versionadas, no como prueba de producción.

## Componentes

- `src/portfolio_data.py`: valida esquemas, fuentes, rutas y recursos visuales.
- `src/render_portfolio_v2.py`: genera nueve diapositivas semánticas y un manifiesto de narración.
- `templates/portfolio_v2.md.j2` y `templates/portfolio.css`: composición visual propia.
- `src/quality_gate.py`: comprueba PDF, enlaces a evidencias, imágenes, márgenes y páginas.
- `src/render_video_v2.py`: genera MP4, narración por diapositiva, fundidos y subtítulos SRT.
- `.github/workflows/ci.yml`: vista previa de PDF y vídeo con tono sintético, aislada de Drive.

## Validación local sin publicación

Instalar con `uv sync` y disponer de Marp CLI, ffmpeg y ffprobe.

1. `uv run python -m unittest discover -s tests -v`.
2. `uv run python src/render_portfolio_v2.py`.
3. `uv run --with pymupdf python src/quality_gate.py --pdf out/portfolio-v2.pdf --manifest out/portfolio-v2-manifest.json`.
4. `uv run python src/render_video_v2.py --smoke-tone` (sin proveedor de voz).
5. `uv run python src/render_video_v2.py` (voz real, requiere conexión).

Las pruebas no modifican `state/`, no publican en Drive y no reescriben históricos.

## Criterios para promover el pipeline semanal

- CI verde, PDF inspeccionado visualmente, sin cortes ni afirmaciones no sustentadas.
- Referencias comprobables y consistentes con las revisiones indicadas.
- Paridad entre PDF, imágenes renderizadas, narración, MP4 y subtítulos.
- El pipeline semanal anterior permanece recuperable hasta completar la promoción.
- La validación académica o CI de un proyecto origen se evalúa por su commit, no por una descripción histórica.

## Limitaciones

Las capturas son snapshots: no acreditan la instalación de sistemas industriales ni el estado actual de la web.
La temporización de subtítulos se estima por el número de palabras; no es alineación fonética.
Las fichas editoriales requieren mantenimiento cuando cambien los proyectos o las pruebas.

## Pulido visual y fiabilidad editorial

- Los diagramas editoriales se derivan de contratos documentados y se etiquetan
  como esquemas explicativos, sin atribuirles ejecución de todos los bloques.
- Los resultados publicados de TIA Portal quedan limitados a los dos recursos
  documentados con pruebas en CPU virtual. Sus enlaces apuntan a la revisión
  SHA fija del proyecto y a los ficheros de evidencia.
- Las capturas de KPI y almacén se recortan para favorecer la lectura; su
  origen sigue indicado mediante enlaces a las imágenes completas versionadas.
- La portada distingue corte documental de generación del documento.
- El PDF fija título, autor y asunto con PyMuPDF; la puerta de calidad exige
  texto dentro del lienzo y tamaño mínimo de 8 puntos.
- La voz y los subtítulos comparten limpieza de puntuación. La sincronización
  SRT es aproximada por distribución de palabras; no por marcas fonéticas.
- Si out/collected.json registra commits posteriores a la revisión editorial,
  se añade una alerta con el SHA observado. Nunca se promociona
  automáticamente una captura, prueba o afirmación a un estado más maduro.
