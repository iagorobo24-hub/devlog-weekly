# Auditoría de vigencia editorial pública V4 — 30/10/2026

**Resultado:** las seis revisiones de la selección editorial pública coinciden con el HEAD de su rama predeterminada tras una actualización controlada de GuiaIA. **No se autoriza publicar ni sustituir el portfolio maestro V2.**

## Evidencia real de GitHub

El 30/10/2026 se consultaron, mediante API de GitHub, las ramas predeterminadas de los seis proyectos del V4: TIA Portal RocaRoibas, PFC Tools, GuiaIA, Awesome TIA Portal, ATM10 Sky y AUTOMATON. Cinco coincidían con las revisiones fijadas. GuiaIA no:

- Revisión editorial antigua: `685bd6d1f614793db7e34667846b4d83b199b550`.
- HEAD público observado: `060497ccb56bb0a2e9b5e488c84256e51bfbf2ef`.
- GitHub Compare informó **66 commits posteriores, 151 archivos en la comparación y cero commits detrás**.
- Se comprobaron mediante la API las rutas versionadas `README.md`, `tests/test_mcp.py` y `assets/guiaia-hero.svg` en el nuevo HEAD.
- El README del nuevo SHA todavía se presenta como *early developer preview*, describe cuatro herramientas MCP disponibles, y **no** reclama un compañero jugable validado. Por tanto, la ficha conserva prudentemente esos límites.
- GitHub Actions mostró cinco workflows de evento push **completed/success** en ese SHA, entre ellos CI, Chest QA, Fabric Observer Build y QA Companion. Esto acredita esos resultados de CI observados, no funcionamiento de Minecraft en el entorno del usuario.

Se han actualizado solamente las revisiones de GuiaIA en `content/portfolio/editorial-selection-public.yml`, `content/portfolio/candidates/guiaia.yml`, `content/portfolio/evidence-inventory-public.yml` y su test de inventario público. Se conservan los demás proyectos, su orden, sus claims prudentes, la clasificación de las imágenes como no aprobadas y todas las compuertas de publicación.

## Nueva protección

`src/editorial_live_freshness.py` comprueba solo repositorios públicos, compara cada SHA fijado con el HEAD actual, produce un informe JSON sin tokens y falla cerradamente si GitHub no está disponible o alguna revisión difiere. El workflow `portfolio-editorial-v4-pdf-preview.yml` la ejecuta **antes del exportador PDF**. No hay escritura remota ni modificación automática de las revisiones.

La prueba negativa real se ejecutó primero con el SHA antiguo: **5 actuales, 1 obsoleto; código de salida 1**. Tras verificar las fuentes y actualizar la ficha, la segunda prueba real dio **6 actuales, 0 obsoletos, 0 no verificables; código de salida 0**.

Este control impide que un PDF nuevo se presente como actualizado sin revisar cambios posteriores de código. No sustituye las comprobaciones de afirmaciones, autoría, calidad gráfica, hardware, pruebas jugables ni la revisión humana del contenido.

## Pendiente de publicación

La selección V4 continúa con tres proyectos principales, dos complementarios y AUTOMATON excluido. La cartera V2 aprobada no se modifica; tampoco `current.json`, Drive, CI alojado ni el manifiesto PSM histórico. Los informes públicos dependientes y el PDF V4 se han regenerado y han superado sus validaciones automáticas, pero aún es necesario comprobar las afirmaciones en funcionamiento real, revisar visualmente el PDF a tamaño de lectura y obtener aprobación editorial explícita antes de reemplazar el portfolio publicado.

## Regeneración integral local y PDF (30/10/2026)

La auditoría pública completa se ha repetido desde una candidata reconstruida de `main@2f79343e` más el parche acumulado. Se ejecutaron consecutivamente el selector de 9 repositorios públicos, actividad/CI de ramas, auditoría de rutas de commits, calidad por HEAD, fichas, auditoría de fuentes, estrategia, cobertura, revisión de release, inventario visual, preparación funcional, comprobación viva de los 6 HEAD y composición editorial V4. Todos los pasos pasaron sin usar GitHub Actions, repositorios privados ni Google Drive.

Resultado: cinco candidatos con fuentes estructurales al HEAD; CI de push correcta al HEAD para GuiaIA y TIA Portal, no confirmada para ATM10 y Awesome TIA, fallida para AUTOMATON; ocho archivos visuales inventariados y ninguno autorizado automáticamente. Actividad de ramas no fusionadas: 0 commits de código/pruebas en la ventana de siete días de los proyectos seleccionados; cobertura parcial de otros dos repositorios secundarios. La revisión pública V4 conserva tres casos principales, dos complementarios, un caso excluido y **cero autorizaciones de publicación**.

El Markdown y manifiesto V4 han superado el preflight de procedencia. Se ha creado un PDF real con Marp CLI 4.5.0 y Chromium headless, configurado con metadatos y validado con PyMuPDF: **9 páginas, 11 enlaces fijados a SHA y control PDF automático aprobado**. Las nueve páginas se renderizaron como imágenes y se inspeccionó una hoja de contacto: jerarquía visual consistente, sin desbordes evidentes; las citas inferiores aparecen pequeñas y quedan sujetas a una revisión de legibilidad a tamaño real. La marca `visual_review_completed: false` del informe QA permanece deliberadamente sin aprobar, pues esta inspección no acredita lectura humana exhaustiva ni autorización editorial.

PDF de revisión copiado sin sobrescribir otros archivos en el Chromebook: `/home/iagui/Downloads/DEVLOG_PORTFOLIO_V4_BORRADOR_NO_PUBLICAR_2026-10-30.pdf` (SHA-256 `27c65010596295b087921f36619b2418cb41de9c0b0c1a57a69845c1271f6323`). El informe QA está junto al PDF con sufijo `-QA.json`. La candidata local también conserva `out/` con Markdown, manifiesto, informe de fuentes y PDF.

La regresión reconstruida pasó **436/436 pruebas**. No se ha realizado commit, push, deploy, gasto de minutos CI ni publicación Drive. Quedan por validar las funcionalidades en entornos reales, permisos de imágenes y la aprobación expresa de sustitución del V2.
