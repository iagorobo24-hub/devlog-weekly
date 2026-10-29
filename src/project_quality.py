"""Conservative, public-only repo quality evidence for selection review.

CI evidence is tied to default-branch HEAD and checked separately from
existence of tests and workflow files. No inference of E2E functionality.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from itertools import islice
import re
from urllib.parse import quote

from github import Auth, Github
from github.GithubException import GithubException

try:
    from src.project_selection_core import NAME_RE, SHA_RE, commit_date
except ModuleNotFoundError:
    from project_selection_core import NAME_RE, SHA_RE, commit_date

TEST_NAMES = {"test", "tests", "__tests__", "spec", "specs", "e2e", "integration"}
WORKFLOW_PREFIX = ".github/workflows/"
DOC_NAMES = {"readme.md", "readme.rst", "readme", "readme.txt"}
MAX_RUNS = 25
MAX_REPOS = 100


def assess_head_ci(*, head: str, branch: str, runs: list[dict],
                   now: datetime, max_age_days: int = 30) -> dict:
    """Only completed push runs for EXACT default-branch HEAD count."""
    if not isinstance(head, str) or not SHA_RE.fullmatch(head):
        raise ValueError("head SHA inválido")
    if not isinstance(branch, str) or not branch:
        raise ValueError("rama predeterminada inválida")
    filtered = []
    for run in runs:
        if (run.get("head_sha") != head or run.get("head_branch") != branch
                or run.get("event") != "push"):
            continue
        stamp = commit_date(run.get("created_at"))
        if stamp is None or stamp > now or stamp < now - timedelta(days=max_age_days):
            continue
        filtered.append((stamp, run))
    if not filtered:
        return {"status": "unknown", "run_count_at_head": 0,
                "reason": "no_recent_push_ci_at_default_head", "run_url": None}
    filtered.sort(key=lambda x: (x[0], x[1].get("id", 0)), reverse=True)
    latest = filtered[0][1]
    conclusions = [x[1].get("conclusion") for x in filtered]
    if any(x in (None, "") for x in conclusions):
        status = "pending"
    elif any(x not in {"success", "skipped", "neutral"} for x in conclusions):
        status = "failure_or_cancelled"
    elif "success" in conclusions:
        status = "success_at_head"
    else:
        status = "inconclusive"
    url = latest.get("url")
    if not isinstance(url, str) or not url.startswith("https://github.com/"):
        url = None
    return {
        "status": status, "run_count_at_head": len(filtered),
        "reason": "default_branch_push_runs_only",
        "run_url": url,
    }


def evaluate_quality(facts: dict, now: datetime,
                     expected_visibility: str = "public") -> dict:
    if expected_visibility not in {"public", "private"} or facts.get("visibility") != expected_visibility:
        raise ValueError("quality visibility partition mismatch")
    repo = facts.get("repo")
    head = facts.get("head")
    if not isinstance(repo, str) or not NAME_RE.fullmatch(repo):
        raise ValueError("invalid repo")
    if not isinstance(head, str) or not SHA_RE.fullmatch(head):
        raise ValueError("invalid head")
    default = facts.get("default_branch")
    ci = assess_head_ci(head=head, branch=default, runs=facts.get("runs", []),
                        now=now)
    readme = facts.get("readme", False) is True
    test_paths = facts.get("test_paths", False) is True
    workflows = facts.get("workflows", False) is True
    score = ((5 if readme else 0)
             + (5 if test_paths else 0)
             + (5 if workflows else 0)
             + (15 if ci["status"] == "success_at_head" else 0))
    if ci["status"] == "failure_or_cancelled":
        readiness = "ci_failure_needs_review"
    elif ci["status"] == "success_at_head" and test_paths:
        readiness = "ci_head_passed_tests_exist"
    elif ci["status"] == "success_at_head":
        readiness = "ci_head_passed_tests_not_located"
    else:
        readiness = "insufficient_current_ci_evidence"
    return {
        "repo": repo, "visibility": expected_visibility,
        "default_branch": default, "head": head,
        "head_evidence_link": f"https://github.com/{repo}/tree/{head}",
        "readme_present": readme,
        "test_path_present": test_paths,
        "workflow_present": workflows,
        "ci": ci,
        "evidence_score": score,
        "readiness": readiness,
        "not_product_validation": True,
        "tests_present_do_not_prove_passing": True,
        "future_changes_require_recheck": True,
    }


def _repo_facts(gh: Github, name: str, *, expected_private: bool) -> dict:
    """Verify visibility before any repo content, commit, or workflow read."""
    if not NAME_RE.fullmatch(name):
        raise ValueError("invalid repository identifier")
    r = gh.get_repo(name)
    if bool(r.private) != expected_private:
        raise ValueError("private repo blocked before content/API reads"
                         if not expected_private else "nonprivate repo rejected")
    if r.archived:
        raise ValueError("archived repo excluded")
    branch = r.default_branch
    head = r.get_branch(branch).commit.sha
    # Read root only; avoids inspecting full source files or private archives.
    root = r.get_contents("", ref=head)
    paths = [c.path.lower() for c in root] if isinstance(root, list) else []
    readme = any(p in DOC_NAMES for p in paths)
    test_paths = any(p in TEST_NAMES or p.startswith("test_") for p in paths)
    # Shallow bounded discovery: tests frequently live under tools/tests,
    # backend/tests or src/tests. Only names are read, never file contents.
    if not test_paths:
        containers = {"src", "tools", "30-tools", "backend", "frontend",
                      "scripts", "app", "packages"}
        dirs = [c.path for c in root if c.type == "dir"
                and c.name.lower() in containers][:8]
        for directory in dirs:
            children = r.get_contents(directory, ref=head)
            if isinstance(children, list) and any(
                    c.type == "dir" and (c.name.lower() in TEST_NAMES
                                         or c.name.lower().startswith("test_"))
                    for c in children):
                test_paths = True
                break
    # A workflow existing does not prove it ran successfully.
    workflows = False
    try:
        w = r.get_contents(".github/workflows", ref=head)
        workflows = isinstance(w, list) and any(
            x.name.lower().endswith((".yml", ".yaml")) for x in w)
    except GithubException as exc:
        if exc.status != 404:
            raise
    runs = []
    for run in list(islice(r.get_workflow_runs(event="push", branch=branch, head_sha=head), MAX_RUNS)):
        url = getattr(run, "html_url", None)
        if not isinstance(url, str) or not url.startswith("https://github.com/"):
            url = None
        runs.append({
            "id": run.id,
            "head_sha": run.head_sha,
            "head_branch": run.head_branch,
            "event": run.event,
            "created_at": run.created_at.isoformat() if run.created_at else None,
            "conclusion": run.conclusion,
            "url": url,
        })
    return {
        "repo": name, "visibility": "private" if expected_private else "public",
        "default_branch": branch, "head": head, "readme": readme, "test_paths": test_paths,
        "workflows": workflows, "runs": runs,
    }


def repo_facts(gh: Github, name: str) -> dict:
    """Public probe never reads a private repo's code, CI or commits."""
    return _repo_facts(gh, name, expected_private=False)


