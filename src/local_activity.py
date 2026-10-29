"""Read-only audit of explicitly allowlisted local Git repositories.

Does not fetch, stage, reset, commit or mutate files. Never integrates local
metadata into a public report or prints private paths/branch names.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import tempfile

import yaml

try:
    from src.select_projects import PRIVATE_DIR
except ModuleNotFoundError:
    from select_projects import PRIVATE_DIR

CONFIG = PRIVATE_DIR / "local-repositories.yml"
OUTPUT = PRIVATE_DIR / "local-worktrees.json"


def ensure_private_file(path: Path, *, must_exist: bool = True) -> None:
    if path.is_symlink():
        raise ValueError("archivo privado simbólico")
    if must_exist and not path.is_file():
        raise ValueError("falta configuración privada local")
    if must_exist and (path.stat().st_mode & 0o077):
        raise ValueError("permisos inseguros del archivo privado")


def command(repo: Path, *args: str, timeout: int = 12) -> str:
    env = dict(os.environ, GIT_OPTIONAL_LOCKS="0", GIT_TERMINAL_PROMPT="0")
    result = subprocess.run(
        ["git", "-C", str(repo), *args], env=env,
        capture_output=True, text=True, timeout=timeout, check=False)
    if result.returncode != 0:
        raise RuntimeError("consulta git local no disponible")
    return result.stdout.strip()


def audit_one(path: Path, *, allowed_root: Path,
              verify_remote: bool = False) -> dict:
    # Explicit paths only; never a recursive scan.
    if path.is_symlink() or not path.is_dir():
        return {"state": "unavailable"}
    real = path.resolve(strict=True)
    if not real.is_relative_to(allowed_root.resolve(strict=True)):
        raise ValueError("repositorio local fuera del directorio autorizado")
    try:
        top = Path(command(real, "rev-parse", "--show-toplevel")).resolve()
        if top != real:
            raise ValueError("path no es raíz real de un repositorio Git")
        head = command(real, "rev-parse", "HEAD")
        branch = command(real, "symbolic-ref", "--quiet", "--short", "HEAD")
        last = command(real, "log", "-1", "--format=%cI")
        status = command(real, "status", "--porcelain=v1", "--untracked-files=no", timeout=25)
    except (RuntimeError, subprocess.TimeoutExpired):
        return {"state": "git_inaccessible"}
    tracked_changes = sum(1 for line in status.splitlines() if line)
    try:
        upstream = command(real, "rev-parse", "--abbrev-ref",
                           "--symbolic-full-name", "@{upstream}")
        ahead_behind = command(real, "rev-list", "--left-right", "--count",
                               "@{upstream}...HEAD")
        behind, ahead = (int(x) for x in ahead_behind.split())
        tracked = True
    except (RuntimeError, ValueError, subprocess.TimeoutExpired):
        upstream, behind, ahead, tracked = None, None, None, False
    remote_check = "not_checked"
    ahead_verified = None
    if verify_remote:
        if not tracked or "/" not in upstream:
            remote_check = "no_upstream"
        else:
            remote_name, branch_name = upstream.split("/", 1)
            try:
                env = dict(os.environ, GIT_OPTIONAL_LOCKS="0", GIT_TERMINAL_PROMPT="0")
                result = subprocess.run(
                    ["git", "-C", str(real), "ls-remote", remote_name,
                     "refs/heads/" + branch_name],
                    env=env, capture_output=True, text=True, timeout=18, check=False)
                fetched = result.stdout.split()[0] if result.returncode == 0 and result.stdout.strip() else None
                if not fetched:
                    remote_check = "remote_inaccessible"
                elif fetched == head:
                    remote_check = "head_matches_remote"
                    ahead_verified = 0
                elif fetched == command(real, "rev-parse", upstream):
                    remote_check = "tracking_ref_matches_remote"
                    ahead_verified = ahead
                else:
                    remote_check = "tracking_ref_stale_or_diverged"
            except (RuntimeError, subprocess.TimeoutExpired):
                remote_check = "remote_inaccessible"
    return {
        "state": "inspected", "head": head, "branch": branch,
        "last_commit_date": last, "tracked_changes": tracked_changes,
        "has_upstream": tracked, "ahead_of_tracking_ref": ahead,
        "behind_tracking_ref": behind,
        "remote_check": remote_check,
        "ahead_of_remote_verified": ahead_verified,
        "upstream_tracking_ref_may_be_stale": remote_check not in {
            "tracking_ref_matches_remote", "head_matches_remote"},
        "untracked_files_not_counted": True,
        "unpublished_changes_not_proof_of_feature": True,
    }


def audit(config_path: Path = CONFIG, output: Path = OUTPUT,
          root: Path = Path.home(), verify_remote: bool = False) -> dict:
    if os.environ.get("CI") or os.environ.get("GITHUB_ACTIONS"):
        raise RuntimeError("auditoría local privada prohibida en CI")
    ensure_private_file(config_path)
    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("version") != 1:
        raise ValueError("configuración de worktrees inválida")
    paths = data.get("repositories")
    if not isinstance(paths, list) or not paths or len(paths) > 25:
        raise ValueError("lista de rutas autorizadas inválida")
    if output.resolve() != OUTPUT.resolve() or output.is_symlink():
        raise ValueError("salida local no autorizada")
    records = {}
    for i, value in enumerate(paths):
        if not isinstance(value, str) or not value.startswith("/"):
            raise ValueError("ruta local no absoluta")
        path = Path(value)
        if value in records:
            raise ValueError("ruta local duplicada")
        # The report is private and path identities never leave the local file.
        records[value] = audit_one(path, allowed_root=root, verify_remote=verify_remote)
    report = {
        "schema": 1, "visibility": "private-local",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "remote_network_calls": verify_remote, "mutated_git_or_worktrees": False,
        "tracking_refs_not_refreshed": True,
        "repositories": records,
    }
    if output.parent.resolve() != PRIVATE_DIR.resolve() or PRIVATE_DIR.is_symlink():
        raise ValueError("directorio privado no autorizado")
    PRIVATE_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    PRIVATE_DIR.chmod(0o700)
    fd, temp = tempfile.mkstemp(prefix=".local-audit-", dir=PRIVATE_DIR)
    try:
        os.chmod(temp, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fp:
            json.dump(report, fp, ensure_ascii=False, indent=2)
        os.replace(temp, output)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)
    return report


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-remotes", action="store_true",
                        help="Consultar refs remotas (solo git ls-remote, nunca fetch)")
    args = parser.parse_args()
    report = audit(verify_remote=args.verify_remotes)
    print(f"Revisión local privada: {len(report['repositories'])} worktrees consultados; "
          "ninguna operación de escritura Git; resultados solo en carpeta restringida.")
