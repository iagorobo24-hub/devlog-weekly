"""JSON -> narrativa. Única llamada al modelo (una por repo).

Lee out/collected.json y el historial acumulado en state/narrative/*.md,
y escribe out/summaries.json con lo que dice el modelo de cada repo.

Igual que collect.py, NO toca state/narrative/*.md en el run normal: eso pasa
con --commit-state, pensado como último step del pipeline (después de que
render/publish hayan salido bien). Si algo falla más adelante, el historial
de esta semana no queda a medio escribir, y puedes reintentar sin duplicar
lo ya contado.

Flags para iterar en desarrollo:
  --repo NAME       procesa solo el/los repo(s) indicados (repetible)
  --dry-run         no llama al modelo; imprime el prompt que se enviaría
  --no-state        ignora el historial acumulado (como si fuera la primera vez)
  --commit-state    no sintetiza: escribe state/narrative/*.md a partir de
                     out/summaries.json ya generado
  --model MODEL_ID  fuerza un modelo concreto, sin cadena de fallback

Modelo: NVIDIA NIM (https://integrate.api.nvidia.com/v1), API compatible con
OpenAI. Por defecto se usa FALLBACK_MODELS: openai/gpt-oss-20b fue
validado en la ejecución real del 29-10-2026. Los modelos anteriores
(nemotron-super-v1/v1.5 y los llama de 2026) devolvían HTTP 410.
Las alternativas actuales del catálogo son candidatas, no están validadas
para esta cuenta. NIM_MODEL permite fijar un modelo validado.

Si un modelo falla (red, rate limit, JSON inválido...), se reintenta el
MISMO modelo ATTEMPTS_PER_MODEL veces antes de darlo por caído y pasar al
siguiente de la cadena — fallos puntuales no deben tirar de fallback.

--model fuerza un único modelo, sin cadena (útil para comparar modelos a
mano, como hicimos para elegir el default).

Ojo: no todos los modelos listados en /v1/models están habilitados para
cualquier cuenta — un 404 con "Function ... Not found for account" significa
que ese modelo concreto no está disponible para tu API key, no que el slug
esté mal escrito.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
from datetime import date, datetime
import sys
import time
from pathlib import Path

from openai import OpenAI

ROOT = Path(__file__).resolve().parent.parent
COLLECTED_PATH = ROOT / "out" / "collected.json"
NARRATIVE_DIR = ROOT / "state" / "narrative"
OUT_PATH = ROOT / "out" / "summaries.json"

NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"

# Candidatos del catálogo NVIDIA NIM; la disponibilidad para la cuenta
# se confirma con cada ejecución. Los modelos anteriores expiraron en 2026.
# NIM_MODEL permite forzar un modelo validado desde el entorno.
FALLBACK_MODELS = [
    # Validado con la cuenta en Actions el 2026-10-29 (4/4 repos).
    "openai/gpt-oss-20b",
    # Alternativas del catálogo pendientes de validar para esta cuenta.
    "nvidia/nvidia-nemotron-nano-9b-v2",
    "qwen/qwen3-next-80b-a3b-instruct",
]
ATTEMPTS_PER_MODEL = 2
RETRY_DELAY_SECONDS = 3

MAX_COMMITS_LISTED = 60
REQUIRED_KEYS = {"titular", "avances", "estado", "narrativa_actualizada"}

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("synthesize")

PROMPT_TEMPLATE = """Eres un analista técnico riguroso. Tus únicas evidencias verificables son
los commits (SHA y fecha), issues y PRs del JSON de esta ejecución.
Los títulos de commits NO prueban por sí solos que algo esté desplegado,
sea estable o haya superado pruebas. No afirmes eso sin evidencia.

HISTORIAL ANTERIOR (contexto no recertificado: puede contener errores):
{narrativa_acumulada}

EVENTOS OBSERVADOS EN EL INTERVALO:
{json_recogido}

