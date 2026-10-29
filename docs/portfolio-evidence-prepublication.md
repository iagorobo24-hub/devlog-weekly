# Verificación de evidencias y capturas — V4

Este gate de **lectura pública** compara los cinco casos de
\`editorial-selection-public.yml\` con sus revisiones Git, consulta CI de
evento \`push\` en SHA y rama exactos, verifica la existencia de archivos
visuales y fuentes documentales, y crea los artefactos JSON/Markdown de auditoría.

Los archivos \`.svg\` conceptuales **no** se presentan como capturas reales,
ni las imágenes E2E de PFC Tools acreditan automáticamente una sesión
funcional actual. Las doce capturas de ATM10 proceden de candidatas anteriores
a la traducción 191. Las imágenes de Awesome TIA proceden del repositorio,
pero su autenticidad, revisión exacta y permiso de uso no se han validado
en este proceso.

Una CI de GitHub correcta tampoco prueba TIA Portal, Minecraft,
PLCSIM, WinCC, una sesión web o un despliegue real.

El informe determina de forma verificable:
- Identidad pública, SHA y rama predeterminada actual.
- CI \`push\` en el SHA actual, filtrada **antes** de truncar a 25 runs.
- Archivo de evidencia documental presente o ausente.
- Imagen de referencia versionada presente, formato, tamaño y blob Git.
- Permisos, autenticidad y validación funcional: **pendientes**, nunca inferidos.

No lee repositorios privados ni modifica los casos publicados. La ausencia
de una captura utilizable no bloquea la revisión documental; sí bloquea
su promoción a un PDF público si necesita una captura no acreditada.
