"""Pure and auditable scoring for GitHub project activity, without AI.

An activity candidate is NOT a verified success or automatically promoted to
the portfolio. No private repository metadata is accepted in public mode.
"""
from __future__ import annotations

import math
import re
from datetime import datetime, timedelta, timezone

OWNER_RE = re.compile(r"^[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,38})$")
NAME_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
SHA_RE = re.compile(r"^[0-9a-fA-F]{40}$")
PSM_RE = re.compile(
    r"(?:\bpsm\b|project[-_ ]system[-_ ]map|manifest\s+draft|"
    r"manifiesto\s+draft|refresh\s+.*audit\s+hash)", re.I
)
MAINTENANCE_RE = re.compile(r"^(?:docs|chore|ci|build|style)(?:\([^)]+\))?[!: ]", re.I)
FEATURE_RE = re.compile(r"^(?:feat|fix|perf|refactor)(?:\([^)]+\))?[!: ]", re.I)
TEST_RE = re.compile(r"^(?:test|tests)(?:\([^)]+\))?[!: ]", re.I)


def commit_date(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        return None
    return dt.astimezone(timezone.utc)


def categorize(message: object) -> str:
    subject = str(message or "").splitlines()[0].strip()
    if PSM_RE.search(subject):
        return "psm_noise"
    if TEST_RE.match(subject):
        return "test"
    if FEATURE_RE.match(subject):
        return "code"
    if MAINTENANCE_RE.match(subject):
        return "maintenance"
    # Unknown conventional-commit style => review, never imply validated change.
    return "other"


def configured_projects(config: dict) -> list[dict]:
    if not isinstance(config, dict) or config.get("version") != 1:
        raise ValueError("selector: versión de configuración no reconocida")
    owner = config.get("owner")
    if not isinstance(owner, str) or not OWNER_RE.fullmatch(owner):
        raise ValueError("selector: propietario inválido")
    for key, low, high in (("recent_days", 1, 30), ("lookback_days", 7, 90),
                           ("max_commits_per_repo", 20, 300),
                           ("max_repositories", 1, 200), ("top_n", 1, 30)):
        value = config.get(key)
        if type(value) is not int or not low <= value <= high:
            raise ValueError(f"selector: {key} fuera de rango")
    if config["recent_days"] > config["lookback_days"]:
        raise ValueError("selector: ventana reciente excede el histórico")
    projects = config.get("projects", [])
    if not isinstance(projects, list):
        raise ValueError("selector: projects debe ser lista")
    ids, repo_names = set(), set()
    for item in projects:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            raise ValueError("selector: project id inválido")
        pid = item["id"]
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,63}", pid) or pid in ids:
            raise ValueError(f"selector: ID duplicado o inválido {pid}")
        ids.add(pid)
        if not isinstance(item.get("title"), str) or not 2 <= len(item["title"]) <= 100:
            raise ValueError("selector: título inválido")
        if type(item.get("spotlight", True)) is not bool:
            raise ValueError("selector: spotlight debe ser booleano")
        importance = item.get("priority")
        if type(importance) is not int or not 0 <= importance <= 5:
            raise ValueError("selector: prioridad debe estar entre 0 y 5")
        names = item.get("repos")
        if not isinstance(names, list) or not names:
            raise ValueError("selector: proyecto sin repos")
        for name in names:
            if not isinstance(name, str) or not NAME_RE.fullmatch(name):
                raise ValueError("selector: nombre de repo inválido")
            if not name.startswith(owner + "/") or name in repo_names:
                raise ValueError("selector: repos cruzados, duplicados o externos al propietario")
            repo_names.add(name)
    return projects


def evaluate_repo(repo: dict, *, now: datetime, recent_days: int = 7,
                  lookback_days: int = 30) -> dict:
    """Scores facts, not self-reported successful deployments."""
    if now.tzinfo is None:
        raise ValueError("now debe incluir zona horaria")
    cutoff = now.astimezone(timezone.utc) - timedelta(days=lookback_days)
    recent = now.astimezone(timezone.utc) - timedelta(days=recent_days)
    summary = {k: 0 for k in ("code_7d", "code_30d", "tests_7d", "tests_30d",
                              "docs_30d", "psm_30d", "other_30d")}
    seen = set()
    first_evidence = None
    for c in repo.get("commits", []):
        if not isinstance(c, dict):
            continue
        sha = c.get("sha")
        dt = commit_date(c.get("date"))
        if not isinstance(sha, str) or not SHA_RE.fullmatch(sha) or sha in seen:
            continue
        if dt is None or dt < cutoff or dt > now.astimezone(timezone.utc):
            continue
        seen.add(sha)
        kind = categorize(c.get("message"))
        if kind == "code":
            summary["code_30d"] += 1
            if dt >= recent:
                summary["code_7d"] += 1
        elif kind == "test":
            summary["tests_30d"] += 1
            if dt >= recent:
                summary["tests_7d"] += 1
        elif kind == "maintenance":
            summary["docs_30d"] += 1
        elif kind == "psm_noise":
            summary["psm_30d"] += 1
        else:
            summary["other_30d"] += 1
        if kind in {"code", "test"} and first_evidence is None:
            first_evidence = {"sha": sha.lower(), "date": dt.isoformat()}
    # Logarithmic: avoid 100 trivial commits crowding out smaller but meaningful work.
    score = (
        6 * math.log2(1 + summary["code_7d"] + summary["tests_7d"])
        + 3.5 * math.log2(1 + summary["code_30d"] + summary["tests_30d"])
        + 2 * math.log2(1 + summary["tests_30d"])
    )
    return {"counts": summary, "activity_score": round(score, 2),
            "latest_substantive": first_evidence,
            "capped": bool(repo.get("capped", False))}


