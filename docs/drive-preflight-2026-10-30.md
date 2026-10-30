# Prepublicación de Google Drive — 30/10/2026

## Diagnóstico

El Chromebook no tiene rclone.conf ni RCLONE_CONF local. En GitHub Actions existe un secreto RCLONE_CONF y otros dos nombres para credenciales propias no aparecen configurados (consulta solo de nombres). El contenido de los secretos no es legible mediante la API; podría contener client_id y client_secret propios, pero **no está verificado**.

Hasta ahora la comprobación de Drive ocurría después de recopilar y sintetizar el devlog, y la publicación podía proceder usando credenciales OAuth compartidas o incompletas. Eso desperdicia recursos y dificulta diagnosticar fallos reales de OAuth.

## Corrección

El módulo src/drive_readiness.py valida la configuración estática de forma estricta: remote gdrive de tipo drive, configuración OAuth propia completa (en RCLONE_CONF o en variables separadas) y token de usuario con refresh_token. Rechaza service accounts en esta ruta destinada a Drive personal, credenciales partidas, JSON inválido y nombres de remote inseguros. No realiza tráfico de red y no imprime ningún secreto.

El workflow weekly.yml ejecuta el preflight después de uv sync --locked y **antes** de instalar herramientas, recopilar actividad, llamar a NVIDIA, renderizar o publicar. El job de pruebas sigue sin necesitar secretos.

La primera publicación real exigirá comprobar OAuth y permisos con una lectura/escritura aislada de Drive. Las 8 pruebas unitarias cubren escenarios positivos, negativos, filtrado de secretos y orden del workflow. **Esta fase no realizó ninguna escritura remota.**

## Condición operativa

Si el secreto RCLONE_CONF ya contiene client_id y client_secret propios junto con el refresh_token, no hace falta crear dos secretos nuevos. Si contiene el cliente compartido o no hay refresh_token, la futura ejecución programada se bloqueará **antes de cualquier generación** hasta configurar OAuth propio.

No se autoriza ni realiza una migración automática de credenciales, un cambio del token o una publicación del portfolio. La prueba de extremo a extremo con Drive real sigue pendiente.