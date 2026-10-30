# Recuperación del portfolio maestro V2

## Contrato de publicación

`src/publish.py --target master` mantiene las rutas habituales
`Portfolio/master/portfolio.pdf`, `.mp4` y `.srt`.
**No son un conjunto atómico**: una interrupción puede dejar algunas rutas
con la nueva versión y otras con la anterior.

Para lectores que necesitan una versión coherente existe ahora
`Portfolio/master/current.json`. Se actualiza **después** de que los tres
archivos, sus copias inmutables y los alias hayan superado SHA-256.
Cada manifiesto apunta exclusivamente a
`Portfolio/master/versions/<run-id>/portfolio.{pdf,mp4,srt}`
y registra el hash de cada archivo. La versión del propio manifiesto se
conserva en `versions/<run-id>/release.json`, también verificada.

El recibo local de generación V2 sigue siendo obligatorio. El publicador
compara sus SHA-256 con los bytes que prepara para subir: una modificación
entre la validación y el inicio de la publicación se rechaza.

## Recuperar una versión coherente sin tocar los alias

Con un `RCLONE_CONF` válido en el entorno, desde la raíz del repositorio:

```bash
python - <<'PY'
import os
from pathlib import Path
from src.publish import download_verified_master_snapshot

document = download_verified_master_snapshot(
    os.environ.get("RCLONE_REMOTE", "gdrive"),
    os.environ["RCLONE_CONF"],
    Path("out/master-recuperado"),
)
print("Versión verificada:", document["run_id"])
PY
```

El directorio de destino **no debe existir todavía**. Se descargan las
tres versiones inmutables y se comprueban los SHA-256 antes de exponer el
directorio completo mediante un único renombrado local. Si el puntero,
algún archivo o un hash no coincide, se aborta sin recurrir a los alias
mutables. El procedimiento no publica ni modifica contenido remoto.

## Fallos y límites

- Si falla una subida o la actualización del segundo/tercer alias, el
  `current.json` anterior sigue apuntando a la versión previa (salvo
  escrituras externas concurrentes), mientras las versiones nuevas quedan
  disponibles para diagnóstico y reintento.
- Si falla la actualización o lectura de `current.json` mismo, el paso
  termina con error: **no se puede asumir qué puntero quedó visible** sin
  leerlo y validarlo otra vez.
- Antes de la primera publicación completa no existe un puntero certificado;
  por seguridad, el recuperador falla en vez de leer los alias.
- `current.json` es una referencia de integridad **no firmada**. Un actor
  que controle tanto el puntero como las versiones puede sustituirlos.
- Los consumidores que continúen leyendo directamente los alias
  tradicionales seguirán expuestos a versiones mezcladas. Migrar lectores
  al puntero es un paso operativo separado.
- Se ha probado con un backend `rclone` local real y fallos remotos
  simulados, **no** con Google Drive personal y OAuth real. Se mantienen
  pendientes esa prueba operativa y la aprobación del portfolio editorial.
