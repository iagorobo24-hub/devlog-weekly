"""Private quality evidence on Penguin only, never on a CI runner.

Metadata-only GitHub checks; stores only aggregate quality evidence in a
private 0600 file and never prints repo names or any private URL.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile

from github import Auth, Github
from github.GithubException import GithubException

try:
    from src.select_projects import PRIVATE_DIR, PRIVATE_OUT, credentials
    from src.project_quality import private_repo_facts, evaluate_quality
except ModuleNotFoundError:
    from select_projects import PRIVATE_DIR, PRIVATE_OUT, credentials
    from project_quality import private_repo_facts, evaluate_quality

OUTPUT = PRIVATE_DIR / "project-quality-private.json"
MAX_CANDIDATES = 100


def from_selection(selection: dict, gh, now: datetime) -> dict:
    if selection.get("visibility") != "private-local":
        raise ValueError("no importar selección pública")
    sections = [selection.get(k, []) for k in ("ranked", "other_active")]
    if (any(not isinstance(rows, list) for rows in sections)
            or sum(map(len, sections)) > MAX_CANDIDATES):
        raise ValueError("número de candidatos privados inválido")
    candidates = [p for rows in sections for p in rows]
    if any(not isinstance(p, dict) or p.get("visibility") != "private"
           for p in candidates):
        raise ValueError("contaminación del ranking privado")
    names = []
    for item in candidates:
        if item.get("visibility") != "private":
            raise ValueError("contaminación del ranking privado")
        for name in item.get("repos", []):
            if not isinstance(name, str) or "/" not in name:
                raise ValueError("repo privado inválido")
            if name not in names:
                names.append(name)
    records = []
    for name in names:
        try:
            records.append(evaluate_quality(private_repo_facts(gh, name), now,
                                            expected_visibility="private"))
        except GithubException as exc:
            records.append({"repo":name,"visibility":"private",
                            "readiness":"probe_unavailable","error_status":exc.status,
                            "evidence_score":0,"not_product_validation":True})
    return {"schema":1,"visibility":"private-local",
            "generated_at":now.isoformat(),"automatic_publication":False,
            "only_repository_metadata":True,"records":records}


def run(now: datetime | None = None, github_client=None, selection=None,
        *, output: Path = OUTPUT) -> dict:
    if os.environ.get("CI") or os.environ.get("GITHUB_ACTIONS"):
        raise RuntimeError("calidad privada prohibida en CI")
    if not PRIVATE_DIR.is_dir() or PRIVATE_DIR.is_symlink():
        raise ValueError("directorio privado no autorizado")
    if selection is None:
        if PRIVATE_OUT.is_symlink() or PRIVATE_OUT.stat().st_mode & 0o077:
            raise ValueError("ranking privado con permisos inseguros")
        selection = json.loads(PRIVATE_OUT.read_text(encoding="utf-8"))
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("fecha sin zona horaria")
    if github_client is None:
        with Github(auth=Auth.Token(credentials()), per_page=100) as gh:
            result=from_selection(selection,gh,now)
    else:
        result=from_selection(selection,github_client,now)
    if output.resolve() != OUTPUT.resolve() or output.is_symlink():
        raise ValueError("destino privado no autorizado")
    fd,tmp=tempfile.mkstemp(prefix=".quality-private-",dir=PRIVATE_DIR)
    try:
        os.chmod(tmp,0o600)
        with os.fdopen(fd,"w",encoding="utf-8") as f:
            json.dump(result,f,ensure_ascii=False,indent=2)
        os.replace(tmp,output)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return result


if __name__=="__main__":
    result=run()
    print(f"Calidad privada evaluada para {len(result['records'])} candidatos; "
          "datos exclusivamente en Penguin.")
