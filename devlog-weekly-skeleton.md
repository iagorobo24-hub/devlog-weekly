# devlog-weekly — esqueleto

Brief para pasarle a la sesión de Claude Code. Contiene la estructura de archivos,
los contratos entre pasos y el workflow. La sesión rellena la lógica.

---

## Qué es

Cron semanal que lee tus repos (privados y públicos), analiza el desarrollo real
de la semana, y genera un deck que se sube solo a Drive.

**Corre en GitHub Actions**, no en el Chromebook. Motivo: si el portátil está apagado
el lunes por la mañana, el cron no dispara. Actions corre siempre.

---

## Estructura de archivos

```
devlog-weekly/
├── .github/
│   └── workflows/
│       └── weekly.yml
├── src/
│   ├── collect.py        # GitHub → JSON. Sin IA.
│   ├── synthesize.py     # JSON → narrativa. Única llamada al modelo.
│   ├── render.py         # narrativa → deck. Determinista.
│   └── publish.py        # deck → Drive.
├── templates/
│   └── deck.md.j2        # plantilla Marp
├── config/
│   └── repos.yml         # qué repos, cuáles son de escaparate
├── state/                # commiteado por el propio workflow
│   ├── last_run.json
│   └── narrative/
│       └── <repo>.md     # historial acumulado por proyecto
├── out/                  # gitignored
├── pyproject.toml
└── README.md
```

---

## Contratos entre pasos

Cada script lee un archivo y escribe otro. Nada de pasarse objetos en memoria —
así puedes correr cualquier paso suelto mientras desarrollas.

| Script | Lee | Escribe |
|---|---|---|
| `collect.py` | `config/repos.yml`, `state/last_run.json` | `out/collected.json` |
| `synthesize.py` | `out/collected.json`, `state/narrative/*` | `out/summaries.json`, actualiza `state/narrative/*` |
| `render.py` | `out/summaries.json`, `templates/deck.md.j2` | `out/deck.md` → `out/deck.pdf` |
| `publish.py` | `out/deck.pdf` | Drive |

---

## config/repos.yml

```yaml
defaults:
  since_days: 7

repos:
  - name: iago/gestionab2b
    showcase: true
    pitch: "SaaS de gestión de stock B2B con copiloto de IA integrado"
  - name: iago/engram
    showcase: true
    pitch: "Sistema de memoria en SQLite con FTS5 para agentes"
  - name: iago/sonex
    showcase: false
```

`showcase` y `pitch` los pones tú a mano. Así decides qué proyectos son de
escaparate en vez de que lo adivine el modelo. `showcase: false` sigue apareciendo
en el informe semanal pero no en el deck maestro.

---

## collect.py — qué recoge

Por cada repo, desde `last_run`:

- commits: mensaje, autor, fecha, SHA
- diff stats agregados: archivos tocados, líneas +/-
- issues y PRs cerrados
- tags nuevos
- lenguajes (por si cambia el peso)
- primeras ~40 líneas del README

Cero IA en este paso. Usa `PyGithub` o `gh` CLI. Sale un JSON plano.

---

## synthesize.py — la única llamada al modelo

Una llamada **por repo**, con el JSON ya condensado más la narrativa acumulada de
semanas anteriores. Eso es lo que hace que escriba *qué cambió* en vez de repetir
*qué es el proyecto* todas las semanas.

Modelo: Haiku o Gemini Flash. Con este volumen son céntimos al mes.

Prompt base:

```
Eres un analista técnico. Te paso la actividad de esta semana en un repo
y el historial de lo que ya se ha contado en semanas anteriores.

HISTORIAL PREVIO:
{narrativa_acumulada}

ACTIVIDAD DE ESTA SEMANA:
{json_recogido}

Devuelve JSON, sin markdown ni preámbulo, con estas claves:
- "titular": una línea, qué es lo importante de esta semana
- "avances": 2-4 bullets de lo que se movió de verdad
- "estado": en qué punto está el proyecto ahora
- "narrativa_actualizada": el historial previo actualizado con esta semana,
  máximo 200 palabras, para pasártelo la semana que viene

Si la actividad es trivial (typos, bumps de dependencias), dilo y no infles.
```

Ese último renglón importa. Si no, te escribe medio deck sobre un cambio en el
`.gitignore`.

---

## render.py — deck determinista

Marp: markdown → PDF. La plantilla es fija, el modelo solo aporta el texto.

```bash
marp out/deck.md --pdf --allow-local-files
```

Si prefieres PPTX editable, `marp --pptx` o python-pptx.

---

## publish.py — Drive

`rclone` con service account. Estructura:

```
Portfolio/
├── semanal/
│   └── 2026-W35/
│       └── devlog.pdf
├── master/
│   └── portfolio.pdf
└── assets/
```

---

## .github/workflows/weekly.yml

```yaml
name: devlog semanal

on:
  schedule:
    - cron: '0 7 * * MON'   # UTC. En horario de verano español son las 09:00.
  workflow_dispatch:         # para dispararlo a mano mientras desarrollas

permissions:
  contents: write            # necesario para commitear state/

jobs:
  devlog:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: astral-sh/setup-uv@v3
      - run: uv sync

      - uses: actions/setup-node@v4
      - run: npm install -g @marp-team/marp-cli

      - name: Recoger
        run: uv run python src/collect.py
        env:
          GH_PAT: ${{ secrets.GH_PAT }}

      - name: Sintetizar
        run: uv run python src/synthesize.py
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}

      - name: Renderizar
        run: uv run python src/render.py

      - name: Publicar
        run: uv run python src/publish.py
        env:
          RCLONE_CONF: ${{ secrets.RCLONE_CONF }}

      - name: Guardar estado
        run: |
          git config user.name "devlog-bot"
          git config user.email "bot@users.noreply.github.com"
          git add state/
          git diff --staged --quiet || git commit -m "state: semana $(date +%Y-W%V)"
          git push
```

**Secrets a configurar en Settings → Secrets and variables → Actions:**

- `GH_PAT` — token clásico con scope `repo` (hace falta para leer los privados;
  el `GITHUB_TOKEN` por defecto solo ve este repo)
- `ANTHROPIC_API_KEY`
- `RCLONE_CONF` — contenido del `rclone.conf` con la service account de Drive

---

## Orden de desarrollo

1. `collect.py` solo. Lo corres a mano, miras el JSON, ajustas qué recoges.
2. `synthesize.py` con ese JSON de input. Iteras el prompt hasta que salga bien.
   Aquí es donde se va el tiempo, y es normal.
3. `render.py` + plantilla Marp.
4. `publish.py` y rclone.
5. Envuelves en el workflow. Lo pruebas con `workflow_dispatch` antes de fiarte del cron.

El vídeo (ffmpeg + Piper TTS sobre el deck) y el deck maestro por umbral se dejan
para cuando lo anterior lleve dos semanas corriendo sin tocarlo.
