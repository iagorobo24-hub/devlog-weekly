# Selector de proyectos: relevancia y privacidad

## Motivo del cambio

El devlog semanal sólo rastreaba cuatro repositorios configurados manualmente.
El portfolio maestro seleccionaba dos casos de estudio fijos. Ninguno
representaba automáticamente la actividad real de todos los proyectos.

## Inventarios separados

- Public: se descubren sólo repositorios públicos. Salida en
  out/project-selection-public.json y workflow de vista previa pública.
- Private-local: se descubren sólo privados accesibles al propietario
  autenticado. El informe queda FUERA del repositorio, en la carpeta
  local ~/.local/share/devlog-weekly/restricted con permisos 0700 y
  archivo 0600. No se imprime el ranking privado y CI lo bloquea.

No se envían datos privados a NVIDIA, Drive, GitHub Actions, repositorios
públicos ni PDF compartidos. La selección es de solo lectura contra GitHub
y no cambia state, narrativas, PDF ni repositorios de origen.

## Reglas de selección

Se consultan ventanas de 7 y 30 días, con tope de 200 commits por repo.
Se puntúan feat, fix, refactor, perf y test; PSM, documentos rutinarios y
commits sin clasificación no puntúan como desarrollo funcional.
Los recuentos se transforman logarítmicamente, de modo que muchos cambios
pequeños no desplacen automáticamente a un proyecto importante.

Para los proyectos públicos existe prioridad editorial explícita entre
0 y 5, con origen en config/project-selection.yml. Los nuevos repositorios
públicos son descubiertos aunque no aparezcan en el fichero.
Devlog Weekly queda fuera del ranking protagonista por ser la herramienta
que genera el propio informe. Aparece en la lista de seguimiento.

El resultado separa ranked (candidatos activos), other_active (otros con
actividad) y watchlist (PSM solamente, inactivos o infraestructura interna).
Todos los candidatos requieren revisión editorial, sin alegar que
las pruebas o los despliegues se hayan validado.

## Ejecución

    uv run python -m src.select_projects --mode public
    uv run python -m src.select_projects --mode private-local
    uv run python -m unittest tests.test_project_selection -v

El workflow project-selector-preview.yml puede producir semanalmente
una vista previa pública, sin publicar ni modificar el portfolio maestro.

## Limitaciones conocidas

- Un repo con múltiples productos (family-homelab) requiere atribución
  por rutas y scopes: no se puede suponer que todos sus commits son de
  DuránMusic, Spotube o Android Auto a la vez.
- El trabajo local sin commit ni push no es observable desde GitHub.
- Los asuntos de commits no demuestran corrección, madurez ni éxito de CI.
- Un repo con más de 200 commits recientes queda marcado como truncado.
- La incorporación de un proyecto al PDF exige una ficha curada con
  fuentes, capturas, capacidades y limitaciones comprobadas. El selector
  nunca fabrica una ficha ni cambia automáticamente la presentación.
\nLa segunda salida pública, out/project-selection-review.json, compara candidatos\ncon las fichas existentes e indica cuáles requieren evidencias nuevas. Nunca\npromueve proyectos automáticamente ni publica fichas sin una revisión.\n
## Monorepos y scopes privados

Puede crearse un mapeo protegido local components.yml junto al informe privado.
La atribución reconoce únicamente scopes explícitos y disjuntos de commits
convencionales. Los cambios compartidos o ambiguos quedan sin asignar.
El resultado es un indicio inferior de actividad: se deberá contrastar cada
componente contra los archivos modificados antes de usarlo editorialmente.
Este mapeo NO forma parte de GitHub, CI ni la presentación pública.

## Fase de comprobación de evidencias y actividad local

### Evidencia por archivos reales, nunca por ámbito solamente

Los ámbitos de commits de un monorepo pueden señalar productos distintos
aunque ambos modifiquen la misma carpeta de código. En modo privado existe
una prueba acotada adicional:

    uv run python -m src.select_projects --mode private-local --verify-file-paths

Requiere un mapping local protegido, con listas de prefijos de directorio,
junto a la configuración de componentes. Consulta como máximo cinco commits
de código o tests por componente. La verificación agrupa resultados como
exclusive, shared, mixed, no_path_match o fetch_error. Sólo acepta exclusividad
si las rutas observadas pertenecen al componente y no coinciden con otros.
Cuando dos componentes comparten la misma carpeta, se informa como shared,
sin declarar exclusividad ni validación funcional. El informe **no almacena
nombres de ficheros del repositorio privado**. Los cambios de pruebas no
acreditan que las pruebas hayan pasado.

### Inspección de worktrees autorizados

Para registrar cambios locales todavía no representados por GitHub:

    uv run python -m src.local_activity
    uv run python -m src.local_activity --verify-remotes

Consulta únicamente las rutas autorizadas en una lista protegida localmente.
Usa consultas Git de solo lectura, sin git fetch, commit, reset, push ni
modificaciones de otros agentes. No cuenta archivos sin seguimiento.
La verificación optativa ejecuta git ls-remote para saber si la rama
remota coincide con la referencia de seguimiento local, que podría estar
desactualizada. Cuando no coincide, el supuesto número de commits locales
por delante **no se presenta como un número verificado de commits sin subir**.

La auditoría local no cambia puntuaciones; se guarda fuera del repositorio
en un JSON privado (0700/0600). Si existe un mapeo privado y explícito
entre las rutas y las identidades de proyectos, se puede combinar con la
selección privada usando:

    uv run python -m src.private_review

El resultado separa cambios rastreados, ausencia de upstream y divergencias
de referencias. No significa que los cambios estén terminados ni que la
aplicación esté funcionando.

### Alcance de lo que todavía queda

La selección está equipada con señales reales de archivos y worktrees, pero
no incluye por sí misma un ensayo E2E, análisis completo de cada diff,
calificación objetiva de importancia estratégica o autorización para publicar
proyectos privados. La incorporación a un PDF público sigue requiriendo
autorización de contenido y fichas documentales versionadas. Todas estas
operaciones quedan separadas del cron del portfolio maestro y de Drive.