def build_selection(inventory: list[dict], config: dict, *, now: datetime,
                    visibility: str = "public") -> dict:
    """Rank projects from an explicit visibility partition, never intermix both."""
    cfg = configured_projects(config)
    if visibility not in {"public", "private-local"}:
        raise ValueError("selector: modo de visibilidad desconocido")
    owner = config["owner"]
    if type(inventory) is not list:
        raise ValueError("selector: inventario inválido")
    allowed_visibility = "private" if visibility == "private-local" else "public"
    seen = set()
    repo_scores = {}
    excluded = {"other_visibility": 0, "archived": 0, "foreign_owner": 0, "invalid": 0}
    for repo in inventory:
        if not isinstance(repo, dict) or not isinstance(repo.get("name"), str) or not NAME_RE.fullmatch(repo["name"]):
            excluded["invalid"] += 1
            continue
        name = repo["name"]
        if name in seen:
            raise ValueError(f"selector: repositorio duplicado {name}")
        seen.add(name)
        if not name.startswith(owner + "/"):
            excluded["foreign_owner"] += 1
            continue
        if repo.get("visibility") != allowed_visibility:
            excluded["other_visibility"] += 1
            continue
        if repo.get("archived") is True:
            excluded["archived"] += 1
            continue
        repo_scores[name] = evaluate_repo(repo, now=now,
                                          recent_days=config["recent_days"],
                                          lookback_days=config["lookback_days"])
    # Non-curated repos are also discovered. Never assume they are important
    # just because the repo name suggests that they are.
    groups = []
    mapped = set()
    if visibility == "public":
        for p in cfg:
            overlap = [r for r in p["repos"] if r in repo_scores]
            if not overlap:
                continue
            mapped.update(overlap)
            groups.append({"id": p["id"], "title": p["title"],
                           "repos": overlap, "priority": p["priority"],
                           "curated": True, "spotlight": p.get("spotlight", True)})
    # Private mode cannot consume the public projects list (a separate partition).
    for name in sorted(repo_scores):
        if name not in mapped:
            groups.append({"id": name.split("/", 1)[1], "title": name.split("/", 1)[1],
                           "repos": [name], "priority": 1, "curated": False,
                           "spotlight": True})
    ranked = []
    for group in groups:
        metrics = [repo_scores[name] for name in group["repos"]]
        total = {k: sum(m["counts"][k] for m in metrics)
                 for k in metrics[0]["counts"]}
        activity = sum(m["activity_score"] for m in metrics)
        # Importance is an explicit editorial signal, secondary to demonstrable activity.
        priority_points = group["priority"] * 4
        score = round(min(85, activity) + priority_points, 2)
        evidence = next(({"repo": name, **repo_scores[name]["latest_substantive"]}
                         for name in group["repos"]
                         if repo_scores[name]["latest_substantive"]), None)
        active = (total["code_7d"] + total["tests_7d"]) > 0
        ranked.append({
            "id": group["id"], "title": group["title"], "repos": group["repos"],
            "visibility": allowed_visibility, "curated": group["curated"],
            "priority": group["priority"], "score": score,
            "activity_score": round(activity, 2), "priority_score": priority_points,
            "active_7d": active, "active_30d": (total["code_30d"] + total["tests_30d"]) > 0,
            "spotlight": group["spotlight"], "counts": total, "evidence": evidence,
            "capped": any(m["capped"] for m in metrics),
            "editorial_status": "candidate_needs_review",
            "reasons": [
                f"{total['code_7d']} commits de código y {total['tests_7d']} de tests (7 días)",
                f"{total['psm_30d']} commits PSM descartados (30 días)",
                f"prioridad editorial declarada: {group['priority']}/5",
            ],
        })
    ranked.sort(key=lambda p: (-int(p["active_7d"]), -p["score"], p["id"].lower()))
    suitable = [p for p in ranked if p["spotlight"] and p["active_30d"]]
    watchlist = [dict(p, watch_reason=("internal_infrastructure" if not p["spotlight"]
                                      else "no_substantive_activity_30d"))
                 for p in ranked if not p["spotlight"] or not p["active_30d"]]
    return {
        "schema": 1, "visibility": visibility, "generated_at": now.astimezone(timezone.utc).isoformat(),
        "recent_days": config["recent_days"], "lookback_days": config["lookback_days"],
        "coverage": {"eligible_repos": len(repo_scores), "input_repos": len(inventory),
                     "exclusions": excluded},
        "limits": {"per_repo_cap": config["max_commits_per_repo"],
                   "ranking_is_not_proof_of_functionality": True,
                   "may_omit_local_unpushed_changes": True},
        "ranked": suitable[:config["top_n"]],
        "other_active": [{"id": p["id"], "score": p["score"],
                          "active_7d": p["active_7d"], "counts": p["counts"], "visibility": allowed_visibility}
                         for p in suitable[config["top_n"]:]],
        "watchlist": watchlist,
    }
