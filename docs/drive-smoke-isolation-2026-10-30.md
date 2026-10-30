# Prueba aislada de Drive — 30/10/2026

## Fallo identificado y corregido

La opción `modo_prueba=true` de `.github/workflows/weekly.yml` antes ejecutaba el recolector real de GitHub, la síntesis NVIDIA y el renderizador para obtener un PDF que luego cargaba en Drive. No era una prueba aislada del almacenamiento: consumía APIs externas y podía fallar por motivos ajenos a OAuth o Drive.

La combinación `modo_prueba=true` con `solo_portfolio=true` producía una ejecución sin ninguno de los dos productos esperados, en lugar de indicar que ambas opciones son incompatibles.

## Comportamiento nuevo

| Evento / opciones | Recopila GitHub | Sintetiza con NVIDIA | Publicación semanal | Portfolio maestro | Drive sintético |
| --- | --- | --- | --- | --- | --- |
| `schedule` | Sí | Sí | Sí | Según actividad | No |
| Manual: `modo_prueba=true`, `solo_portfolio=false` | No | No | No | No | **Sí** |
| Manual: `modo_prueba=false`, `solo_portfolio=false` | Sí | Sí | Sí | Según actividad | No |
| Manual: `modo_prueba=false`, `solo_portfolio=true` | No | No | No | Sí, forzado | No |
| Manual: ambos `true` | **Error explícito** | No | No | No | No |

En el modo de prueba no se instalan Node/Marp ni FFmpeg. El job mantiene `uv sync --locked`, la validación estática de credenciales y el instalador fijado de rclone. El job de tests sigue ejecutando las pruebas Python, por lo que no significa coste cero de GitHub Actions.

`src/drive_smoke.py` genera de forma determinista un pequeño PDF PDF 1.4 sintético, sin texto personal, consultas externas ni dependencias de navegador. Se publica una copia en `Portfolio/verificaciones/<run-id>-<attempt>/devlog.pdf`, se descarga y se compara su SHA-256. El objeto se conserva intencionadamente como prueba auditable. Antes de cualquier transferencia se valida estructura OAuth propia mediante `src/drive_readiness.py`.

No se toca `state/`, ni se sobrescribe el PDF semanal o maestro. Las rutas se construyen con identificadores numéricos canónicos; las mismas bytes permiten reintentar la publicación en la ruta inmutable de un mismo run.

## Evidencia y limitaciones

`tests/test_drive_smoke.py`: seis pruebas que cubren PDF/XREF válido, roundtrip con **rclone real y backend local**, reintento, rechazo de identificadores peligrosos, protección ante OAuth ausente, corrupción y segregación de pasos del workflow. Los seis workflows han superado `actionlint 1.7.12` (descarga oficial verificada por SHA-256) sin errores.

**No se ha probado Google Drive real.** El backend local demuestra integridad y flujo de transferencia, pero no los permisos del token ni la validez del OAuth. No se ha ejecutado GitHub Actions ni se han gastado minutos de CI, ni se ha publicado contenido remoto. Los únicos writes fueron en carpetas locales aisladas.
