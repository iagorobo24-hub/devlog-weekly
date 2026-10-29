# Control automático de cobertura editorial pública

El pipeline de selección pública ahora termina con un informe adicional,
`out/editorial-coverage-public.json` y `out/editorial-coverage-public.md`.

## Función

Este control relaciona **la misma instantánea pública** de selección,
calidad de CI, prioridades, fichas candidatas, auditoría de existencia de
fuentes y preflight de publicación. Rechaza entradas privadas, corruptas,
desincronizadas o que parezcan autorizar publicación.

Para cada candidato activo registra separadamente:

- Si existe una ficha y está fijada al HEAD actual de la rama por defecto.
- Si sus rutas de referencia se han localizado en GitHub al SHA exacto.
- El resultado de CI **en la rama predeterminada**, independiente de CI de
  ramas de trabajo.
- Los bloqueos pendientes de prueba funcional, capturas autorizadas y
  aprobación editorial del propietario.

Las fichas ausentes u obsoletas se identifican como pendientes, no como
proyectos terminados. La auditoría es estructural: **una ruta localizada
no prueba que su afirmación sea verdadera**. Las pruebas de CI tampoco
demuestran comportamiento en Minecraft, TIA Portal ni un cliente real.

Este informe no reemplaza ni publica el PDF, no consulta repositorios
privados ni modifica Drive. El workflow programado de los lunes mantiene
su frecuencia y permisos originales.

## Interpretación de resultados

La cobertura de fichas en HEAD puede llegar a ser completa mientras
`publication_approved_count` permanece en **cero**, porque publicar
requiere verificación funcional independiente y aprobación explícita.

Para la ejecución completa y actualizada del pipeline se necesita un
nuevo run del workflow de selección; **la CI normal del repositorio no
equivale a ejecutar ese pipeline**. La ejecución programada existente
será el primer mecanismo ordinario para obtener nuevos resultados.
