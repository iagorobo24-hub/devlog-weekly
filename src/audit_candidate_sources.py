"""Check that public candidate citations exist at their exact immutable commit.

File presence is a structural fact, NOT proof that the quoted statement,
any integration, or any application feature works. No private repos are read.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
from urllib.parse import urlparse

from github import Auth, Github
from github.GithubException import GithubException

from src.candidate_profiles import REPORT as DRAFT_REPORT
from src.portfolio_data import ROOT
from src.project_selection_core import NAME_RE, SHA_RE
from src.select_projects import credentials

QUALITY_REPORT = ROOT / "out/project-quality-public.json"
OUTPUT = ROOT / "out/candidate-source-audit-public.json"


def _parse_source(source: dict, repo: str, revision: str) -> tuple[str, str]:
    """Fail closed on a foreign URL, unpinned ref, or path type mismatch."""
    if not isinstance(source, dict) or source.get("evidence_kind") not in {
            "documented", "repository_file", "repository_directory", "ci_at_head"}:
        raise ValueError("Invalid public source kind")
    uri = urlparse(source.get("url", ""))
    kind = source["evidence_kind"]
    link_type = "tree" if kind == "repository_directory" else "blob"
    prefix = f"/{repo}/{link_type}/{revision}/"
    if (uri.scheme != "https" or uri.netloc != "github.com"
            or uri.username or uri.password or uri.query or uri.fragment
            or not uri.path.startswith(prefix)):
        raise ValueError("Foreign or unpinned public source")
    path = uri.path[len(prefix):]
    from src.candidate_profiles import PATH_RE
    if not PATH_RE.fullmatch(path) or any(part in (".", "..") for part in path.split("/")):
        raise ValueError("Unsafe source path")
    return path, "dir" if link_type == "tree" else "file"


def _get_public_repo(client, name: str):
    """Visibility is checked BEFORE inspecting repository contents."""
    repo = client.get_repo(name)
    if repo.private is not False:
        raise ValueError("Private repository rejected before source lookup")
    return repo


def build(drafts: dict, quality: dict, client, *, now: datetime) -> dict:
    if now.tzinfo is None:
        raise ValueError("Timezone-aware audit timestamp required")
    if any(x.get("schema") != 1 or x.get("visibility") != "public"
           for x in (drafts, quality)):
        raise ValueError("Only versioned PUBLIC reports accepted")
    if drafts.get("automatic_publication") is not False:
        raise ValueError("Unsafe editorial publication flag")
    quality_rows = {}
    for q in quality.get("records", []):
        if not isinstance(q, dict) or q.get("visibility") != "public":
            raise ValueError("Private quality record rejected")
        repo = q.get("repo")
        if not isinstance(repo, str) or not NAME_RE.fullmatch(repo) or repo in quality_rows:
            raise ValueError("Invalid or duplicate quality record")
        quality_rows[repo] = q
    probes = []
    seen = set()
    for draft in drafts.get("drafts", []):
        if (not isinstance(draft, dict) or draft.get("visibility") != "public"
                or draft.get("draft_only") is not True
                or draft.get("publication_allowed") is not False):
            raise ValueError("Private or promoted candidate rejected")
        name, revision = draft.get("repo"), draft.get("revision")
        if (not isinstance(name, str) or not NAME_RE.fullmatch(name)
                or not isinstance(revision, str) or not SHA_RE.fullmatch(revision)
                or name in seen):
            raise ValueError("Invalid or duplicate public candidate")
        seen.add(name)
        sources = draft.get("sources")
        if not isinstance(sources, list) or not sources or len(sources) > 20:
            raise ValueError("Unbounded or empty source list")
        paths = [_parse_source(source, name, revision) for source in sources]
        quality_head = quality_rows.get(name, {}).get("head")
        stale = quality_head != revision
        remote = None
        unavailable = False
        if not stale:
            try:
                remote = _get_public_repo(client, name)
            except GithubException as exc:
                if exc.status in (401, 403, 404, 429, 500, 502, 503, 504):
                    unavailable = True
                else:
                    raise
        citations = []
        cached_status = {}
        for source, (path, expected_type) in zip(sources, paths):
            url = source["url"]
            if url in cached_status:
                status = cached_status[url]
            elif stale:
                status = "revision_outdated"
            elif unavailable:
                status = "unavailable"
            else:
                try:
                    content = remote.get_contents(path, ref=revision)
                    observed = "dir" if isinstance(content, list) else content.type
                    status = "present" if observed == expected_type else "type_mismatch"
                except GithubException as exc:
                    if exc.status == 404:
                        status = "missing"
                    elif exc.status in (401, 403, 429, 500, 502, 503, 504):
                        status = "unavailable"
                    else:
                        raise
            cached_status[url] = status
            citations.append({
                "url": url, "evidence_kind": source["evidence_kind"],
                "status": status,
                "proves_runtime_functionality": False,
                "statement_semantically_verified": False,
            })
        ci = quality_rows.get(name, {}).get("ci", {})
        ci_url = ci.get("run_url") if isinstance(ci, dict) else None
        ci_prefix = f"https://github.com/{name}/actions/runs/"
        if (stale or not isinstance(ci, dict) or ci.get("status") != "success_at_head"
                or not isinstance(ci_url, str) or not ci_url.startswith(ci_prefix)
                or not ci_url[len(ci_prefix):].isdigit()):
            ci_url = None
        probes.append({
            "repo": name, "revision": revision, "visibility": "public",
            "quality_head_matches_revision": not stale,
            "all_sources_exist_at_pinned_revision": bool(not stale and citations and all(
                c["status"] == "present" for c in citations)),
            "ci_run_url_at_head": ci_url,
            "sources": citations,
        })
    return {
        "schema": 1, "visibility": "public",
        "generated_at": now.astimezone(timezone.utc).isoformat(),
        "source_selection_generated_at": quality.get("source_selection_generated_at"),
        "source_quality_generated_at": quality.get("generated_at"),
        "automatic_publication": False, "no_private_data": True,
        "not_functionality_validation": True,
        "probes": probes,
    }


def run(*, client=None) -> dict:
    quality = json.loads(QUALITY_REPORT.read_text(encoding="utf-8"))
    drafts = json.loads(DRAFT_REPORT.read_text(encoding="utf-8"))
    if client is None:
        with Github(auth=Auth.Token(credentials()), per_page=100) as gh:
            report = build(drafts, quality, gh, now=datetime.now(timezone.utc))
    else:
        report = build(drafts, quality, client, now=datetime.now(timezone.utc))
    if OUTPUT.is_symlink() or OUTPUT.parent.resolve() != (ROOT / "out").resolve():
        raise ValueError("Public audit output path rejected")
    fd, temp = tempfile.mkstemp(prefix=".candidate-sources-", dir=OUTPUT.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as writer:
            json.dump(report, writer, ensure_ascii=False, indent=2)
            writer.write("\n")
        os.replace(temp, OUTPUT)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)
    return report


if __name__ == "__main__":
    result = run()
    for item in result["probes"]:
        counts = {}
        for source in item["sources"]:
            counts[source["status"]] = counts.get(source["status"], 0) + 1
        print(item["repo"], counts, "run_url_at_head", bool(item["ci_run_url_at_head"]))
    print("Auditoría estructural pública, no validación funcional; sin publicación.")
