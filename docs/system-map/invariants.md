# Catálogo de Invariantes del Sistema (System Invariants)

> **Commit Auditado:** `97a4319bba38bb5a09cfe8be89e58ead54f028a9` | **Framework:** `0.2.0-alpha`

---

| ID | Invariante | Severidad | Método de Control | Test / Verificación |
|---|---|---|---|---|
| `INV-01-GITHUB-API-RATE-LIMIT-AWARE` | **Respeto de Cuotas de API:** La recolección maneja respuestas 429 y cabeceras de rate limit con backoff exponencial. | `HIGH` | `src/collect.py` con manejo de excepciones. | Ejecución de prueba con dry-run |
| `INV-02-DETERMINISTIC-DECK-OUTPUT` | **Idempotencia de Renderizado:** Mismos inputs de actividad producen diapositivas con idéntica estructura y contenido. | `HIGH` | Plantillas Jinja/HTML deterministas en `templates/`. | `src/render.py` |
| `INV-03-NO-HARDCODED-SECRETS` | **Cero Credenciales Estáticas:** `GITHUB_TOKEN` y API keys de LLM se obtienen de variables de entorno seguras. | `CRITICAL` | `os.environ` y archivos de configuración en `config/`. | Análisis estático |

---

## Estado observado el 30/10/2026 — sin recertificar el commit histórico

El cuadro anterior describe **la revisión antigua** del PSM. La fuente
`97a4319bba38bb5a09cfe8be89e58ead54f028a9` no está accesible en
el Git local y la API GitHub ha respondido 422. No se pueden mantener
sin reservas sus calificaciones `VERIFIED` para el código actual.

- **INV-01: evidencia parcial.** Hay tratamiento de rate limits y tests
  sintéticos de reintentos. **No** se acredita una caché explícita de
  respuestas y no se han forzado límites reales de GitHub.
- **INV-02: evidencia de contenido/estructura.** Se han ejecutado
  conversiones reales con Marp, pero no está comprobada la igualdad
  byte a byte de PDFs en distintos navegadores, fuentes o entornos.
- **INV-03: evidencia parcial.** Las rutas principales usan variables
  de entorno para secretos; un escaneo limitado de patrones comunes no
  detectó literales evidentes. Eso no es una auditoría integral de
  secretos, dependencias, logs y credenciales previas.

Los contratos nuevos de estado, procedencia, selección editorial y
publicación recuperable se detallan en
[la auditoría del estado actual](CURRENT-REVIEW-2026-10-30.md).
No se debe interpretar esta nota como una actualización de
`manifest.yaml`, `verified_at` o de los estados históricos.
