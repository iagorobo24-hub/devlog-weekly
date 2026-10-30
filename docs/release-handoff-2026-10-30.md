# Devlog Weekly — puerta de integración y entrega (30/10/2026)

**Dictamen: CANDIDATA LISTA PARA INTEGRACIÓN CONTROLADA, NO LISTA PARA DECLARAR PRODUCCIÓN CERTIFICADA.** No publicar el V4 automáticamente.

## Estado verificable

| Control | Resultado al 30/10/2026 |
| --- | --- |
| GitHub `main` remoto y origen local | `2f79343ea2fd9fdfd613f3fe81ac3d34cf20136a`, coinciden |
| Cambios desarrollados | 58 rutas modificadas o nuevas, incluido este informe; **sin commit, push, PR, merge ni despliegue** |
| Regresión Python de la candidata V4 | **436/436 tests correctos**; registro `/tmp/devlog-v4-refresh-regression-20261030.log` |
| Workflow YAML / Actionlint | Seis workflows sin errores en la fase anterior. No ejecutados en Actions tras el cambio |
| GitHub / selección pública | Cadena pública regenerada con API real, seis HEAD del V4 actuales al consultar; no se sigue la evolución futura automáticamente sin ejecutar el nuevo control |
| PDF semanal y publicación maestra V2 | E2E local con datos sintéticos, render real, rclone local, procedencia SHA-256 y recuperación; **no Google Drive remoto** |
| Publicación Drive, credenciales | GitHub Actions contiene `RCLONE_CONF`, pero se desconoce si su contenido cumple OAuth propio y ofrece permisos reales |
| Síntesis IA | GitHub Actions contiene `NVIDIA_API_KEY`; no se ha revalidado NVIDIA contra los siete repositorios de esta candidata |
| Estado histórico | `state/last_run.json` coincide byte a byte con `main`, SHA-256 `9dade7154bf8336e7a45fffbd264bd447dd917499cc1398c3dadac601c82e3f1` |
| V4 público | 3 proyectos principales, 2 complementarios, 1 descartado; propuesta **NO PUBLICAR**; QA PDF automático 9 páginas, 11 enlaces SHA, sin aprobación visual completa ni editorial |
| PSM histórico | Baseline `97a4319bba38bb5a09cfe8be89e58ead54f028a9` inaccesible (GitHub REST 422); auditoría actual separada, sin recertificar el manifiesto |
| Seguridad GitHub | `main` sin branch protection según la API; permiso por defecto de workflows `read`, pero el job `devlog` declara `contents: write` para confirmar `state/` y hacer `git push` |

## Dónde están los entregables

- Directorio de trabajo original, con los cambios **sin commit**: `/home/iagui/.cache/devlog-stabilization-20261029`.
- Candidata reconstruida, con informes públicos reales y PDF V4: `/home/iagui/.cache/devlog-v4-refresh-candidate-20261030`.
- Parche acumulado para reaplicar exclusivamente sobre la revisión de origen: ubicado en `/home/iagui/.cache/` con prefijo `devlog-stabilization-20261030-` y sufijo `complete.patch`; su hash se verifica por separado al cierre de la sesión.
- Borrador para revisar en Descargas: `/home/iagui/Downloads/DEVLOG_PORTFOLIO_V4_BORRADOR_NO_PUBLICAR_2026-10-30.pdf`; SHA-256 `27c65010596295b087921f36619b2418cb41de9c0b0c1a57a69845c1271f6323`.
- QA del PDF en Descargas: mismo nombre con `-QA.json`.

## Secuencia mínima para llegar a producción

**1. Autorizar integración de Git.** Comprobar que el remoto no haya cambiado desde `2f79343e` y que ningún otro agente esté modificando los mismos archivos; aplicar o consolidar el parche en una ubicación controlada. Revisar diff y, con autorización explícita, decidir commit, PR/push y destino. En este proyecto **continuar** no se interpreta como permiso implícito para push o despliegue.

**2. Revalidar el código integrado.** Ejecutar desde el SHA que efectivamente se vaya a entregar: `uv sync --locked`, `python -m unittest discover -s tests -q`, compilación estática, Actionlint y lock npm. Una prueba verde de la candidata sin integrar no acredita una versión remota nueva.

**3. Probar Drive de forma aislada.** Verificar si `RCLONE_CONF` contiene credenciales OAuth propias y `refresh_token`, o configurar secretos adicionales. Ejecutar primero el **modo de prueba sintético** del workflow, que no llama a NVIDIA ni publica portfolio; comprobar subida/descarga SHA-256 en Drive real. El token no debe mostrarse en logs.

**4. Probar NVIDIA y el ciclo semanal** con los siete repositorios y revisar resultados editoriales, manteniendo cursores, publicación y rollback coherentes. No gastar minutos CI sin comprobar disponibilidad o autorización para hacerlo.

**5. Mantener separados V2 y V4.** El cron conserva los dos casos publicados V2. No cambiar el target del publicador al V4: la selección editorial pública, la procedencia de afirmaciones, las capturas auténticas y la aprobación de distribución requieren revisión explícita. El QA `visual_review_completed` permanece **false**.

**6. Completar el mapa PSM** con un commit de referencia recuperable o abrir una nueva baseline auditada, sin cambiar retrospectivamente etiquetas históricas `VERIFIED`.

## Condición de salida

No anunciar *LISTO TODO* ni *producción estabilizada* hasta que existan SHA integrado, resultado de workflow sobre ese SHA, smoke de Drive real, ejercicio de modelo real, PDF semanal/portfolio verificables y aprobación editorial para cualquier sustitución V4. La situación local actual sí es una **candidata auditada y reproducible**, con límites identificados.

**Este documento no concede autorización de escritura en GitHub, Drive ni otros servicios.**

## Transporte Git comprobado el 30/10/2026

Una lectura de `origin` desde el Chromebook devolvió `Permission denied (publickey)` porque `origin` usa `git@github.com:iagorobo24-hub/devlog-weekly.git`, el agente SSH no estaba disponible y hay una regla global `url.*.insteadOf` que transforma incluso una URL HTTPS normal en SSH. **No se ha modificado ninguna configuración, clave ni token.** El repositorio continúa disponible: `gh api .../branches/main` devolvió `2f79343ea2fd9fdfd613f3fe81ac3d34cf20136a` y una lectura pública con la configuración Git global deshabilitada temporalmente tuvo el mismo resultado:

```bash
GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_SYSTEM=/dev/null GIT_TERMINAL_PROMPT=0 git ls-remote https://github.com/iagorobo24-hub/devlog-weekly.git refs/heads/main
```

La integración autorizada requiere además asegurar un transporte **de escritura** viable, preferiblemente mediante la autenticación HTTPS ya activa en `gh`, sin ejecutar todavía `push`. No se debe interpretar el acceso público de lectura como prueba de capacidad de escritura.
