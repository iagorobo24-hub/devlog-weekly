"""GitHub -> JSON. Sin IA.

Lee config/repos.yml y state/last_run.json, recorre cada repo desde la fecha
del último run (o `since_days` si es la primera vez), y escribe out/collected.json
con la actividad cruda de la semana.

No actualiza state/last_run.json en el mismo run: eso pasa con el modo
--commit-state, pensado para correr como último step del pipeline (después de
que synthesize/render/publish hayan salido bien). Así si algo peta a mitad,
la ventana de esta semana sigue disponible para reintentarlo.

Flags para iterar en desarrollo:
  --since 7d|30d|<ISO date>   fuerza la ventana, ignora state/ y since_days
  --no-state                  no lee state/last_run.json (como si fuera la primera vez)
  --commit-state              no recoge nada: lee out/collected.json ya generado
                               y escribe state/last_run.json a partir de ahí
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml
from github import Auth, Github, GithubException

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config" / "repos.yml"
LAST_RUN_PATH = ROOT / "state" / "last_run.json"
OUT_PATH = ROOT / "out" / "collected.json"

README_EXCERPT_LINES = 40
DURATION_RE = re.compile(r"^(\d+)([dhw])$")

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("collect")


def to_utc(dt: datetime | None) -> datetime | None:
    """PyGithub a veces da naive, a veces aware. Todo a UTC aware antes de comparar."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def parse_since_arg(value: str, now: datetime) -> datetime:
    match = DURATION_RE.match(value)
    if match:
        amount, unit = match.groups()
        delta = {"d": timedelta(days=int(amount)), "h": timedelta(hours=int(amount)), "w": timedelta(weeks=int(amount))}[unit]
        return now - delta
    return to_utc(datetime.fromisoformat(value))


def load_repos_config() -> dict:
    with CONFIG_PATH.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_last_run() -> dict:
    if not LAST_RUN_PATH.exists():
        return {}
    with LAST_RUN_PATH.open(encoding="utf-8") as f:
        return json.load(f) or {}


