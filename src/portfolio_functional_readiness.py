"""Inspect exact-pinned public GitHub Actions jobs; not a runtime certificate."""
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import urllib.error
import urllib.request

from src.portfolio_data import ROOT
from src.select_projects import credentials

INPUT = ROOT / "out/portfolio-evidence-public.json"
OUTPUT = ROOT / "out/portfolio-functional-readiness-public.json"
NOTES = ROOT / "out/portfolio-functional-readiness-public.md"
REPO = re.compile(r"^iagorobo24-hub/[A-Za-z0-9_.-]+$")
SHA = re.compile(r"^[a-f0-9]{40}$")
RUN = re.compile(r"^[1-9][0-9]{0,15}$")
STATES = {"success_at_head", "failure_or_cancelled", "unknown", "pending",
          "inconclusive", "unavailable"}


def validate(source):
    if (not isinstance(source, dict) or source.get("schema") != 1
            or source.get("visibility") != "public"
            or source.get("private_sources_inspected") is not False
            or source.get("automatic_publication") is not False
            or source.get("safe_to_replace_public_portfolio") is not False
            or source.get("ci_reports_consistent") is not True
            or source.get("ci_report_disagreements") != []):
        raise ValueError("Fuente pública no reconciliada")
    cases = source.get("cases")
    if not isinstance(cases, list) or len(cases) != 5:
        raise ValueError("Inventario de cinco casos requerido")
    seen = set()
    for c in cases:
        if not isinstance(c, dict):
            raise ValueError("Caso inválido")
        repo, rev, ci = c.get("repo"), c.get("revision"), c.get("ci")
        if (not isinstance(repo, str) or not REPO.fullmatch(repo)
                or repo in seen or not isinstance(rev, str)
                or not SHA.fullmatch(rev) or c.get("visibility") != "public"
                or c.get("head_matches_revision") is not True
                or c.get("ready_for_publication") is not False
                or c.get("independent_runtime_validated") is not False
                or c.get("owner_permission_confirmed") is not False):
            raise ValueError("Proyecto privado, desfasado o promocionado")
        seen.add(repo)
        if not isinstance(ci, dict) or ci.get("status") not in STATES:
            raise ValueError("CI no fiable")
        url = ci.get("run_url")
        if url is not None:
            prefix = f"https://github.com/{repo}/actions/runs/"
            if (not isinstance(url, str) or not url.startswith(prefix)
                    or not RUN.fullmatch(url[len(prefix):])):
                raise ValueError("URL de run ajena o inválida")
    return cases


def github_jobs(repo, run_id, token):
    if not REPO.fullmatch(repo) or not RUN.fullmatch(run_id):
        raise ValueError("Destino de API no permitido")
    request = urllib.request.Request(
        f"https://api.github.com/repos/{repo}/actions/runs/{run_id}/jobs?per_page=100",
        headers={"Accept": "application/vnd.github+json",
                 "Authorization": "Bearer " + token,
                 "X-GitHub-Api-Version": "2022-11-28"})
    with urllib.request.urlopen(request, timeout=25) as response:
        content = response.read(300001)
        if response.status != 200 or len(content) > 300000:
            raise ValueError("Respuesta de CI excesiva")
    return json.loads(content)


def extract(payload):
    if not isinstance(payload, dict):
        raise ValueError("Jobs no estructurados")
    jobs = payload.get("jobs")
    if (not isinstance(jobs, list) or not 1 <= len(jobs) <= 100
            or type(payload.get("total_count")) is not int
            or payload["total_count"] != len(jobs)):
        raise ValueError("Jobs incompletos")
    observed, job_results = [], []
    for job in jobs:
        if not isinstance(job, dict) or not isinstance(job.get("steps"), list):
            raise ValueError("Job sin pasos")
        if job.get("conclusion") not in {"success", "failure", "cancelled",
                                         "skipped", "timed_out", "neutral"}:
            raise ValueError("Resultado de job desconocido")
        if len(job["steps"]) > 150:
            raise ValueError("Demasiados pasos")
        job_results.append(job["conclusion"])
        for step in job["steps"]:
            if not isinstance(step, dict):
                raise ValueError("Paso inválido")
            name, state = step.get("name"), step.get("conclusion")
            if not isinstance(name, str) or len(name) > 220 or state not in {
                    "success", "failure", "skipped", "cancelled", "neutral", None}:
                raise ValueError("Paso sin estado fiable")
            low = name.lower()
            kind = ("security" if "production dependency audit" in low
                    else "unit" if "unittest" in low or "unit tests" in low
                    else "workspace" if "workspacechecks" in low or "ci-safe workspace checks" in low
                    else "setup" if "install playwright" in low
                    else "e2e" if "end-to-end tests" in low or "playwright test" in low
                    else "build" if "production build" in low
                    else "static" if low in ("lint", "typecheck") else None)
            if kind:
                observed.append({"kind": kind, "name": name, "status": state})
    return {"job_results": job_results, "steps": observed}


