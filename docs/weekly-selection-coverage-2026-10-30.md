# Devlog Weekly — cierre de cobertura y relevancia, 30/10/2026

## Diagnóstico confirmado por repositorio y API

El devlog semanal lee la lista **manual** `config/repos.yml`; por
tanto, su publicación no descubría automáticamente los proyectos que sí
detectaba el selector de vista previa `config/project-selection.yml`.
La configuración anterior tenía cuatro repositorios y omitía **GuiaIA**,
**T-IA-Portal-RocaRoibas** y **atm10sky-es-es-localization**.

Se consultó la API pública de GitHub el 30/10/2026, entre 03:31 y
03:35 UTC, exclusivamente para `iagorobo24-hub`. Resultado: nueve
repositorios públicos, nueve elegibles, sin comprobar repositorios
privados. Los commits consultados pertenecen a la rama predeterminada.
En la muestra de siete días desde el 23/10/2026:

| Repositorio | Commits muestreados | Código clasificado | Tests clasificados | Observación |
| --- | ---: | ---: | ---: | --- |
| GuiaIA | 69 | 28 | 27 | Primera prioridad por actividad y prioridad editorial |
| T-IA-Portal-RocaRoibas | 21 | 9 | 0 | Segunda prioridad |
| atm10sky-es-es-localization | 9 | 2 | 0 | Tercer candidato con código |
| devlog-weekly | 62 | 49 | 6 | Excluido deliberadamente del protagonismo editorial propio |
| awesome-tia-portal | 3 | 0 | 0 | Solo PSM en la muestra |
| proyecto-pfc-iago-duran | 3 | 0 | 0 | Solo PSM en la muestra |
| AUTOMATON | 3 | 0 | 0 | Solo PSM en la muestra |
| opencode-telegram-bot | 3 | 0 | 0 | Solo PSM en la muestra |
| vibe-kanban | 3 | 0 | 0 | Solo PSM en la muestra |

**Limitación fundamental:** se clasifican **títulos** de commits,
no la calidad de los diffs, el estado funcional ni CI. El trabajo no
publicado en GitHub tampoco es observable. Los recuentos del informe
son señales de actividad pública, no una certificación.

## Corrección integrada localmente

- Se han añadido los tres proyectos omitidos al seguimiento semanal:
  ahora hay **siete** repositorios configurados.
- Las nuevas entradas tienen `showcase: false`: aparecerán en el devlog
  cuando corresponda, pero **no** se incorporan automáticamente al
  portfolio maestro V2 ni desbloquean el editorial V4.
- Las tres entradas carecen de cursor histórico. En la primera ejecución
  usan `defaults.since_days: 7`; los cursores de los cuatro repositorios
  existentes se mantienen sin alteración. `confirm_pipeline_state`
  comprueba cobertura completa antes de cambiar `state/`.
- `src/synthesize.py` comparte con el selector las categorías de commits.
  Solo PSM/documentación/CI/chore/estilo/build no constituye por sí mismo
  avance sustancial. Los mensajes de formato **desconocido** se siguen
  enviando a revisión; los PR, issues cerrados y tags nuevos siguen
  contando como eventos de actividad.
- En repos mixtos, los asuntos rutinarios no desplazan los eventos
  sustanciales del prompt ni sus enlaces de evidencias. Se conserva el
  total de commits y se informa del número de asuntos rutinarios omitidos.
- La respuesta de la IA no puede marcar por su cuenta una síntesis
  sustancial como `trivial`. El PDF identifica explícitamente
  **avances sustanciales**, no supone que un mantenimiento sea inactividad
  absoluta.

## Criterios de cierre y límites

Pruebas añadidas para cobertura pública de prioridades altas, ausencia
de duplicados, no promoción maestra accidental, ventanas de bootstrap,
compatibilidad de estado nuevo y antiguo, fallos por cobertura parcial,
detección de ruido PSM, filtrado de evidencias, conservación de mensajes
desconocidos y defensa frente a la marca `trivial` del modelo.

Pendiente: la primera ejecución real del collector/GitHub Actions con
siete proyectos y su síntesis NVIDIA NIM; no se consume CI ni se
publican datos automáticamente en esta fase. La selección editorial V4
y su aprobación permanecen independientes. No se modifican los
compromisos históricos del PSM.

## Comprobación real posterior al cambio

Se ejecutó `python -m src.collect` el 30/10/2026 desde la candidata
aislada, con el cliente PyGithub real y autenticación de lectura disponible.
No se ejecutó GitHub Actions, no se publicó ningún PDF, no se hizo commit y
no se alteraron las fuentes GitHub. La ejecución terminó con **7/7
repositorios recogidos** y código de salida cero (51,39 segundos).

| Entrada | Commits de la ventana realmente recogidos | No rutinarios o sin clasificar | Rutinarios |
| --- | ---: | ---: | ---: |
| GuiaIA | 69 | 57 | 12 |
| T-IA-Portal-RocaRoibas | 21 | 10 | 11 |
| atm10sky-es-es-localization | 9 | 2 | 7 |
| Los cuatro repositorios previos | 0 | 0 | 0 |

Los tres proyectos nuevos comienzan con una ventana de siete días. Los
cuatro anteriores conservan su cursor del 29/10/2026, de modo que aquí
no aparece actividad nueva de estos últimos. El archivo original
`state/last_run.json` no cambió (SHA-256:
`9dade7154bf8336e7a45fffbd264bd447dd917499cc1398c3dadac601c82e3f1`).

A continuación se utilizó una **respuesta artificial de modelo**, de
carácter no publicable, para ejecutar `synthesize.main`, la validación
`confirm_pipeline_state.check_state` y `render.main(--no-pdf)` sobre
ese JSON real: siete resúmenes completos, tres proyectos destacados,
cuatro sin avance sustancial, salida Markdown y estado sin cambios.
El primer intento detectó que la respuesta simulada no incluía
`trivial`; se reforzó `synthesize.main` para que lo derive
determinísticamente de los eventos de GitHub. La segunda ejecución pasó.
No se llamó a NVIDIA, Marp ni Drive en esta comprobación concreta.

Pendientes de integración real: publicar el parche autorizado, ejecutar
NVIDIA NIM con los siete repositorios y repetir una ejecución semanal
con GitHub Actions y Google Drive OAuth, respetando el bloqueo editorial
V4. La prueba de renderizado y publicación local real de la fase anterior
sigue siendo válida, pero no equivale a ejecutar esta nueva selección
con servicios externos.