def save_last_run(last_run: dict) -> None:
    LAST_RUN_PATH.write_text(json.dumps(last_run, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def resolve_since(repo_cfg: dict, defaults: dict, prev_state: dict, now: datetime, forced_since: datetime | None) -> datetime:
    if forced_since is not None:
        return forced_since
    if "since" in prev_state:
        return to_utc(datetime.fromisoformat(prev_state["since"]))
    since_days = repo_cfg.get("since_days", defaults.get("since_days", 7))
    return now - timedelta(days=since_days)


def collect_commits(repo, since: datetime, until: datetime) -> tuple[list[dict], list]:
    """Solo metadatos (sha/autor/fecha/mensaje). Nada de .stats/.files aquí:
    eso dispararía una llamada a la API por commit."""
    commits = []
    raw = list(repo.get_commits(since=since, until=until))  # más nuevo primero
    for commit in raw:
        commit_data = commit.commit
        author_date = to_utc(commit_data.author.date) if commit_data.author else None
        commits.append(
            {
                "sha": commit.sha,
                "author": commit_data.author.name if commit_data.author else None,
                "date": author_date.isoformat() if author_date else None,
                "message": commit_data.message,
            }
        )
    return commits, raw


def collect_diff_stats(repo, commits_desc: list) -> dict:
    """Agregado en una sola llamada vía compare, en vez de N llamadas a commit.stats."""
    if not commits_desc:
        return {"files_changed": 0, "additions": 0, "deletions": 0}

    head_sha = commits_desc[0].sha
    oldest = commits_desc[-1]
    parents = oldest.parents
    # sin padre = primer commit del repo; su propio diff no queda incluido en el compare
    base_sha = parents[0].sha if parents else oldest.sha

    try:
        comparison = repo.compare(base_sha, head_sha)
    except GithubException as e:
        log.warning("no se pudo comparar %s...%s en %s: %s", base_sha, head_sha, repo.full_name, e)
        return {"files_changed": 0, "additions": 0, "deletions": 0}

    files = comparison.files or []
    return {
        "files_changed": len(files),
        "additions": sum(f.additions for f in files),
        "deletions": sum(f.deletions for f in files),
    }


def collect_closed_issues(repo, since: datetime, until: datetime) -> list[dict]:
    issues = []
    for issue in repo.get_issues(state="closed", since=since, sort="updated", direction="desc"):
        if issue.pull_request is not None:
            continue  # la API de issues incluye PRs, los descartamos
        closed_at = to_utc(issue.closed_at)
        if closed_at is None or not (since <= closed_at <= until):
            continue
        issues.append({"number": issue.number, "title": issue.title, "closed_at": closed_at.isoformat()})
    return issues


def collect_closed_prs(repo, since: datetime, until: datetime) -> list[dict]:
    prs = []
    for pr in repo.get_pulls(state="closed", sort="updated", direction="desc"):
        if to_utc(pr.updated_at) < since:
            break  # ordenados por updated desc: a partir de aquí ya son viejas
        closed_at = to_utc(pr.closed_at)
        if closed_at is None or not (since <= closed_at <= until):
            continue
        prs.append(
            {
                "number": pr.number,
                "title": pr.title,
                "merged": pr.merged_at is not None,
                "closed_at": closed_at.isoformat(),
            }
        )
    return prs


def collect_tags(repo, previously_seen: set[str]) -> tuple[list[str], list[str]]:
    """Diferencia de conjuntos contra lo visto en el run anterior. Una sola llamada,
    determinista, sin depender de la fecha del commit al que apunta el tag."""
    current = [t.name for t in repo.get_tags()]
    new = [name for name in current if name not in previously_seen]
    return current, new


def collect_readme_excerpt(repo) -> str | None:
    try:
        readme = repo.get_readme()
    except GithubException:
        return None
    text = readme.decoded_content.decode("utf-8", errors="replace")
    lines = text.splitlines()[:README_EXCERPT_LINES]
    return "\n".join(lines)


def collect_repo(gh: Github, repo_name: str, repo_cfg: dict, since: datetime, until: datetime, previously_seen_tags: set[str]) -> dict | None:
    log.info("recogiendo %s (desde %s)", repo_name, since.isoformat())
    try:
        repo = gh.get_repo(repo_name)
    except GithubException as e:
        log.error("no se pudo acceder a %s: %s", repo_name, e)
        return None

    commits, commits_raw = collect_commits(repo, since, until)
    diff_stats = collect_diff_stats(repo, commits_raw)
    issues_closed = collect_closed_issues(repo, since, until)
    prs_closed = collect_closed_prs(repo, since, until)
    tags_all, tags_new = collect_tags(repo, previously_seen_tags)
    try:
        # PyGithub inyecta una clave "url" en dicts crudos de respuestas GET
        # (Requester.__postProcess); nos quedamos solo con los pares lenguaje->bytes.
        languages = {k: v for k, v in repo.get_languages().items() if isinstance(v, int)}
    except GithubException:
        languages = {}
    readme_excerpt = collect_readme_excerpt(repo)

    return {
        "name": repo_name,
        "showcase": repo_cfg.get("showcase", False),
        "pitch": repo_cfg.get("pitch"),
        "since": since.isoformat(),
        "until": until.isoformat(),
        "commits": commits,
        "diff_stats": diff_stats,
        "issues_closed": issues_closed,
        "prs_closed": prs_closed,
        "tags_new": tags_new,
        "tags_all": tags_all,
        "languages": languages,
        "readme_excerpt": readme_excerpt,
    }


def commit_state() -> None:
    """Lee out/collected.json (ya generado por un run normal) y confirma en
    state/last_run.json la ventana de cada repo. No toca la API de GitHub."""
    if not OUT_PATH.exists():
        log.error("%s no existe todavía; corre collect.py sin --commit-state primero", OUT_PATH)
        sys.exit(1)

    collected = json.loads(OUT_PATH.read_text(encoding="utf-8"))
    last_run = load_last_run()
    for repo in collected["repos"]:
        last_run[repo["name"]] = {"since": repo["until"], "tags_seen": repo["tags_all"]}
    save_last_run(last_run)
    log.info("estado confirmado para %d repos", len(collected["repos"]))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--since", help="Fuerza la ventana (ej. '7d', '30d', o fecha ISO). Ignora state/ y since_days.")
    parser.add_argument("--no-state", action="store_true", help="No lee state/last_run.json.")
    parser.add_argument("--commit-state", action="store_true", help="No recoge: confirma el estado a partir de out/collected.json.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.commit_state:
        commit_state()
        return

    token = os.environ.get("GH_PAT")
    if not token:
        log.error("falta la variable de entorno GH_PAT")
        sys.exit(1)

    config = load_repos_config()
    defaults = config.get("defaults", {})
    repos_cfg = config.get("repos", [])
    if not repos_cfg:
        log.error("config/repos.yml no define ningún repo")
        sys.exit(1)

    now = to_utc(datetime.now(timezone.utc))
    forced_since = parse_since_arg(args.since, now) if args.since else None
    last_run = {} if args.no_state else load_last_run()

    gh = Github(auth=Auth.Token(token))

    results = []
    for repo_cfg in repos_cfg:
        repo_name = repo_cfg["name"]
        prev_state = last_run.get(repo_name, {})
        since = resolve_since(repo_cfg, defaults, prev_state, now, forced_since)
        previously_seen_tags = set(prev_state.get("tags_seen", []))
        data = collect_repo(gh, repo_name, repo_cfg, since, now, previously_seen_tags)
        if data is not None:
            results.append(data)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    output = {"generated_at": now.isoformat(), "repos": results}
    OUT_PATH.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    log.info("escrito %s (%d repos) — corre con --commit-state al final del pipeline para confirmar la ventana", OUT_PATH, len(results))


if __name__ == "__main__":
    main()
