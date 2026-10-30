"""Public-only live revision gate for an editorial V4 PDF preview.

Revision drift is a reason to re-audit claims, not to update or publish
editorial material. Uses read-only GitHub API; never touches repo state.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sys
from urllib import error, request

import yaml

ROOT = Path(__file__).resolve().parent.parent
SELECTION = ROOT / "content/portfolio/editorial-selection-public.yml"
OUT = ROOT / "out/editorial-live-freshness-public.json"
REPO_RE = re.compile(r"^iagorobo24-hub/[A-Za-z0-9_.-]+$")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def selected_revisions(selection: dict) -> dict[str, str]:
    if (not isinstance(selection, dict)
            or selection.get("visibility") != "public"
            or selection.get("status") != "frozen_editorial_scope_not_release_approval"
            or not isinstance(selection.get("policy"), dict)
            or selection["policy"].get("automatic_publication") is not False):
        raise ValueError("selección editorial no pública o no fijada")
    expected = {"main_cases": 3, "supporting_cases": 2, "excluded_cases": 1}
    result = {}
    for bucket, count in expected.items():
        rows = selection.get(bucket)
        if not isinstance(rows, list) or len(rows) != count:
            raise ValueError("composición editorial incompleta")
        for item in rows:
            if not isinstance(item, dict):
                raise ValueError("candidato editorial inválido")
            name, sha = item.get("repo"), item.get("revision")
            if (not isinstance(name, str) or not REPO_RE.fullmatch(name)
                    or name in result or not isinstance(sha, str)
                    or not SHA_RE.fullmatch(sha)):
                raise ValueError("repo o revisión editorial inválidos")
            result[name] = sha
    return result


def github_json(endpoint: str, token: str = "") -> dict:
    url = "https://api.github.com" + endpoint
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "devlog-editorial-revision-gate",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = "Bearer " + token
    with request.urlopen(request.Request(url, headers=headers), timeout=15) as stream:
        data = json.load(stream)
    if not isinstance(data, dict):
        raise ValueError("respuesta pública GitHub inválida")
    return data


def inspect(selection: dict, fetch=github_json, *, token: str = "") -> dict:
    candidates = selected_revisions(selection)
    rows = []
    for name, pinned in candidates.items():
        try:
            meta = fetch("/repos/" + name, token)
            if meta.get("private") is not False:
                raise ValueError("repositorio no confirmado como público")
            branch = meta.get("default_branch")
            if (not isinstance(branch, str) or not branch
                    or not re.fullmatch(r"[A-Za-z0-9_./-]{1,150}", branch)
                    or branch.startswith("/") or ".." in branch):
                raise ValueError("rama pública inválida")
            from urllib.parse import quote
            tip = fetch("/repos/" + name + "/branches/" + quote(branch, safe=""), token)
            current = tip.get("commit", {}).get("sha")
            if not isinstance(current, str) or not SHA_RE.fullmatch(current):
                raise ValueError("HEAD público inválido")
            status = "current" if current == pinned else "outdated"
        except (error.HTTPError, error.URLError, TimeoutError, OSError, KeyError,
                TypeError, ValueError) as exc:
            current, status = None, "unavailable"
        rows.append({
            "repo": name, "pinned_revision": pinned,
            "observed_head": current, "status": status,
        })
    return {
        "schema": 1, "visibility": "public",
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "automatic_publication": False,
        "revision_gate_pass": all(row["status"] == "current" for row in rows),
        "current_count": sum(row["status"] == "current" for row in rows),
        "outdated_count": sum(row["status"] == "outdated" for row in rows),
        "unavailable_count": sum(row["status"] == "unavailable" for row in rows),
        "projects": rows,
    }


def main() -> None:
    if SELECTION.is_symlink() or not SELECTION.is_file():
        raise SystemExit("Falta selección pública editorial segura")
    selection = yaml.safe_load(SELECTION.read_text(encoding="utf-8"))
    result = inspect(selection, token=os.environ.get("GITHUB_TOKEN", ""))
    if OUT.parent.resolve() != (ROOT / "out").resolve() or OUT.is_symlink():
        raise SystemExit("Directorio de informe no seguro")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"V4 revisión pública: {result['current_count']} actuales, "
          f"{result['outdated_count']} obsoletos, "
          f"{result['unavailable_count']} no verificados")
    for item in result["projects"]:
        if item["status"] != "current":
            print(f"  {item['repo']}: {item['status']} — "
                  f"fijado {item['pinned_revision'][:12]}, "
                  f"HEAD {(item['observed_head'] or 'desconocido')[:12]}")
    if not result["revision_gate_pass"]:
        raise SystemExit("V4 sin revisión editorial vigente: PDF bloqueado")
    print("V4: seis revisiones públicas actuales; aún sin aprobación para publicar")


if __name__ == "__main__":
    main()
