# Portfolio Maestro V3 — propuesta editorial separada de producción

La revisión de GitHub del 29/10/2026 confirmó **nueve repositorios públicos**,
**cinco candidatos activos**, **cinco borradores fijados al HEAD** y **15 rutas
de referencia localizadas**. Se conservaron los dos casos oficiales; ningún
candidato está aprobado para publicación.

## Qué cambia

1. El selector diferencia explícitamente **caso publicado**, **ficha candidata
   preparada** y **aprobación técnica/editorial**. Que cuatro candidatos
   no figuren en el PDF oficial **no** significa que falten cuatro fichas.
2. Las cinco fichas aportan su narrativa de presentación y limitaciones,
   siempre asociadas a una revisión pública y etiquetadas como borrador.
3. El nuevo generador `src.render_portfolio_proposal` crea una composición
   de **ocho diapositivas 16:9** en
   `out/portfolio-proposal-v3.md` con manifiesto y SHA-256.
4. El workflow público añade ambos archivos al artefacto de revisión,
   sin modificar `content/portfolio/projects.yml`, PDFs publicados ni Drive.

## Composición recomendada (provisional)

- **GuiaIA** y **TIA Portal RocaRoibas**: foco narrativo (prioridades declaradas
  5 y 4; GuiaIA no está validado funcionalmente en main, TIA conserva CI
  correcta al HEAD pero no demuestra ejecución real con TIA).
- **Awesome TIA Portal** y **ATM10 Sky es_es**: complementarios documentales.
  No se sobreinterpretan las fichas, capturas ni validaciones parciales.
- **AUTOMATON**: laboratorio con CI fallida en el HEAD, separado del
  protagonismo y no representado como producto estable.
- **Awesome TIA** y **PFC Tools**, casos actualmente publicados, se conservan
  íntegros hasta revisar cualquier sustitución.

El generador deriva las prioridades del archivo público de configuración y
del estado de CI, pero **no** convierte una puntuación en aprobación.
Si la auditoría de referencias no confirma el SHA, no utiliza el texto de la
ficha como prueba. Los nombres y enlaces se escapan y se verifican; los
repositorios privados quedan fuera.

## Pendiente

La propuesta es **Markdown de diseño editorial**, no un nuevo PDF público.
La fase visual debe exportarla a PDF, revisar páginas y enlaces, y obtener
validación independiente y autorización antes de reemplazar el portfolio.
