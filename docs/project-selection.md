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

## Evidencia de calidad y fichas nuevas

La selección no equivale a validación técnica. Existe un segundo comprobador
público, src.audit_project_quality, que examina por cada candidato:
README, rutas reales de tests, workflows y ejecuciones push de CI del
commit EXACTO de la rama predeterminada durante 30 días. Una CI antigua o
sobre otra rama no certifica el HEAD. Las pruebas de hardware, QA móvil y
E2E se contrastan por separado; una carpeta de tests no equivale a pruebas
pasadas.

El resultado público se guarda en out/project-quality-public.json y se
combina con src.selection_review; no altera las fichas de producción.
src.candidate_profiles comprueba los borradores públicos, con afirmaciones
limitadas y enlaces fijados a revisiones Git SHA completas. Los borradores de
GuiaIA y TIA Portal RocaRoibas permanecen en
content/portfolio/candidates/: draft_only, sin publicación automática,
con advertencias de validación real y autorización editorial pendiente.

Para los candidatos privados existe src.private_project_quality: solo puede
ejecutarse localmente y produce un JSON con permisos 0600 dentro de
~/.local/share/devlog-weekly/restricted. No imprime los nombres y queda
prohibido en CI. src.private_review incorpora los estados de CI a sus
señales de worktrees, pero deja explícitamente la importancia estratégica como
requires_owner_review. No se inventan prioridades ni se importan datos
privados a las fichas públicas. La apertura de contenido privado a terceros o
a un PDF público necesita una autorización explícita sobre qué mostrar.

### Límites editoriales todavía pendientes

- Certificar ejecución real de los candidatos en entornos relevantes.
- Contrastar diffs, tests y capturas para decidir qué logros pueden afirmarse.
- Confirmar con el propietario el peso estratégico de cada producto.
- Decidir qué proyectos privados, si alguno, pueden tener una versión pública.
- Incorporar únicamente los proyectos aprobados al portfolio maestro,
  conservando el diseño validado.


## Fase estratégica: actividad, importancia y calidad son distintas

El informe público out/project-strategy-public.json añade una triage que
considera prioridades editoriales explícitas del archivo de configuración,
evidencia de CI sobre HEAD, rutas de pruebas y existencia de borradores
versionados. Un proyecto con alta importancia pero CI pendiente queda como
strategic_high_requires_verification; si la CI del HEAD falla se clasifica
block_until_ci_diagnosis sin esconder el fallo por volumen de commits.

Incluso un proyecto con CI correcta y ficha válida queda en
candidate_for_manual_review: no se autopublica. Las fichas deben estar
fijadas al HEAD comprobado y no contener advertencias de revisión obsoleta.
Si no existe prioridad expresa, el motor registra not_defined y no la
infiere de la actividad reciente.

La estrategia privada se mantiene estrictamente local:
python -m src.private_strategy produce un informe 0600 con propuestas
temporales en strategic-priorities.yml fuera del repositorio. El estado
inferred_proposal nunca equivale a explicit_owner, y el resultado mantiene
publishable: false en todas sus filas. Se incluyen proyectos exclusivamente
locales sin confundir sus archivos modificados con commits de GitHub.

El diseño y la publicación del portfolio maestro siguen congelados.
Para cerrarlos faltan autorización de exposición de cada proyecto privado,
evidencia funcional y aprobación editorial del contenido final.


Las prioridades configuradas para los proyectos públicos constituyen
propuestas editoriales del sistema, no prioridades ratificadas por el usuario.
La salida lo señala como proposed_public_config_not_owner_confirmed. No debe
interpretarse el valor 5/5 como una aprobación o una prueba de mayor valor.


La vista previa pública produce asimismo out/portfolio-content-proposal.md:
una propuesta legible con la selección, CI del HEAD, fuentes fijadas a SHA y
una lista de condiciones que aún impiden la publicación. No usa el PDF de
producción, no accede a repositorios privados y no contiene conclusiones
automáticas de éxito funcional.

## Corrección de cobertura editorial (29-10-2026)

Contrato de impacto: no cambiar la estética, PDFs publicados, Drive, repositorios
de terceros ni el protocolo de autorización. Evitar que top_n limite el
descubrimiento o descarte candidatos relevantes.

- El primer grupo ranked sigue limitado por top_n para presentación; other_active
  conserva las identidades y métricas completas de los demás candidatos
  sustantivamente activos, en vez de un resumen incompleto.
- Las evaluaciones de calidad pública y privada, la triage estratégica y la
  revisión editorial consideran tanto ranked como other_active. Se verifican
  explícitamente visibilidad, identidad y duplicados; ningún hallazgo acredita
  funcionalidad E2E ni concede publicación.
- La estrategia pública conserva además una lista separada de proyectos
  históricos con prioridad editorial declarada (2 o superior), sin actividad
  sustantiva reciente. No se someten a aprobación ni se confunden con proyectos
  activos, ya que falta evidencia actual. Las prioridades continúan pendientes
  de ratificación por el propietario.
- Los informes privados permanecen exclusivamente en el directorio local
  protegido 0700/0600. La ejecución CI está prohibida para ellos y el
  portfolio público no los lee.
- Los límites explícitos se mantienen: 100 grupos evaluados como máximo,
  procedencia por revisión y sin autopublicación.
- El PSM del repositorio mantiene su baseline antiguo sin recertificar;
  este cambio requiere validación local y CI independiente.

## Preflight de integración pública

La evaluación src.portfolio_release_review considera los candidatos ranked
y other_active con identidades y revisiones coherentes. Las fichas deben
tener referencias versionadas, la CI debe coincidir exactamente con la
revisión y las entradas privadas se rechazan. El informe aislado en
out/portfolio-release-review.json distingue pruebas pendientes, capturas
reales autorizadas y aprobación editorial del propietario.

El resultado es de lectura y propuesta: ninguna CI verde ni prioridad
estratégica permiten autopublicación. La selección original del portfolio,
el diseño del PDF y Google Drive permanecen inalterados.

El preflight también rechaza instantáneas de selección o calidad con más
de 36 horas, marcas temporales futuras, y seguimiento público
contaminado por elementos privados.
