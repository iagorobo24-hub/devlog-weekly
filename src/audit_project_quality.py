"""Generate a quality-evidence assessment for PUBLIC candidates only.

Inputs and outputs live under out/; no private data, no modification of
editorial profiles, portfolio.pdf, Drive or state/.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import logging
from pathlib import Path

from github import Auth, Github

try:
    from src.select_projects import ROOT, credentials
    from src.project_quality import public_quality_report
except ModuleNotFoundError:
    from select_projects import ROOT, credentials
    from project_quality import public_quality_report

INPUT = ROOT / "out" / "project-selection-public.json"
OUTPUT = ROOT / "out" / "project-quality-public.json"
LOG = logging.getLogger("project-quality")


def run(*, now: datetime | None = None, selector: dict | None = None,
        github_client=None) -> dict:
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("zona horaria obligatoria")
    data = selector if selector is not None else json.loads(INPUT.read_text(encoding="utf-8"))
    generated = data.get("generated_at")
    try:
        stamp = datetime.fromisoformat(generated.replace("Z", "+00:00"))
    except (ValueError, AttributeError) as exc:
        raise ValueError("selección sin fecha verificable") from exc
    if stamp.tzinfo is None or not timedelta(0) <= now - stamp <= timedelta(hours=36):
        raise ValueError("selección pública obsoleta: regenerar antes de evaluar")
    if github_client is None:
        with Github(auth=Auth.Token(credentials()), per_page=100) as gh:
            result = public_quality_report(gh, data, now=now)
    else:
        result = public_quality_report(github_client, data, now=now)
    # write_report is for project selection; same public-only confinement,
    # but quality uses a distinct fixed destination.
    if OUTPUT.is_symlink() or OUTPUT.parent.resolve() != (ROOT / "out").resolve():
        raise ValueError("salida de calidad no autorizada")
    if result.get("visibility") != "public" or any(
            item.get("visibility") != "public" for item in result.get("records", [])):
        raise ValueError("no escribir datos privados en informe público")
    import os
    import tempfile
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=".quality-", dir=OUTPUT.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fp:
            json.dump(result, fp, ensure_ascii=False, indent=2)
            fp.write("\n")
        os.replace(temp, OUTPUT)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)
    return result


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    result = run()
    print("Evaluación pública, solo evidencias CI y estructura documental:")
    for item in result["records"]:
        print(item["repo"], item["readiness"], "CI:",item.get("ci", {}).get("status", "unknown"))
