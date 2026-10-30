"""Create a matched synthetic collection/summary pair for the CI-only preview.

This is a visual fixture, never real collected activity or publishable evidence.
All URLs, dates and headlines come from the committed synthetic sample.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


def prepare(fixture: Path, output: Path) -> tuple[Path, Path]:
    if fixture.is_symlink() or not fixture.is_file():
        raise ValueError("falta la muestra visual segura")
    sample = json.loads(fixture.read_text(encoding="utf-8"))
    if (not isinstance(sample, dict)
            or not isinstance(sample.get("generated_at"), str)
            or not isinstance(sample.get("repos"), list)
            or not sample["repos"]):
        raise ValueError("muestra visual inválida")
    repositories = []
    seen = set()
    for record in sample["repos"]:
        if not isinstance(record, dict):
            raise ValueError("repositorio de demostración inválido")
        name = record.get("name")
        since, until = record.get("since"), record.get("until")
        if (not isinstance(name, str) or not name or name in seen
                or not all(isinstance(s, str) and s for s in (since, until))):
            raise ValueError("intervalos de demostración inválidos")
        seen.add(name)
        repositories.append({
            "name": name, "since": since, "until": until,
            "fixture_only": True, "commits": [], "prs_closed": [],
            "issues_closed": [], "tags_all": [], "tags_new": [],
        })
    source = {
        "generated_at": sample["generated_at"],
        "github_run_id": None,
        "fixture_only": True,
        "repos": repositories,
    }
    source_bytes = (json.dumps(source, sort_keys=True, ensure_ascii=False,
                               indent=2) + "\n").encode("utf-8")
    summary = dict(sample)
    summary["github_run_id"] = None
    summary["source_collected_sha256"] = hashlib.sha256(source_bytes).hexdigest()
    if output.is_symlink():
        raise ValueError("directorio de salida inseguro")
    output.mkdir(parents=True, exist_ok=True)
    collected_path = output / "collected.json"
    summary_path = output / "summaries.json"
    if collected_path.is_symlink() or summary_path.is_symlink():
        raise ValueError("artefacto de vista previa inseguro")
    collected_path.write_bytes(source_bytes)
    summary_path.write_text(
        json.dumps(summary, sort_keys=True, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return collected_path, summary_path


if __name__ == "__main__":
    from src.deck_provenance import verify_collected_source
    root = Path(__file__).resolve().parent.parent
    collected, summary = prepare(root / "tests/fixtures/weekly_sample.json",
                                 root / "out")
    verify_collected_source(collected, summary)
    print("Muestra visual sintética con procedencia interna verificada")