def private_repo_facts(gh: Github, name: str) -> dict:
    """Private probe; caller must enforce local-only execution and persistence."""
    return _repo_facts(gh, name, expected_private=True)


def public_quality_report(gh: Github, selection: dict, *,
                          now: datetime) -> dict:
    if selection.get("visibility") != "public" or selection.get("schema") != 1:
        raise ValueError("only public selection accepted")
    sections = [selection.get(k, []) for k in ("ranked", "other_active")]
    if any(not isinstance(rows, list) for rows in sections) or sum(map(len, sections)) > MAX_REPOS:
        raise ValueError("selection count out of bounds")
    seen = set()
    records = []
    for candidate in (p for rows in sections for p in rows):
        if not isinstance(candidate, dict) or candidate.get("visibility") != "public":
            raise ValueError("private candidate blocked")
        names = candidate.get("repos")
        if not isinstance(names, list) or not names:
            raise ValueError("candidate without full repository identity")
        for name in names:
            if not isinstance(name, str) or not NAME_RE.fullmatch(name):
                raise ValueError("invalid candidate repository")
            if name in seen:
                continue
            seen.add(name)
            # API failures must be visible, not converted into 'passed'.
            try:
                records.append(evaluate_quality(repo_facts(gh, name), now))
            except GithubException as exc:
                records.append({"repo": name, "visibility": "public",
                                "readiness": "probe_unavailable", "reason": f"github_http_{exc.status}",
                                "evidence_score": 0, "not_product_validation": True})
    return {
        "schema": 1, "visibility": "public", "generated_at": now.isoformat(),
        "source_selection_generated_at": selection.get("generated_at"),
        "no_private_data": True, "not_product_validation": True,
        "records": records,
    }
