"""Discover and rank projects without LLM. Public outputs never include private metadata.

Public preview: python -m src.select_projects
Local/private (NEVER for Actions): python -m src.select_projects --mode private-local
Both are READ-ONLY against GitHub. Neither alters state/ nor the published PDF.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from itertools import islice
import json
import logging
import os
from pathlib import Path
import subprocess
import tempfile

from github import Auth, Github
import yaml

try:
    from src.project_selection_core import build_selection, configured_projects
except ModuleNotFoundError:
    from project_selection_core import build_selection, configured_projects

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config" / "project-selection.yml"
PUBLIC_OUT = ROOT / "out" / "project-selection-public.json"
PRIVATE_DIR = Path.home() / ".local" / "share" / "devlog-weekly" / "restricted"
PRIVATE_OUT = PRIVATE_DIR / "project-selection-private.json"
LOG = logging.getLogger("project-selection")


def credentials() -> str:
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_PAT")
    if not token:
        result = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True,
                                check=False, timeout=12)
        if result.returncode == 0:
            token = result.stdout.strip()
    if not token:
        raise RuntimeError("falta token de lectura GitHub para descubrir proyectos")
    return token


def to_iso(dt) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def discover(gh: Github, config: dict, *, now: datetime, mode: str) -> list[dict]:
    """Fetch owner repos in one visibility partition. Limits are explicit, never silent."""
    owner = config["owner"]
    if mode == "public":
        repos = gh.get_user(owner).get_repos(type="public")
        want_private = False
    elif mode == "private-local":
        # Authenticated user listing, never GitHub public search.
        identity = gh.get_user()
        if identity.login.lower() != owner.lower():
            raise RuntimeError("la identidad autenticada no es la propietaria de los proyectos")
        repos = identity.get_repos(affiliation="owner")
        want_private = True
    else:
        raise ValueError("modo de descubrimiento desconocido")
    maximum = config["max_repositories"]
    items = []
    # Extra item prevents silently truncating the inventory.
    all_repos = list(islice(repos, maximum + 1))
    if len(all_repos) > maximum:
        raise RuntimeError(f"el inventario supera el límite {maximum}; revisar configuración")
    since = now - timedelta(days=config["lookback_days"])
    for repo in all_repos:
        if repo.full_name.split("/", 1)[0].lower() != owner.lower():
            continue
        # Partition before reading ANY commit details.
        if bool(repo.private) != want_private:
            continue
        if repo.archived:
            items.append({"name": repo.full_name,
                          "visibility": "private" if want_private else "public",
                          "archived": True, "commits": []})
            continue
        commits = []
        iterator = repo.get_commits(since=since, until=now)
        sampled = list(islice(iterator, config["max_commits_per_repo"] + 1))
        capped = len(sampled) > config["max_commits_per_repo"]
        for change in sampled[:config["max_commits_per_repo"]]:
            commit = change.commit
            time = getattr(getattr(commit, "committer", None), "date", None)
            if time is None:
                time = getattr(getattr(commit, "author", None), "date", None)
            commits.append({
                "sha": change.sha,
                "date": to_iso(time),
                "message": commit.message.splitlines()[0][:300],
            })
        items.append({
            "name": repo.full_name, "visibility": "private" if want_private else "public",
            "archived": False, "capped": capped, "commits": commits,
        })
    return items


def ensure_safe_output(path: Path, mode: str) -> Path:
    target = path.expanduser().resolve(strict=False)
    checkout = ROOT.resolve()
    if mode == "public":
        if not target.is_relative_to((checkout / "out").resolve()):
            raise ValueError("informe público debe quedar en out/ exclusivamente")
        if target != PUBLIC_OUT.resolve():
            raise ValueError("ruta pública distinta a la permitida")
        target.parent.mkdir(parents=True, exist_ok=True)
    elif mode == "private-local":
        if os.environ.get("CI") or os.environ.get("GITHUB_ACTIONS"):
            raise RuntimeError("modo privado prohibido en CI/GitHub Actions")
        if not target.is_relative_to(PRIVATE_DIR.resolve(strict=False)) or target != PRIVATE_OUT.resolve(strict=False):
            raise ValueError("informe privado debe quedar fuera del repositorio, en carpeta restringida")
        if PRIVATE_DIR.is_symlink() or target.is_symlink():
            raise ValueError("ruta privada simbólica prohibida")
        PRIVATE_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
        PRIVATE_DIR.chmod(0o700)
    else:
        raise ValueError("modo inválido")
    if target.is_symlink():
        raise ValueError("destino simbólico prohibido")
    return target


def write_report(result: dict, target: Path, mode: str) -> None:
    output = ensure_safe_output(target, mode)
    items = [x for section in ("ranked", "other_active", "watchlist")
             for x in result.get(section, [])]
    if mode == "public" and (result.get("visibility") != "public" or any(
            p.get("visibility") != "public" for p in items)):
        raise ValueError("datos privados bloqueados en publicación pública")
    if mode == "private-local" and (result.get("visibility") != "private-local" or any(
            p.get("visibility") != "private" for p in items)):
        raise ValueError("datos públicos o mezclados en salida privada")
    fd, tmp = tempfile.mkstemp(prefix=".selector-", suffix=".tmp", dir=output.parent)
    try:
        os.chmod(tmp, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fp:
            json.dump(result, fp, ensure_ascii=False, indent=2)
            fp.write("\n")
        os.replace(tmp, output)
        if mode == "private-local":
            os.chmod(output, 0o600)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def run(*, mode: str = "public", now: datetime | None = None,
        inventory: list[dict] | None = None, output: Path | None = None) -> dict:
    if mode == "private-local" and (os.environ.get("CI") or os.environ.get("GITHUB_ACTIONS")):
        raise RuntimeError("nunca consultar repos privados desde el workflow")
    config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    configured_projects(config)
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("fecha sin zona horaria")
    destination = ensure_safe_output(output or (PUBLIC_OUT if mode == "public" else PRIVATE_OUT), mode)
    if inventory is None:
        with Github(auth=Auth.Token(credentials()), per_page=100) as gh:
            inventory = discover(gh, config, now=now, mode=mode)
    result = build_selection(inventory, config, now=now, visibility=mode)
    write_report(result, destination, mode)
    # Private report locations and candidate names are not logged/uploaded.
    LOG.info("%s: inventario de %d repositorios, %d candidatos; sin publicar ni tocar state",
             mode, result["coverage"]["eligible_repos"], len(result["ranked"]))
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["public", "private-local"], default="public")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    result = run(mode=args.mode)
    if args.mode == "public":
        print("Vista previa pública (no sustitución del portfolio):")
        for i, item in enumerate(result["ranked"], 1):
            print(f"{i:2}. {item['title']} | score={item['score']:.2f} "
                  f"feat/fix 7d={item['counts']['code_7d']} "
                  f"test 7d={item['counts']['tests_7d']} "
                  f"PSM ignorados={item['counts']['psm_30d']}")
    else:
        print("Informe privado actualizado exclusivamente en el equipo autorizado (sin datos en stdout).")


if __name__ == "__main__":
    main()
