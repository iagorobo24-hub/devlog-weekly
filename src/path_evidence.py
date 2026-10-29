"""Bounded, private-only inspection of files changed by scoped commits.

A matching path corroborates that a scope points at a code area; it does not
prove tests passed, nor that a product works. Shared paths cannot establish an
exclusive component attribution. Do not include filenames in the output.
"""
from __future__ import annotations

from collections import defaultdict
import re
from typing import Callable

try:
    from src.component_selection import SCOPE_RE, validate_mapping
    from src.project_selection_core import categorize, SHA_RE
except ModuleNotFoundError:
    from component_selection import SCOPE_RE, validate_mapping
    from project_selection_core import categorize, SHA_RE

PREFIX_RE = re.compile(r"^[a-zA-Z0-9_.-]+(?:/[a-zA-Z0-9_.-]+)*/$")


def valid_prefix(prefix: object) -> bool:
    return isinstance(prefix, str) and bool(PREFIX_RE.fullmatch(prefix)) and not any(
        segment in {".", ".."} for segment in prefix.split("/") if segment
    )


def verify_paths(inventory: list[dict], mapping: dict, *, owner: str,
                 fetch_files: Callable[[str, str], list[str]],
                 sample_per_component: int = 5) -> list[dict]:
    """Read only bounded commit metadata for configured private repos."""
    rules = validate_mapping(mapping, owner=owner)
    if not 1 <= sample_per_component <= 8:
        raise ValueError("muestreo fuera de límites")
    repo_index = {r["name"]: r for r in inventory if r.get("visibility") == "private"
                  and not r.get("archived", False)}
    result = []
    for rule in rules:
        repo = rule["repo"]
        if repo not in repo_index:
            raise ValueError("monorepo privado no encontrado")
        prefixes = {}
        scopes = {}
        for component in rule["components"]:
            cid = component["id"]
            paths = component.get("paths")
            if not isinstance(paths, list) or not paths or not all(valid_prefix(p) for p in paths):
                raise ValueError("mapping privado sin paths seguros para " + cid)
            prefixes[cid] = paths
            for scope in component["scopes"]:
                scopes[scope] = cid

        examples = defaultdict(list)
        for commit in repo_index[repo].get("commits", []):
            if not isinstance(commit, dict):
                continue
            sha = commit.get("sha")
            if not isinstance(sha, str) or not SHA_RE.fullmatch(sha):
                continue
            if categorize(commit.get("message")) not in {"code", "test"}:
                continue
            subject = str(commit.get("message", "")).splitlines()[0]
            match = SCOPE_RE.match(subject)
            cid = scopes.get(match.group(1).lower()) if match else None
            if cid is not None and len(examples[cid]) < sample_per_component:
                examples[cid].append(sha.lower())

        findings = []
        for component in rule["components"]:
            cid = component["id"]
            counts = {"exclusive": 0, "shared": 0, "mixed": 0,
                      "no_path_match": 0, "fetch_error": 0}
            for sha in examples[cid]:
                try:
                    filenames = fetch_files(repo, sha)
                except Exception:
                    counts["fetch_error"] += 1
                    continue
                if not isinstance(filenames, list) or not filenames or not all(
                        isinstance(f, str) and f for f in filenames):
                    counts["fetch_error"] += 1
                    continue
                claimed = any(f.startswith(pre) for f in filenames for pre in prefixes[cid])
                if not claimed:
                    counts["no_path_match"] += 1
                    continue
                overlapping = any(
                    other != cid and any(f.startswith(pre) for f in filenames for pre in other_paths)
                    for other, other_paths in prefixes.items()
                )
                if overlapping:
                    counts["shared"] += 1
                elif any(not any(f.startswith(pre) for pre in prefixes[cid]) for f in filenames):
                    counts["mixed"] += 1
                else:
                    counts["exclusive"] += 1
            findings.append({
                "id": cid, "sampled": len(examples[cid]), "results": counts,
                "scope_path_status": ("shared_paths_not_exclusive"
                                      if counts["shared"] else
                                      "sampled_paths_only_not_certified"),
                "verified_functionality": False,
            })
        result.append({
            "visibility": "private", "repo": repo,
            "status": "bounded_file_path_audit",
            "limit_per_component": sample_per_component,
            "partial": bool(repo_index[repo].get("capped")),
            "components": findings,
        })
    return result
