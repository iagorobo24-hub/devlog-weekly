# Dependencias externas verificadas — 30/10/2026

Esta fase no ejecuta GitHub Actions ni realiza publicaciones.

## Contratos

| Herramienta | Versión / instalación | Evidencia |
| --- | --- | --- |
| Python | uv.lock, uv sync --locked | 408 pruebas en fase previa |
| Node | actions/setup-node, major 22 | Node 22.23.2 local; revisión menor variable |
| Marp CLI | package.json 4.5.0 exacta y package-lock.json | npm ci instaló 155 paquetes, versión 4.5.0 confirmada |
| rclone | scripts/install-rclone-pinned.sh, v1.75.0 | Descarga real, checksum SHA-256 oficial y binario ejecutable verificados |
| CI | .github/workflows/ci.yml observa locks y scripts | YAML validado, sin usar minutos CI |

Cinco workflows usan npm ci con las dependencias fijadas y añaden node_modules/.bin al PATH. Dos workflows instalan rclone desde un archivo versionado con comprobación SHA-256; no ejecutan un instalador remoto dinámico con privilegios de root. La instalación fijada de rclone admite por ahora solo linux/amd64 y falla expresamente en otras arquitecturas.

Los nuevos contratos automáticos están en tests/test_toolchain_lock.py.

## Límites

ffmpeg procede aún del sistema Ubuntu y el extra puntual pymupdf no está fijado en el bloqueo principal. Las revisiones menores de Node 22 y npm pueden cambiar entre runners. Los checksums no sustituyen una auditoría de cadena de suministro y no garantizan la funcionalidad en Google Drive real, NVIDIA NIM, voz online o CI remoto. La publicación sigue sin autorizarse.

## Resultado

Se verificaron instalaciones locales de Marp y rclone, y la comprobación estática de cinco contratos. Los nuevos cambios todavía deben superar la regresión integral de la candidata final.