def build(source, fetch, now):
    if now.tzinfo is None:
        raise ValueError("Fecha sin timezone")
    results = []
    for c in validate(source):
        url, ci = c["ci"].get("run_url"), c["ci"]["status"]
        found = {"job_results": [], "steps": []}
        inspection = "no_push_run"
        if url:
            try:
                found = extract(fetch(c["repo"], url.rsplit("/", 1)[-1]))
                inspection = "jobs_checked"
            except urllib.error.HTTPError as error:
                if error.code not in (401, 403, 404, 429, 500, 502, 503, 504):
                    raise
                inspection = "jobs_unavailable"
        jobs = found["job_results"]
        if inspection == "jobs_checked" and ci == "success_at_head":
            consistent = "success" in jobs and not any(
                s in ("failure", "cancelled", "timed_out") for s in jobs)
        elif inspection == "jobs_checked" and ci == "failure_or_cancelled":
            consistent = any(s in ("failure", "cancelled", "timed_out") for s in jobs)
        else:
            consistent = inspection != "jobs_checked"
        steps = found["steps"]
        security = [s["name"] for s in steps if s["kind"] == "security"
                    and s["status"] == "failure"]
        skipped = [s["name"] for s in steps if s["kind"] in (
            "unit", "workspace", "e2e", "build") and
            s["status"] in ("skipped", "cancelled", None)]
        passed = [s["name"] for s in steps if s["kind"] in (
            "unit", "workspace", "e2e", "build") and s["status"] == "success"]
        results.append({
            "repo": c["repo"], "revision": c["revision"],
            "ci_status": ci, "run_url": url,
            "inspection": inspection, "ci_jobs_consistent": consistent,
            "observed_steps": steps, "checks_passed": passed,
            "checks_skipped": skipped, "security_failures": security,
            "functional_runtime_verified": False, "image_use_approved": False,
            "publication_approved": False,
        })
    return {"schema": 1, "visibility": "public",
            "source_selection_generated_at": source["source_selection_generated_at"],
            "generated_at": now.isoformat(), "cases": results,
            "automatic_publication": False, "runtime_certification": False,
            "safe_to_publish": False}


def markdown(result):
    rows = [
        "# Portfolio Maestro - pruebas realmente ejecutadas (no publicar)",
        "",
        "El estado del CI no equivale a funcionamiento en TIA/PLCSIM, Minecraft ni SPA.",
        "",
        "| Caso | CI en HEAD | Checks correctos | Omitidos | Seguridad |",
        "|---|---|---:|---:|---|",
    ]
    for c in result["cases"]:
        rows.append(f"| {c['repo']} | {c['ci_status']} | "
                    f"{len(c['checks_passed'])} | {len(c['checks_skipped'])} | "
                    f"{len(c['security_failures'])} fallos |")
    for c in result["cases"]:
        rows.extend(["", "## " + c["repo"], "", "Run: " +
                     (c["run_url"] or "sin run de push comprobada"), ""])
        rows.extend("- " + s["kind"] + ": " + s["name"] + " = " +
                    str(s["status"]) for s in c["observed_steps"])
    rows.extend(["", "Ningún proyecto recibe permiso de publicación, de imágenes",
                 "ni certificación funcional mediante estas comprobaciones.", ""])
    return "\n".join(rows)


def main():
    source = json.loads(INPUT.read_text(encoding="utf-8"))
    token = credentials()
    result = build(source, lambda repo, run: github_jobs(repo, run, token),
                   datetime.now(timezone.utc))
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    for path, content in (
        (OUTPUT, json.dumps(result, ensure_ascii=False, indent=2) + "\n"),
        (NOTES, markdown(result)),
    ):
        if path.is_symlink() or path.parent.resolve() != OUTPUT.parent.resolve():
            raise ValueError("Salida no autorizada")
        path.write_text(content, encoding="utf-8")
    print("CI step audit:", len(result["cases"]), "public cases; release authorized: no")


if __name__ == "__main__":
    main()
