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
OpenAI. Por defecto se usa FALLBACK_MODELS, una cadena ordenada por calidad
real observada (no solo tamaño): nvidia/llama-3.3-nemotron-super-49b-v1
ganó tras comparar en real contra meta/llama-3.1-8b-instruct (demasiado
genérico) y meta/llama-3.1-70b-instruct / meta/llama-3.3-70b-instruct (más
grandes, pero ambos confundían el 'pitch' estático de config con actividad
de esta semana, justo lo que el prompt pide evitar). Ninguno es el modelo
más grande del catálogo NIM a propósito: los flagship/frontera
(nemotron-ultra-253b, nemotron-3-ultra-550b, etc.) reciben más tráfico
gratuito y se caen o rate-limitan más.

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
    "nvidia/llama-3.3-nemotron-super-49b-v1.5",
    "openai/gpt-oss-20b",
    "nvidia/nvidia-nemotron-nano-9b-v2",
]
ATTEMPTS_PER_MODEL = 2
RETRY_DELAY_SECONDS = 3

MAX_COMMITS_LISTED = 60
REQUIRED_KEYS = {"titular", "avances", "estado", "narrativa_actualizada"}

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("synthesize")

PROMPT_TEMPLATE = """Eres un analista técnico. Te paso la actividad de esta semana en un repo
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
    commit_titles = [c["message"].splitlines()[0] for c in repo["commits"][:MAX_COMMITS_LISTED]]
    return {
        "repo": repo["name"],
        "pitch": repo.get("pitch"),
        "periodo": {"desde": repo["since"], "hasta": repo["until"]},
        "diff_stats": repo["diff_stats"],
        "commits": {
            "total": len(repo["commits"]),
            "titulos": commit_titles,
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
        results.append(
            {
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
