"""Conservative monorepo attribution from explicitly mapped conventional scopes.

The mapping is private/local only. A scope match is a *hint*, never evidence
of a passing test or functioning product. Ambiguous changes stay unassigned.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import re

import yaml

try:
    from src.project_selection_core import NAME_RE, commit_date, categorize
except ModuleNotFoundError:
    from project_selection_core import NAME_RE, commit_date, categorize

SCOPE_RE = re.compile(r"^[a-z][a-z0-9-]*\(([a-z0-9][a-z0-9_.-]*)\)[!: ]", re.I)
ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,63}$")


def validate_mapping(mapping: object, *, owner: str) -> list[dict]:
    if not isinstance(mapping, dict) or mapping.get("version") != 1:
        raise ValueError("mapeo de monorepo inválido")
    rules = mapping.get("monorepos")
    if not isinstance(rules, list):
        raise ValueError("monorepos debe ser lista")
    seen_repo = set()
    for rule in rules:
        if not isinstance(rule, dict):
            raise ValueError("regla de monorepo no válida")
        repo = rule.get("repo")
        if not isinstance(repo, str) or not NAME_RE.fullmatch(repo) or not repo.startswith(owner + "/"):
            raise ValueError("monorepo ajeno al propietario")
        if repo in seen_repo:
            raise ValueError("monorepo duplicado")
        seen_repo.add(repo)
        members = rule.get("components")
        if not isinstance(members, list) or not members:
            raise ValueError("monorepo sin componentes")
        ids, used_scopes = set(), set()
        for member in members:
            if not isinstance(member, dict) or not isinstance(member.get("id"), str):
                raise ValueError("componente inválido")
            component_id = member["id"]
            if not ID_RE.fullmatch(component_id) or component_id in ids:
                raise ValueError("componente duplicado o inválido")
            ids.add(component_id)
            scopes = member.get("scopes")
            if not isinstance(scopes, list) or not scopes:
                raise ValueError("componente sin scopes")
            for scope in scopes:
                if not isinstance(scope, str) or not re.fullmatch(r"[a-z0-9][a-z0-9_.-]*", scope):
                    raise ValueError("scope no válido")
                if scope in used_scopes:
                    raise ValueError("scope duplicado entre componentes: atribución ambigua")
                used_scopes.add(scope)
    return rules


def components_from_commits(inventory: list[dict], mapping: dict, *,
                            owner: str, now: datetime, recent_days: int = 7,
                            lookback_days: int = 30) -> list[dict]:
    rules = validate_mapping(mapping, owner=owner)
    repo_index = {item["name"]: item for item in inventory
                  if item.get("visibility") == "private" and not item.get("archived")}
    result = []
    recent = now.astimezone(timezone.utc) - timedelta(days=recent_days)
    cutoff = now.astimezone(timezone.utc) - timedelta(days=lookback_days)
    for rule in rules:
        name = rule["repo"]
        source = repo_index.get(name)
        if not source:
            # A typo in the private mapping must not produce a fake active project.
            raise ValueError("monorepo configurado no accesible en inventario privado")
        lookup = {scope: member["id"]
                  for member in rule["components"] for scope in member["scopes"]}
        hits = {m["id"]: {"code_30d": 0, "test_30d": 0,
                          "code_7d": 0, "test_7d": 0, "example_sha": None}
                for m in rule["components"]}
        unassigned = 0
        seen = set()
        for commit in source.get("commits", []):
            sha = commit.get("sha")
            dt = commit_date(commit.get("date"))
            if not isinstance(sha, str) or sha in seen or dt is None or not cutoff <= dt <= now:
                continue
            seen.add(sha)
            kind = categorize(commit.get("message"))
            if kind not in {"code", "test"}:
                continue
            subject = str(commit.get("message", "")).splitlines()[0]
            scoped = SCOPE_RE.match(subject)
            scope = scoped.group(1).lower() if scoped else None
            target = lookup.get(scope)
            if target is None:
                unassigned += 1
                continue
            slot = hits[target]
            slot[f"{kind}_30d"] += 1
            if dt >= recent:
                slot[f"{kind}_7d"] += 1
            if slot["example_sha"] is None:
                slot["example_sha"] = sha
        result.append({
            "repo": name,
            "visibility": "private",
            "status": "scope_inference_requires_path_validation",
            "capped": bool(source.get("capped")),
            "unassigned_substantive_commits": unassigned,
            "components": [{"id": m["id"], "scopes": m["scopes"],
                            "observed": hits[m["id"]], "verified_by_file_diff": False}
                           for m in rule["components"]],
        })
    return result


def read_private_mapping(path: Path) -> dict | None:
    if not path.exists():
        return None
    if path.is_symlink() or (path.stat().st_mode & 0o077):
        raise ValueError("mapeo privado sin permisos exclusivos")
    return yaml.safe_load(path.read_text(encoding="utf-8"))
