# Catálogo de Invariantes del Sistema (System Invariants)

> **Commit Auditado:** `97a4319bba38bb5a09cfe8be89e58ead54f028a9` | **Framework:** `0.2.0-alpha`

---

| ID | Invariante | Severidad | Método de Control | Test / Verificación |
|---|---|---|---|---|
| `INV-01-GITHUB-API-RATE-LIMIT-AWARE` | **Respeto de Cuotas de API:** La recolección maneja respuestas 429 y cabeceras de rate limit con backoff exponencial. | `HIGH` | `src/collect.py` con manejo de excepciones. | Ejecución de prueba con dry-run |
| `INV-02-DETERMINISTIC-DECK-OUTPUT` | **Idempotencia de Renderizado:** Mismos inputs de actividad producen diapositivas con idéntica estructura y contenido. | `HIGH` | Plantillas Jinja/HTML deterministas en `templates/`. | `src/render.py` |
| `INV-03-NO-HARDCODED-SECRETS` | **Cero Credenciales Estáticas:** `GITHUB_TOKEN` y API keys de LLM se obtienen de variables de entorno seguras. | `CRITICAL` | `os.environ` y archivos de configuración en `config/`. | Análisis estático |