Devuelve solo JSON válido con las claves:
- "titular": un titular técnico concreto y sobrio
- "avances": 2-4 viñetas concisas, basadas en eventos observados
- "estado": situación acreditada por los eventos; indicar incertidumbre
- "narrativa_actualizada": estado general actualizado (máx. 200 palabras)
No uses etiquetas como Semana 1, Semana 2-10 o fechas deducidas de
las etiquetas de versión. Si el intervalo supera 7 días, trátalo como
actividad acumulada de ese periodo, no como una única semana.
No traslades afirmaciones dudosas del historial como hechos probados.
No inventes resultados, métricas, funcionalidades o fechas.
Una etiqueta nueva detectada no revela cuándo fue creada.
Si solo hay cambios triviales, dilo explícitamente.
"""


def narrative_path(repo_name: str) -> Path:
    safe_name = repo_name.split("/")[-1].replace("/", "_")
    return NARRATIVE_DIR / f"{safe_name}.md"


def load_collected() -> dict:
    if not COLLECTED_PATH.exists():
        log.error("%s no existe; corre collect.py primero", COLLECTED_PATH)
        sys.exit(1)
    return json.loads(COLLECTED_PATH.read_text(encoding="utf-8"))


def load_previous_narrative(repo_name: str) -> str:
    path = narrative_path(repo_name)
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8").strip()


def has_activity(repo: dict) -> bool:
    return bool(repo["commits"] or repo["issues_closed"] or repo["prs_closed"] or repo["tags_new"])


def condense(repo: dict) -> dict:
    """Solo lo que cambió esta semana. README y lenguajes se dejan fuera a
    propósito: son estáticos y empujan al modelo a re-describir el proyecto
    en vez de contar qué se movió (para eso ya están 'pitch' y el historial)."""
    commit_events = [
        {"sha": c["sha"], "fecha": c.get("date"),
         "titulo": c["message"].splitlines()[0]}
        for c in repo["commits"][:MAX_COMMITS_LISTED]
    ]
    return {
        "repo": repo["name"],
        "pitch": repo.get("pitch"),
        "periodo": {"desde": repo["since"], "hasta": repo["until"]},
        "diff_stats": repo["diff_stats"],
        "commits": {
            "total": len(repo["commits"]),
            "eventos": commit_events,
            "truncado": len(repo["commits"]) > MAX_COMMITS_LISTED,
        },
        "issues_cerradas": [{"number": i["number"], "title": i["title"]} for i in repo["issues_closed"]],
        "prs_cerradas": [{"number": p["number"], "title": p["title"], "merged": p["merged"]} for p in repo["prs_closed"]],
        "tags_nuevos": repo["tags_new"],
    }


def build_prompt(repo: dict, previous_narrative: str) -> str:
    condensed = condense(repo)
    return PROMPT_TEMPLATE.format(
        narrativa_acumulada=previous_narrative or "(sin historial previo, es la primera semana)",
        json_recogido=json.dumps(condensed, indent=2, ensure_ascii=False),
    )


def trivial_summary(previous_narrative: str) -> dict:
    return {
        "titular": "Sin actividad esta semana",
        "avances": [],
        "estado": "Sin cambios respecto a la semana anterior." if previous_narrative else "Sin actividad registrada todavía.",
        "narrativa_actualizada": previous_narrative,
        "trivial": True,
        "model_used": None,
    }


def parse_model_json(raw_text: str) -> dict:
    text = raw_text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text.split("\n", 1)[1] if "\n" in text else text
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end == -1:
            raise
        return json.loads(text[start : end + 1])


def call_model_once(client: OpenAI, model: str, prompt: str) -> dict:
    kwargs = dict(
        model=model,
        max_tokens=1500,
        temperature=0.3,
        messages=[{"role": "user", "content": prompt}],
    )
    try:
        # no todos los modelos del catálogo NIM soportan JSON forzado; si el
        # modelo o el backend lo rechaza, reintentamos sin la restricción y
        # confiamos en la instrucción del prompt + el parseo defensivo.
        response = client.chat.completions.create(**kwargs, response_format={"type": "json_object"})
    except Exception as e:
        log.warning("response_format=json_object no soportado por %s (%s), reintento sin él", model, e)
        response = client.chat.completions.create(**kwargs)

    raw_text = response.choices[0].message.content
    if not raw_text:
        raise ValueError(f"{model}: la API devolvió una respuesta sin contenido (reintento)")
    data = parse_model_json(raw_text)
    missing = REQUIRED_KEYS - data.keys()
    if missing:
        raise ValueError(f"faltan claves en la respuesta del modelo: {missing}")
    data.setdefault("trivial", False)
    return data


def call_model_with_fallback(client: OpenAI, model_chain: list[str], prompt: str, repo_name: str) -> dict:
    """Reintenta cada modelo ATTEMPTS_PER_MODEL veces antes de darlo por caído
    y pasar al siguiente de la cadena. Un fallo suelto no debe hacer saltar
    de modelo; varios seguidos con el mismo sí."""
    last_error: Exception | None = None
    for model in model_chain:
        for attempt in range(1, ATTEMPTS_PER_MODEL + 1):
            try:
                data = call_model_once(client, model, prompt)
                if model != model_chain[0]:
                    log.warning("%s: usando modelo de fallback %s tras fallos del/de los anteriores", repo_name, model)
                data["model_used"] = model
                return data
            except Exception as e:
                last_error = e
                log.warning("%s: intento %d/%d con %s falló: %s", repo_name, attempt, ATTEMPTS_PER_MODEL, model, e)
                if attempt < ATTEMPTS_PER_MODEL:
                    time.sleep(RETRY_DELAY_SECONDS)
        log.error("%s: %s no respondió tras %d intentos, paso al siguiente modelo de la cadena", repo_name, model, ATTEMPTS_PER_MODEL)

    raise RuntimeError(f"ningún modelo de la cadena respondió ({', '.join(model_chain)}); último error: {last_error}")


def synthesize_repo(client: OpenAI | None, model_chain: list[str], repo: dict, previous_narrative: str, dry_run: bool) -> dict | None:
    if not has_activity(repo):
        log.info("%s: sin actividad, no llamo al modelo", repo["name"])
        return trivial_summary(previous_narrative)

    prompt = build_prompt(repo, previous_narrative)

    if dry_run:
        print(f"\n{'=' * 80}\n{repo['name']} (cadena: {' -> '.join(model_chain)})\n{'=' * 80}\n{prompt}")
        return None

    log.info("%s: llamando al modelo (%s)", repo["name"], model_chain[0])
    try:
        return call_model_with_fallback(client, model_chain, prompt, repo["name"])
    except Exception as e:
        log.error("%s: fallo al sintetizar: %s", repo["name"], e)
        return None


def commit_state() -> None:
    if not OUT_PATH.exists():
        log.error("%s no existe todavía; corre synthesize.py sin --commit-state primero", OUT_PATH)
        sys.exit(1)
    summaries = json.loads(OUT_PATH.read_text(encoding="utf-8"))
    NARRATIVE_DIR.mkdir(parents=True, exist_ok=True)
    count = 0
    for repo in summaries["repos"]:
        narrative_path(repo["name"]).write_text(repo["narrativa_actualizada"].strip() + "\n", encoding="utf-8")
        count += 1
    log.info("historial confirmado para %d repos", count)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo", action="append", help="Procesa solo este repo (repetible). Por defecto, todos.")
    parser.add_argument("--dry-run", action="store_true", help="No llama al modelo; imprime el prompt.")
    parser.add_argument("--no-state", action="store_true", help="Ignora el historial acumulado en state/narrative/.")
    parser.add_argument("--commit-state", action="store_true", help="No sintetiza: confirma state/narrative/ a partir de out/summaries.json.")
    parser.add_argument(
        "--model",
        default=None,
        help="Fuerza un único modelo de NVIDIA NIM, sin cadena de fallback. "
        f"Por defecto se usa la cadena: {' -> '.join(FALLBACK_MODELS)} (o NIM_MODEL si está definida).",
    )
    return parser.parse_args()


def validate_generated_summary(repo: dict, summary: dict) -> None:
    # A source title is not proof of a claim, but fabricated/misplaced explicit
    # dates can be rejected deterministically before they reach a PDF.
    for key in ("titular", "estado", "narrativa_actualizada"):
        if not isinstance(summary.get(key), str) or not summary[key].strip():
            raise ValueError(f"campo inválido: {key}")
    advances = summary.get("avances")
    if not isinstance(advances, list) or not (1 <= len(advances) <= 8):
        raise ValueError("avances requiere entre 1 y 8 viñetas")
    if not all(isinstance(a, str) and a.strip() for a in advances):
        raise ValueError("viñetas vacías o no textuales")
    interval_start = date.fromisoformat(repo["since"][:10])
    interval_end = date.fromisoformat(repo["until"][:10])
    for item in [summary["titular"], summary["estado"], *advances]:
        if re.search(r"\bsemana\s+\d+(?:\s*[-–]\s*\d+)?\b", item, re.I):
            raise ValueError("numeración de semana sin anclaje factual")
        for value in re.findall(r"\b20\d{2}-\d{2}-\d{2}\b", item):
            when = date.fromisoformat(value)
            if not interval_start <= when <= interval_end:
                raise ValueError(f"fecha fuera del intervalo: {value}")


def verified_sources(repo: dict) -> list[dict]:
    # Enlaces extraídos de GitHub, nunca fabricados por el LLM.
    name = repo["name"]
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", name):
        raise ValueError("repositorio inválido para enlaces")
    base = "https://github.com/" + name
    out = []
    for commit in repo["commits"]:
        sha = commit["sha"]
        if not re.fullmatch(r"[0-9a-fA-F]{7,64}", sha):
            raise ValueError("SHA inválido")
        out.append({"kind": "commit", "id": sha[:10], "title": commit["message"].splitlines()[0],
                    "date": commit.get("date"), "url": f"{base}/commit/{sha}"})
    for pr in repo["prs_closed"]:
        number = int(pr["number"])
        out.append({"kind": "pr", "id": f"PR #{number}", "title": pr["title"],
                    "date": pr["closed_at"], "url": f"{base}/pull/{number}"})
    for issue in repo["issues_closed"]:
        number = int(issue["number"])
        out.append({"kind": "issue", "id": f"Issue #{number}", "title": issue["title"],
                    "date": issue["closed_at"], "url": f"{base}/issues/{number}"})
    return out


def ensure_complete_summaries(repos: list[dict], summaries: list[dict]) -> None:
    """No publicar ni confirmar estado si una síntesis necesaria falló."""
    expected = {repo["name"] for repo in repos}
    actual = {summary["name"] for summary in summaries}
    missing = expected - actual
    if missing or len(summaries) != len(repos):
        raise RuntimeError(f"síntesis incompleta; faltan {sorted(missing)}")


def main() -> None:
    args = parse_args()

    if args.commit_state:
        commit_state()
        return

    api_key = os.environ.get("NVIDIA_API_KEY")
    if not api_key and not args.dry_run:
        log.error("falta la variable de entorno NVIDIA_API_KEY")
        sys.exit(1)

    collected = load_collected()
    repos = collected["repos"]
    if args.repo:
        wanted = {r.lower() for r in args.repo}
        repos = [r for r in repos if r["name"].lower() in wanted]
        if not repos:
            log.error("ninguno de los repos pedidos (%s) está en %s", args.repo, COLLECTED_PATH)
            sys.exit(1)

    client = None if args.dry_run else OpenAI(base_url=NVIDIA_BASE_URL, api_key=api_key)

    explicit_model = args.model or os.environ.get("NIM_MODEL")
    model_chain = [explicit_model] if explicit_model else FALLBACK_MODELS

    results = []
    for repo in repos:
        previous_narrative = "" if args.no_state else load_previous_narrative(repo["name"])
        summary = synthesize_repo(client, model_chain, repo, previous_narrative, args.dry_run)
        if summary is None:
            continue
        if not summary.get("trivial"):
            validate_generated_summary(repo, summary)
        results.append(
            {
                "activity_counts": {
                    "commits": len(repo["commits"]),
                    "prs": len(repo["prs_closed"]),
                    "issues": len(repo["issues_closed"]),
                    "tags": len(repo["tags_new"]),
                },
                "verified_sources": verified_sources(repo),
                "name": repo["name"],
                "showcase": repo["showcase"],
                "pitch": repo["pitch"],
                "since": repo["since"],
                "until": repo["until"],
                **summary,
            }
        )

    if args.dry_run:
        log.info("dry-run: %d prompt(s) generado(s), nada escrito", len(repos))
        return

    ensure_complete_summaries(repos, results)
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    output = {"generated_at": collected["generated_at"], "repos": results}
    OUT_PATH.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    log.info(
        "escrito %s (%d/%d repos) — corre con --commit-state al final del pipeline para confirmar el historial",
        OUT_PATH,
        len(results),
        len(repos),
    )


if __name__ == "__main__":
    main()
