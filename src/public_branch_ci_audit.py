"""Public CI runs associated with immutable, unmerged branch tip SHAs.

Checks only up to five selected branch tips per public repo with recent
unmerged code/test commits. No CI result can promote default-branch readiness.
All evidence is run-level only; no claim of runtime or workflow coverage.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import os
import tempfile
from itertools import islice

from github import Auth, Github
from github.GithubException import GithubException

from src.project_selection_core import NAME_RE, SHA_RE, commit_date
from src.select_projects import ROOT, credentials

SOURCE = ROOT / "out/project-branch-activity-public.json"
OUTPUT = ROOT / "out/project-branch-ci-public.json"
MAX_BRANCH_TIPS = 5
MAX_RUNS_PER_TIP = 20
RETRIABLE = {401, 403, 404, 409, 422, 429, 500, 502, 503, 504}
OUTCOMES = {"completed", "success", "failure", "cancelled", "timed_out", "action_required",
            "neutral", "skipped", "stale", "startup_failure", "pending",
            "in_progress", "queued", "requested", "waiting", "unknown"}


def inspect_runs(repo, sha: str, *, limit: int = MAX_RUNS_PER_TIP) -> dict:
    if not isinstance(sha, str) or not SHA_RE.fullmatch(sha) or not 1 <= limit <= MAX_RUNS_PER_TIP:
        raise ValueError("Invalid pinned CI SHA or limits")
    try:
        run_list = list(islice(repo.get_workflow_runs(head_sha=sha), limit + 1))
    except GithubException as exc:
        if exc.status not in RETRIABLE:
            raise
        return {"status": "unavailable", "scan_complete": False,
                "workflow_runs": [], "observed_workflow_count": 0,
                "all_returned_runs_succeeded": False}
    truncated = len(run_list) > limit
    rows = []
    seen = set()
    for run in run_list[:limit]:
        if (str(run.head_sha).lower() != sha.lower() or
                not isinstance(run.id, int) or run.id in seen):
            raise ValueError("Workflow run from another SHA or duplicate")
        seen.add(run.id)
        conclusion = run.conclusion if run.conclusion else None
        progress = run.status
        if conclusion and conclusion not in OUTCOMES:
            conclusion = "unknown"
        if progress not in OUTCOMES:
            progress = "unknown"
        rows.append({
            "run_id": run.id, "name": str(run.name or "")[:120],
            "event": str(run.event or "")[:60],
            "status": progress, "conclusion": conclusion,
            "url": f"https://github.com/{repo.full_name}/actions/runs/{run.id}",
            "head_sha": sha.lower(),
            "not_runtime_evidence": True,
        })
    has_failures = any(row["conclusion"] in
                       ("failure", "cancelled", "timed_out", "action_required",
                        "startup_failure") for row in rows)
    all_passed = bool(rows) and all(
        row["status"] == "completed" and row["conclusion"] == "success"
        for row in rows)
    if has_failures:
        state = "observed_failure_or_cancelled"
    elif truncated:
        state = "incomplete"
    elif all_passed:
        state = "all_observed_runs_successful"
    elif rows:
        state = "pending_or_inconclusive"
    else:
        state = "no_runs_found"
    return {
        "status": state, "scan_complete": not truncated,
        "workflow_runs": rows,
        "observed_workflow_count": len(rows),
        "all_returned_runs_succeeded": all_passed and not truncated,
        "workflow_coverage_not_proven": True,
    }


def build(branches: dict, gh, *, now: datetime) -> dict:
    if now.tzinfo is None:
        raise ValueError("Timezone-aware now required")
    if (not isinstance(branches, dict) or branches.get("schema") != 1
            or branches.get("visibility") != "public"
            or branches.get("automatic_publication") is not False
            or branches.get("private_inputs_accessed") is not False
            or branches.get("feature_work_is_not_main_or_ci_evidence") is not True):
        raise ValueError("Private or unsafe public branch report")
    stamp = commit_date(branches.get("generated_at"))
    if stamp is None or not timedelta(0) <= now - stamp <= timedelta(hours=36):
        raise ValueError("Stale branch scan")
    repos = branches.get("repos")
    if not isinstance(repos, list) or len(repos) > 100:
        raise ValueError("Unbounded branch repository list")
    output = []
    observed_names = set()
    for item in repos:
        if (not isinstance(item, dict) or item.get("visibility") != "public"
                or item.get("not_merged_or_runtime_verified") is not True):
            raise ValueError("Private branch record")
        name = item.get("repo")
        if not isinstance(name, str) or not NAME_RE.fullmatch(name) or name in observed_names:
            raise ValueError("Invalid duplicate public repository")
        observed_names.add(name)
        counts = item.get("counts_unique_ahead_of_default")
        active = (isinstance(counts, dict) and
                  type(counts.get("code_7d")) is int and
                  type(counts.get("tests_7d")) is int and
                  counts["code_7d"] + counts["tests_7d"] > 0)
        selected = item.get("sample_branches", [])
        if not isinstance(selected, list) or len(selected) > MAX_BRANCH_TIPS:
            raise ValueError("Unbounded branch tips")
        seen_tips = set()
        for row in selected:
            tip = row.get("tip") if isinstance(row, dict) else None
            if (not isinstance(tip, str) or not SHA_RE.fullmatch(tip)
                    or tip in seen_tips
                    or not isinstance(row.get("branch"), str)
                    or not 1 <= len(row["branch"]) <= 200):
                raise ValueError("Invalid or duplicate branch tip")
            seen_tips.add(tip)
        checks = []
        if active and selected:
            try:
                repo = gh.get_repo(name)
                if repo.private is not False or repo.full_name != name:
                    raise ValueError("Private repository refused before CI lookup")
            except GithubException as exc:
                if exc.status not in RETRIABLE:
                    raise
                repo = None
            for row in selected:
                result = (inspect_runs(repo, row["tip"]) if repo is not None
                          else {"status": "unavailable", "scan_complete": False,
                                "workflow_runs": [], "observed_workflow_count": 0,
                                "all_returned_runs_succeeded": False,
                                "workflow_coverage_not_proven": True})
                checks.append({
                    "branch": row["branch"], "tip_sha": row["tip"],
                    "visibility": "public", **result,
                })
        output.append({
            "repo": name, "visibility": "public",
            "branch_tips_checked": len(checks),
            "branches": checks,
            "no_promotion_of_main_ci_or_runtime": True,
        })
    return {
        "schema": 1, "visibility": "public",
        "source_selection_generated_at": branches.get("source_selection_generated_at"),
        "source_branch_generated_at": branches["generated_at"],
        "generated_at": now.astimezone(timezone.utc).isoformat(),
        "automatic_publication": False,
        "private_inputs_accessed": False,
        "does_not_verify_all_workflows_or_runtime": True,
        "max_branch_tips": MAX_BRANCH_TIPS,
        "max_runs_per_tip": MAX_RUNS_PER_TIP,
        "repos": output,
    }


def run() -> dict:
    data = json.loads(SOURCE.read_text(encoding="utf-8"))
    with Github(auth=Auth.Token(credentials()), per_page=100) as gh:
        result = build(data, gh, now=datetime.now(timezone.utc))
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    if OUTPUT.is_symlink() or OUTPUT.parent.resolve() != (ROOT/"out").resolve():
        raise ValueError("Unsafe output location")
    fd, temp = tempfile.mkstemp(prefix=".branch-ci-public-", dir=OUTPUT.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
            f.write("\n")
        os.replace(temp, OUTPUT)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)
    return result


if __name__ == "__main__":
    for item in run()["repos"]:
        if item["branches"]:
            print(item["repo"], [(b["branch"], b["status"],
                                  b["observed_workflow_count"])
                                 for b in item["branches"]])
    print("CI de ramas por SHA; no valida main ni ejecución funcional.")
