"""Archivo histórico por fechas reales de GitHub. No escribe state/ ni sube a Drive.

Se usa sólo para los repositorios públicos de config/repos.yml.
No reproduce conclusiones de IA; tampoco atribuye fechas históricas a tags.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import subprocess
from datetime import datetime, time, timedelta, timezone
from pathlib import Path

from github import Auth, Github, GithubException

try:
    from src.collect import collect_closed_issues, collect_closed_prs, collect_commits, load_repos_config
except ModuleNotFoundError:
    from collect import collect_closed_issues, collect_closed_prs, collect_commits, load_repos_config

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT = ROOT / "out" / "backfill"
THEME_PATH = ROOT / "templates" / "theme.css"
LOG = logging.getLogger("backfill")
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")


def parse_utc(value: str) -> datetime:
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"fecha inválida: {value}") from exc
    if dt.tzinfo is None:
        raise ValueError("las fechas deben incluir zona horaria")
    return dt.astimezone(timezone.utc)


def week_windows(start: datetime, end: datetime) -> list[dict]:
    if start.tzinfo is None or end.tzinfo is None or start >= end:
        raise ValueError("intervalo inválido")
    day = start.date() - timedelta(days=start.weekday())
    monday = datetime.combine(day, time.min, tzinfo=timezone.utc)
    result = []
    while monday < end:
        next_monday = monday + timedelta(days=7)
        lower, upper = max(start, monday), min(end, next_monday)
        if lower < upper:
            year, week, _ = monday.isocalendar()
            result.append({"week": f"{year}-W{week:02d}", "since": lower,
                           "until": upper,
                           "partial": lower != monday or upper != next_monday})
        monday = next_monday
    return result


def in_window(value: str | None, lower: datetime, upper: datetime) -> bool:
    return bool(value and lower <= parse_utc(value) < upper)


def safe_text(value: str, limit: int = 160) -> str:
    line = " ".join((value or "").split())
    line = line[:limit] + "…" if len(line) > limit else line
    return (line.replace("<", "&lt;").replace(">", "&gt;")
                .replace(chr(96), "'").replace("|", "/"))


def summarize_week(window: dict, repos: list[dict], max_items: int) -> tuple[str, dict]:
    tick = chr(96)
    content = [
        "---", "marp: true", "theme: devlog", "paginate: true", "size: 16:9",
        "---", "<!-- _class: lead -->", "# Archivo histórico (sin IA)",
        "## " + window["week"],
        window["since"].isoformat() + " a " + window["until"].isoformat()
        + " UTC, extremo final exclusivo",
        "**Semana parcial**" if window["partial"] else "Semana ISO completa",
        "Metadatos de GitHub. Sin narrativas IA, tags ni diffs retroactivos."
    ]
    info = {"week": window["week"], "since": window["since"].isoformat(),
            "until": window["until"].isoformat(), "partial": window["partial"],
            "repos": []}
    for repo in repos:
        commits = [e for e in repo["commits"] if in_window(e.get("date"), window["since"], window["until"])]
        issues = [e for e in repo["issues_closed"] if in_window(e.get("closed_at"), window["since"], window["until"])]
        prs = [e for e in repo["prs_closed"] if in_window(e.get("closed_at"), window["since"], window["until"])]
        info["repos"].append({"name": repo["name"], "commits": len(commits),
                              "issues_closed": len(issues), "prs_closed": len(prs)})
        content.extend(["---", "## " + safe_text(repo["name"].split("/")[-1]),
                        f"**Commits:** {len(commits)} · **PRs cerradas:** {len(prs)} · **Issues cerradas:** {len(issues)}"])
        if not (commits or prs or issues):
            content.append("_Sin eventos registrados._")
        if commits:
            content.append("### Commits")
            content.extend(
                "- " + tick + c["sha"][:10] + tick + " " + safe_text(c["message"].splitlines()[0])
                for c in commits[:max_items])
            if len(commits) > max_items:
                content.append(f"_Mostrados {max_items} de {len(commits)} commits._")
        if prs:
            content.append("### Pull requests cerradas")
            content.extend(f"- #{p['number']} {safe_text(p['title'])}" for p in prs[:max_items])
            if len(prs) > max_items:
                content.append(f"_Mostradas {max_items} de {len(prs)} PRs._")
        if issues:
            content.append("### Issues cerradas")
            content.extend(f"- #{i['number']} {safe_text(i['title'])}" for i in issues[:max_items])
            if len(issues) > max_items:
                content.append(f"_Mostradas {max_items} de {len(issues)} issues._")
    return "\n\n".join(content) + "\n", info


def collect_public_repos(gh: Github, start: datetime, end: datetime, config: dict) -> list[dict]:
    configs = config.get("repos", [])
    if not configs:
        raise ValueError("lista de repositorios vacía")
    results = []
    for item in configs:
        name = item["name"]
        try:
            repo = gh.get_repo(name)
        except GithubException as exc:
            raise RuntimeError(f"consulta fallida: {name}: {exc}") from exc
        if repo.private:
            raise RuntimeError(f"repositorio privado prohibido: {name}")
        until_inclusive = end - timedelta(microseconds=1)
        commits, _ = collect_commits(repo, start, until_inclusive)
        issues = collect_closed_issues(repo, start, until_inclusive)
        prs = collect_closed_prs(repo, start, until_inclusive)
        results.append({"name": name, "commits": commits, "issues_closed": issues, "prs_closed": prs})
        LOG.info("%s: %d commits, %d issues, %d PRs", name, len(commits), len(issues), len(prs))
    return results


def write_backfill(start: datetime, end: datetime, repos: list[dict], target: Path,
                   max_items: int = 15, pdf: bool = False) -> list[dict]:
    if not 1 <= max_items <= 50:
        raise ValueError("max_items debe estar entre 1 y 50")
    windows = week_windows(start, end)
    target.mkdir(parents=True, exist_ok=True)
    manifest = []
    for window in windows:
        markdown, info = summarize_week(window, repos, max_items)
        src = target / (window["week"] + ".md")
        src.write_text(markdown, encoding="utf-8")
        if pdf:
            marp = shutil.which("marp")
            if not marp:
                raise RuntimeError("marp no instalado")
            subprocess.run([marp, str(src), "--pdf", "--theme-set", str(THEME_PATH),
                            "-o", str(target / (window["week"] + ".pdf"))], check=True)
        manifest.append(info)
        LOG.info("generada %s (%s repos)", window["week"], len(repos))
    (target / "manifest.json").write_text(json.dumps({
        "source": "public-github-metadata", "model": None, "drive_uploaded": False,
        "state_modified": False, "weeks": manifest
    }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--since", required=True)
    parser.add_argument("--until", required=True)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--max-items", type=int, default=15)
    parser.add_argument("--pdf", action="store_true")
    args = parser.parse_args()
    since, until = parse_utc(args.since), parse_utc(args.until)
    if since >= until or until - since > timedelta(days=365):
        parser.error("intervalo no válido o superior a un año")
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_PAT")
    if not token:
        parser.error("falta GITHUB_TOKEN o GH_PAT")
    gh = Github(auth=Auth.Token(token))
    repos = collect_public_repos(gh, since, until, load_repos_config())
    weeks = write_backfill(since, until, repos, args.output_dir, args.max_items, args.pdf)
    LOG.info("%d semanas, sin publicación ni cambios en state", len(weeks))


if __name__ == "__main__":
    main()
