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

## Deck de comparación exclusivamente editorial

La nueva salida de src.render_portfolio_review conserva las diapositivas
del portfolio vigente, incorpora una página de revisión, un índice de
candidatos públicos y fichas provisionales con referencias SHA para
aquellos que tienen pruebas documentales. Cada página añade
BORRADOR INTERNO - NO PUBLICAR.

El workflow automático crea únicamente Markdown y un manifiesto
con hash SHA-256. No requiere Chrome, no genera el PDF oficial y no
publica en Drive. En una máquina de edición, el mismo comando genera
HTML aislado; opcionalmente se convierte a PDF con Marp y Chrome,
fuera de portfolio-v2.pdf.

La ficha de TIA Portal RocaRoibas verifica referencias de la revisión
5bb5397297724e2c3a4c1c7e67b4132368f12516: README, pruebas,
workflow y recurso visual. La CI de ese SHA terminó correctamente.
Eso no prueba una sesión real de TIA Portal ni de Openness/PLCSIM.

PSM: la línea base histórica sigue sin reconciliar; esta ampliación de
la revisión no cambia psm.source.commit.

## Comprobación real de enlaces de las fichas públicas

La auditoría src.audit_candidate_sources valida referencias contra el
contenido GitHub del SHA exacto, después de verificar que el repositorio
es público. Comprueba archivo frente a directorio y distingue fuente
presente, 404, tipo erróneo, fallo transitorio y revisión obsoleta.
No lee repositorios privados. La API con errores de cuota nunca se
traduce en éxito; tampoco en un falso archivo inexistente.

La revisión editorial exige el informe sincronizado con calidad y
selección. Una fuente sin comprobación bloquea sus diapositivas
candidatas. Cuando hay CI exitosa comprobada en el HEAD, se conserva
por separado el enlace de su ejecución, nunca se confunde con el
archivo de configuración del workflow.

La existencia de un archivo sólo prueba procedencia documental, no
que la afirmación sea cierta o esté funcionando. Se preservan las tres
puertas pendientes: prueba funcional independiente, evidencias visuales
autorizadas y aprobación del propietario.

## Evidencia de commits de ramas públicas (29-10-2026)

La auditoría de ramas ahora compara referencias inmutables de dos SHA:
la revisión observada de la rama predeterminada y la punta de cada rama
pública. No usa nombres flotantes para calcular el diff. Una comparación
completa cuya punta no coincida con el SHA observado se descarta y marca
la cobertura como incompleta; los fallos no cuentan como actividad ausente.
Los límites de ramas y commits son estrictos.

Además de recuentos deduplicados, se conservan hasta cinco muestras
recientes de commits clasificados como código o test, con permalink al SHA
público. Son asuntos declarados en commits, no verificaciones de que
el código funciona ni tests realmente pasados. Los enlaces se validan
contra el mismo repositorio antes de incorporarse al informe estratégico
y a la vista previa. Las muestras malformadas, extranjeras o privadas
provocan rechazo; el frontend HTML escapa asuntos de commit.

La propuesta editorial incorpora esos SHA como referencias de revisión.
El deck separado puede añadir una diapositiva de evidencia de ramas, con
sello BORRADOR INTERNO / NO PUBLICAR; nunca sustituye las fichas
aprobadas, la CI de la rama predeterminada ni el PDF de producción.
Un informe antiguo o con cobertura parcial no constituye prueba de
ausencia de trabajo. La línea base PSM sigue sin recertificarse.

## Auditoría acotada de archivos modificados por commits destacados

La fase public_commit_diff_audit analiza exclusivamente muestras públicas
versionadas obtenidas por la auditoría de ramas. Antes de consultar cada
commit comprueba que el repositorio no sea privado. Inspecciona como máximo
cinco commits por repositorio y cien entradas de archivos por commit; los
resultados guardan sólo conteos de tipos code/tests/docs/other, nunca rutas,
contenidos, parches ni datos privados. La auditoría distingue repositorio
inaccesible, SHA discrepante, lista truncada, ausencia de archivos y
documentación sin rutas de código/pruebas identificadas.

El workflow genera out/project-commit-diff-audit-public.json antes de
selección estratégica y revisa correspondencia exacta de snapshot, SHA,
repositorio, permalink y clase declarada. El markdown y el deck de revisión
señalan si se identificaron rutas compatibles con el asunto del commit.
Una carpeta o ruta de tests no demuestra que esos tests se hayan ejecutado;
una ruta de código no demuestra que la funcionalidad funcione.

En la muestra pública de GuiaIA del 29/10/2026 se encontraron cinco
commits con archivos clasificados como código o tests. Cuatro de las cinco
muestras tenían rutas acordes a su categoría declarada y una muestra
categorizada test no tenía ninguna ruta reconocida como tests. Es una
heurística de rutas, no un juicio sobre calidad del commit o éxito de QA.
Nada de esta fase aprueba o publica automáticamente una ficha o PDF.

## CI pública de ramas por SHA, separada de main

La revisión editorial ejecuta public_branch_ci_audit después del barrido de
ramas. Consulta únicamente las puntas SHA de hasta cinco ramas públicas con
commits de código o tests no fusionados recientes. Comprueba el carácter
público de cada repositorio antes de inspeccionar ejecuciones y acota a 20
runs por punta. Cada workflow observado conserva su URL, estado, conclusión
y el SHA exacto. Ningún resultado de la rama se equipara a CI de main.

Los estados posibles distinguen ejecuciones exitosas observadas, fallos,
cancelaciones, pendientes, ausencia de runs, cobertura truncada y error de
consulta. Una colección de runs verdes no demuestra que todos los workflows
relevantes se ejecutaran ni que las funcionalidades se hayan probado en el
entorno real. La capa estratégica comprueba la misma instantánea de selección
y de ramas, y rechaza SHA, repositorios, URLs y resultados inconsistentes.

En la revisión pública del 29/10/2026 de GuiaIA se encontraron cinco puntas
de ramas con un total de 16 ejecuciones de workflow devueltas por GitHub,
todas completadas con éxito. Esto no implica despliegue, juego validado en
Minecraft ni CI correcta en main. Para el portfolio definitivo siguen
pendientes las pruebas funcionales, capturas autorizadas y aprobación editorial.
