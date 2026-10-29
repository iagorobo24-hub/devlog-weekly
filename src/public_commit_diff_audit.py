"""Read-only, bounded proof of changed file *categories* in sampled public commits.

Commit subjects and filename categories never establish that functionality works
or that tests were run. Only a sample from the pinned public branch scan is read.
No filenames, file contents, diffs, or private repository data are persisted.
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

from src.project_selection_core import NAME_RE, SHA_RE, commit_date
from src.select_projects import ROOT, credentials

BRANCHES = ROOT / "out/project-branch-activity-public.json"
OUTPUT = ROOT / "out/project-commit-diff-audit-public.json"
MAX_SAMPLES = 5
MAX_FILES = 100
RETRIABLE = (401, 403, 404, 409, 422, 429, 500, 502, 503, 504)
CODE_SUFFIXES = (".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".kt",
                 ".kts", ".go", ".rs", ".c", ".h", ".cpp", ".hpp",
                 ".cs", ".swift", ".scala", ".vue", ".svelte", ".php",
                 ".rb", ".sh", ".sql")
TEST_PARTS = {"test", "tests", "__tests__", "spec", "specs",
              "integration-tests", "e2e", "qa"}


def classify_path(path: str) -> str:
    """Only coarse categories; never output filenames from audited commits."""
    if not isinstance(path, str) or not path:
        return "other"
    clean = path.replace("\\", "/").lower()
    parts = clean.split("/")
    name = parts[-1]
    if (any(part in TEST_PARTS for part in parts[:-1])
            or name.startswith("test_") or name.endswith(("_test.py", ".test.ts",
              ".spec.ts", ".test.tsx", ".spec.tsx", ".test.js", ".spec.js",
              ".test.jsx", ".spec.jsx", "test.java", "tests.java"))):
        return "tests"
    if (name.endswith(CODE_SUFFIXES) or
            name in ("dockerfile", "makefile")):
        return "code"
    if (any(part in ("docs", "documentation") for part in parts[:-1])
            or name.endswith((".md", ".rst", ".txt", ".adoc", ".pdf"))):
        return "docs"
    return "other"


def read_diff(repo, sha: str, declared_kind: str, *,
              max_files: int = MAX_FILES) -> dict:
    if (not isinstance(sha, str) or not SHA_RE.fullmatch(sha)
            or declared_kind not in ("code", "test")
            or type(max_files) is not int or not 1 <= max_files <= MAX_FILES):
        raise ValueError("Invalid pinned SHA, declaration, or bounds")
    try:
        c = repo.get_commit(sha)
        if c.sha.lower() != sha.lower():
            return {"status": "commit_sha_mismatch", "scan_complete": False,
                    "counts": None, "declared_kind": declared_kind,
                    "matching_declared_kind": False,
                    "filename_categories_only": True,
                    "not_test_execution_or_functional_validation": True}
        filenames = list(islice(c.files, max_files + 1))
        truncated = len(filenames) > max_files
        counts = {key: 0 for key in ("code", "tests", "docs", "other")}
        for file in filenames[:max_files]:
            kind = classify_path(getattr(file, "filename", None))
            counts[kind] += 1
        if truncated:
            status = "incomplete_file_list"
        elif not filenames:
            status = "no_changed_files"
        elif counts["code"] or counts["tests"]:
            status = "code_or_test_files_present"
        else:
            status = "only_docs_or_other_paths"
        return {
            "status": status, "scan_complete": not truncated,
            "counts": counts, "declared_kind": declared_kind,
            "matching_declared_kind": (counts["tests"] > 0 if declared_kind == "test"
                                       else counts["code"] > 0),
            "filename_categories_only": True,
            "not_test_execution_or_functional_validation": True,
        }
    except GithubException as exc:
        if exc.status not in RETRIABLE:
            raise
        return {
            "status": "unavailable", "scan_complete": False,
            "counts": None, "declared_kind": declared_kind,
            "matching_declared_kind": False,
            "filename_categories_only": True,
            "not_test_execution_or_functional_validation": True,
        }


def build(branch_report: dict, gh, *, now: datetime) -> dict:
    if now.tzinfo is None:
        raise ValueError("Timezone-aware time required")
    if (not isinstance(branch_report, dict) or branch_report.get("schema") != 1
            or branch_report.get("visibility") != "public"
            or branch_report.get("private_inputs_accessed") is not False
            or branch_report.get("automatic_publication") is not False
            or branch_report.get("feature_work_is_not_main_or_ci_evidence") is not True):
        raise ValueError("Only safe public branch input permitted")
    observed = commit_date(branch_report.get("generated_at"))
    if observed is None or not timedelta(0) <= now - observed <= timedelta(hours=36):
        raise ValueError("Stale or future branch report")
    probes = branch_report.get("repos")
    if not isinstance(probes, list) or len(probes) > 100:
        raise ValueError("Unbounded public candidate list")
    repos = []
    seen_repos = set()
    for entry in probes:
        if (not isinstance(entry, dict) or entry.get("visibility") != "public"
                or entry.get("not_merged_or_runtime_verified") is not True):
            raise ValueError("Private or invalid branch entry")
        name = entry.get("repo")
        if (not isinstance(name, str) or not NAME_RE.fullmatch(name)
                or name in seen_repos):
            raise ValueError("Invalid or duplicate public repository")
        seen_repos.add(name)
        samples = entry.get("sample_recent_substantive_commits", [])
        if not isinstance(samples, list) or len(samples) > MAX_SAMPLES:
            raise ValueError("Unbounded evidence sample")
        seen_sha = set()
        for item in samples:
            sha = item.get("sha") if isinstance(item, dict) else None
            if (not isinstance(sha, str) or not SHA_RE.fullmatch(sha)
                    or sha in seen_sha
                    or item.get("kind") not in ("code", "test")
                    or item.get("url") != f"https://github.com/{name}/commit/{sha}"
                    or item.get("commit_subject_only") is not True
                    or item.get("not_merged_or_functionally_verified") is not True):
                raise ValueError("Unsafe or mismatched public commit sample")
            seen_sha.add(sha)
        entries = []
        if samples:
            try:
                repo = gh.get_repo(name)
                if repo.private is not False or repo.full_name != name:
                    raise ValueError("Private repo refused before reading commit files")
            except GithubException as exc:
                if exc.status not in RETRIABLE:
                    raise
                repo = None
            for item in samples:
                if repo is None:
                    observation = {"status": "unavailable", "scan_complete": False,
                                   "counts": None, "declared_kind": item["kind"],
                                   "matching_declared_kind": False,
                                   "filename_categories_only": True,
                                   "not_test_execution_or_functional_validation": True}
                else:
                    observation = read_diff(repo, item["sha"], item["kind"])
                entries.append({
                    "sha": item["sha"], "url": item["url"],
                    "visibility": "public", **observation,
                })
        repos.append({"repo": name, "visibility": "public",
                      "sampled": len(entries), "audited": entries,
                      "does_not_prove_feature_or_test_pass": True})
    return {
        "schema": 1, "visibility": "public",
        "source_selection_generated_at": branch_report.get("source_selection_generated_at"),
        "source_branch_generated_at": branch_report.get("generated_at"),
        "generated_at": now.astimezone(timezone.utc).isoformat(),
        "automatic_publication": False, "private_inputs_accessed": False,
        "only_file_category_evidence": True,
        "not_functional_or_test_execution_validation": True,
        "limits": {"samples_per_repo": MAX_SAMPLES, "files_per_commit": MAX_FILES},
        "repos": repos,
    }


def run() -> dict:
    report = json.loads(BRANCHES.read_text(encoding="utf-8"))
    with Github(auth=Auth.Token(credentials()), per_page=100) as gh:
        result = build(report, gh, now=datetime.now(timezone.utc))
    if OUTPUT.is_symlink() or OUTPUT.parent.resolve() != (ROOT / "out").resolve():
        raise ValueError("Unsafe public audit destination")
    fd, temp = tempfile.mkstemp(prefix=".commit-diff-public-", dir=OUTPUT.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as writer:
            json.dump(result, writer, indent=2, ensure_ascii=False)
            writer.write("\n")
        os.replace(temp, OUTPUT)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)
    return result


if __name__ == "__main__":
    result = run()
    for item in result["repos"]:
        if item["audited"]:
            print(item["repo"], "sampled", item["sampled"],
                  "diff_statuses", [x["status"] for x in item["audited"]])
    print("Solo categorías de archivos públicos. No se valida funcionamiento ni tests.")
