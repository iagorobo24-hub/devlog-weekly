"""Bounded, public-only audit of commits ahead of default branches.

This report supplements default-branch selection, never validates CI or runtime.
GitHub comparison excludes commits already reachable from the default head.
Shared commits in two feature branches are deduplicated by full SHA.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from itertools import islice
import json
import os
from pathlib import Path
import tempfile

from github import Auth, Github
from github.GithubException import GithubException

from src.project_selection_core import NAME_RE, SHA_RE, commit_date, categorize
from src.select_projects import ROOT, credentials, to_iso

SOURCE = ROOT / "out/project-selection-public.json"
OUTPUT = ROOT / "out/project-branch-activity-public.json"
MAX_REPOS = 100
MAX_BRANCHES = 20
MAX_AHEAD_COMMITS = 120
LOOKBACK_DAYS = 30
RECENT_DAYS = 7


def _names(selection: dict, owner: str) -> list[str]:
    if selection.get("schema") != 1 or selection.get("visibility") != "public":
        raise ValueError("Public-only branch auditor")
    names = []
    for bucket in ("ranked", "other_active", "watchlist"):
        rows = selection.get(bucket, [])
        if not isinstance(rows, list):
            raise ValueError("Invalid candidate bucket")
        for row in rows:
            if not isinstance(row, dict) or row.get("visibility") != "public":
                raise ValueError("Private branch audit input rejected")
            repos = row.get("repos")
            if not isinstance(repos, list) or not repos:
                raise ValueError("Candidate lacks repository identity")
            for name in repos:
                if (not isinstance(name, str) or not NAME_RE.fullmatch(name)
                        or not name.lower().startswith(owner.lower() + "/")
                        or name in names):
                    raise ValueError("Duplicate or foreign branch candidate")
                names.append(name)
    if len(names) > MAX_REPOS:
        raise ValueError("Too many candidate repositories")
    return names


def probe(gh, name: str, *, now: datetime, recent_days: int,
          lookback_days: int, branch_limit: int = MAX_BRANCHES,
          commit_limit: int = MAX_AHEAD_COMMITS) -> dict:
    if now.tzinfo is None:
        raise ValueError("Date must have a timezone")
    repo = gh.get_repo(name)
    # The privacy check precedes branch enumeration or commit inspection.
    if repo.private is not False or repo.full_name != name:
        raise ValueError("Private/foreign repository blocked before branch content")
    branch = repo.default_branch
    default_head = repo.get_branch(branch).commit.sha
    if not SHA_RE.fullmatch(default_head):
        raise ValueError("Invalid default branch head")
    all_branches = list(islice(repo.get_branches(), branch_limit + 1))
    incomplete = len(all_branches) > branch_limit
    checked = 0
    errors = 0
    seen: set[str] = set()
    commits = []
    observed_ahead = 0
    branch_evidence = []
    for item in all_branches[:branch_limit]:
        if item.name == branch:
            continue
        checked += 1
        try:
            comparison = repo.compare(branch, item.name)
            ahead = comparison.ahead_by
            if not isinstance(ahead, int) or ahead < 0:
                raise ValueError("Invalid comparison ahead_by")
            if not ahead:
                continue
            observed_ahead += ahead  # Not a unique count across branches.
            sampled = list(islice(comparison.commits, commit_limit + 1))
            if len(sampled) > commit_limit or ahead > len(sampled):
                incomplete = True
            for c in sampled[:commit_limit]:
                sha = c.sha
                if not isinstance(sha, str) or not SHA_RE.fullmatch(sha) or sha in seen:
                    continue
                seen.add(sha)
                date = to_iso(getattr(getattr(c.commit, "committer", None), "date", None)
                              or getattr(getattr(c.commit, "author", None), "date", None))
                when = commit_date(date)
                if when is None or not now - timedelta(days=lookback_days) <= when <= now:
                    continue
                commits.append({"sha": sha.lower(), "date": date,
                                "message": c.commit.message.splitlines()[0][:300]})
            head = getattr(getattr(item, "commit", None), "sha", None)
            if (isinstance(head, str) and SHA_RE.fullmatch(head)
                    and isinstance(item.name, str) and 1 <= len(item.name) <= 200):
                branch_evidence.append({
                    "branch": item.name, "tip": head.lower(), "ahead_by": ahead,
                    "ahead_is_not_unique_across_branches": True,
                })
        except GithubException as exc:
            if exc.status not in (401, 403, 404, 409, 422, 429, 500, 502, 503, 504):
                raise
            errors += 1
            incomplete = True
    counts = {k: 0 for k in ("code_7d", "code_30d", "tests_7d", "tests_30d",
                             "psm_30d", "docs_30d", "other_30d")}
    recent = now - timedelta(days=recent_days)
    for c in commits:
        kind = categorize(c["message"])
        when = commit_date(c["date"])
        assert when is not None
        if kind == "code":
            counts["code_30d"] += 1
            if when >= recent:
                counts["code_7d"] += 1
        elif kind == "test":
            counts["tests_30d"] += 1
            if when >= recent:
                counts["tests_7d"] += 1
        elif kind == "psm_noise":
            counts["psm_30d"] += 1
        elif kind == "maintenance":
            counts["docs_30d"] += 1
        else:
            counts["other_30d"] += 1
    branches_sorted = sorted(branch_evidence, key=lambda v: (-v["ahead_by"], v["branch"]))
    return {
        "repo": name, "visibility": "public", "default_branch": branch,
        "default_head_at_scan": default_head.lower(),
        "branch_scanned": checked, "comparison_errors": errors,
        "scan_complete": not incomplete,
        "counts_unique_ahead_of_default": counts,
        "observed_unique_sha_count_in_window": len(commits),
        "observed_ahead_sum_not_unique": observed_ahead,
        "sample_branches": branches_sorted[:5],
        "commit_count_is_lower_bound_if_scan_incomplete": True,
        "separate_from_default_head_ci": True,
        "not_merged_or_runtime_verified": True,
    }


def build(selection: dict, gh, *, now: datetime,
          owner: str = "iagorobo24-hub") -> dict:
    if now.tzinfo is None:
        raise ValueError("Date without timezone")
    stamp = commit_date(selection.get("generated_at"))
    if stamp is None or not timedelta(0) <= now - stamp <= timedelta(hours=36):
        raise ValueError("Selection stale or undated; rerun discovery")
    names = _names(selection, owner)
    recent_days = selection.get("recent_days", RECENT_DAYS)
    lookback_days = selection.get("lookback_days", LOOKBACK_DAYS)
    if not all(type(v) is int for v in (recent_days, lookback_days)):
        raise ValueError("Invalid date windows")
    if not 1 <= recent_days <= lookback_days <= 90:
        raise ValueError("Date windows out of range")
    probes = []
    for name in names:
        try:
            probes.append(probe(gh, name, now=now, recent_days=recent_days,
                                lookback_days=lookback_days))
        except GithubException as exc:
            if exc.status not in (401, 403, 404, 429, 500, 502, 503, 504):
                raise
            probes.append({
                "repo": name, "visibility": "public",
                "status": "unavailable", "scan_complete": False,
                "separate_from_default_head_ci": True,
                "not_merged_or_runtime_verified": True,
                "counts_unique_ahead_of_default": None,
            })
    return {
        "schema": 1, "visibility": "public",
        "source_selection_generated_at": selection["generated_at"],
        "generated_at": now.astimezone(timezone.utc).isoformat(),
        "default_branch_counts_unchanged": True,
        "feature_work_is_not_main_or_ci_evidence": True,
        "private_inputs_accessed": False, "automatic_publication": False,
        "limits": {"branches_per_repo": MAX_BRANCHES,
                   "compare_commits_per_branch": MAX_AHEAD_COMMITS},
        "repos": probes,
    }


def run() -> dict:
    from src.project_selection_core import configured_projects
    import yaml
    config = yaml.safe_load((ROOT / "config/project-selection.yml").read_text())
    configured_projects(config)
    selection = json.loads(SOURCE.read_text(encoding="utf-8"))
    with Github(auth=Auth.Token(credentials()), per_page=100) as client:
        result = build(selection, client, now=datetime.now(timezone.utc),
                       owner=config["owner"])
    if OUTPUT.is_symlink() or OUTPUT.parent.resolve() != (ROOT / "out").resolve():
        raise ValueError("Public branch output destination rejected")
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=".branch-public-", dir=OUTPUT.parent)
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
    report = run()
    for item in report["repos"]:
        counts = item.get("counts_unique_ahead_of_default") or {}
        print(item["repo"], "unmerged_code_7d", counts.get("code_7d", "?"),
              "unmerged_tests_7d", counts.get("tests_7d", "?"),
              "coverage_complete", item["scan_complete"])
    print("Auditoría separada de ramas públicas; sin atribución a main ni publicación.")
