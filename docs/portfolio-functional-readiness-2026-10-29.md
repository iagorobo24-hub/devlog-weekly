# Diagnóstico funcional de portfolio - 29/10/2026

La auditoría examina mediante GitHub Actions los pasos **realmente ejecutados** en las ejecuciones de push del commit fijado y mantiene la separación entre prueba automatizada, CI, hardware/simulador y permisos de imagen.

**PFC Tools:** el run 40444658645, en main 205725a89598, pasó lint y typecheck, pero se detuvo en Production dependency audit. El log de npm audit (production) notificó seis vulnerabilidades: una crítica, cuatro altas y una baja. Las pruebas unitarias, build y Playwright quedaron omitidos. Revisar dependencias directas/transitivas, lockfile y compatibilidad; repetir npm ci, npm audit de producción, pruebas, build y Playwright en el repositorio PFC. No utilizar cambios forzados sin evaluación.

**GuiaIA:** el run 40821224773 contiene pruebas unittest correctas en tres versiones de Python, sin validar acompañante jugable. **TIA Portal RocaRoibas:** run 40892526988, workspace-checks en Windows, sin acreditar TIA o PLCSIM. **Awesome TIA:** ejecución de Pages dinámica y no CI push del producto. **ATM10:** sin CI push en HEAD acreditada.

Archivo generado en la auditoría pública: portfolio-functional-readiness-public.json, más resumen Markdown. No se cambian repositorios de origen ni la publicación. Ninguna imagen se aprueba automáticamente.
