"""Confirm a complete, same-run weekly snapshot; never publish or call APIs.

This is the sole state commit entry point for both legacy --commit-state
commands and the weekly workflow. Validate *all* inputs before touching state.
Writes are staged and rolled back on ordinary I/O failure. Git only pushes
state after this command succeeds (a process crash mid-write is not an
atomic multi-file transaction).
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile

ROOT = Path(__file__).resolve().parent.parent
COLLECTED_PATH = ROOT / "out" / "collected.json"
SUMMARIES_PATH = ROOT / "out" / "summaries.json"
LAST_RUN_PATH = ROOT / "state" / "last_run.json"
NARRATIVE_DIR = ROOT / "state" / "narrative"
CONFIG_PATH = ROOT / "config" / "repos.yml"
REPO = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
RUN_ID = re.compile(r"^[0-9]+$")


def _utc(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError("fecha o intervalo ausente")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("fecha no ISO") from exc
    if parsed.tzinfo is None:
        raise ValueError("fecha sin zona horaria")
    return parsed.astimezone(timezone.utc)


def _read_json(path: Path) -> tuple[dict, bytes]:
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"origen ausente o inseguro: {path.name}")
    content = path.read_bytes()
    try:
        obj = json.loads(content)
    except (ValueError, UnicodeDecodeError) as exc:
        raise ValueError(f"JSON inválido: {path.name}") from exc
    if not isinstance(obj, dict):
        raise ValueError("la raíz debe ser objeto JSON")
    return obj, content


def _by_repo(document: dict, label: str) -> dict[str, dict]:
    items = document.get("repos")
    if not isinstance(items, list) or not items:
        raise ValueError(f"{label}: repos vacíos")
    result = {}
    for item in items:
        if not isinstance(item, dict):
            raise ValueError(f"{label}: entrada inválida")
        name = item.get("name")
        if (not isinstance(name, str) or not REPO.fullmatch(name)
                or any(part in (".", "..") for part in name.split("/"))
                or name in result):
            raise ValueError(f"{label}: repos duplicados o ruta insegura")
        result[name] = item
    return result


def prepare_state(collected: dict, raw_collected: bytes, summaries: dict,
                  previous: dict, config_names: list[str],
                  expected_run_id: str | None = None) -> dict[str, object]:
    """Pure validation and staging plan; no filesystem mutations."""
    c = _by_repo(collected, "recolección")
    s = _by_repo(summaries, "síntesis")
    if (not config_names or len(set(config_names)) != len(config_names)
            or set(c) != set(s) or set(c) != set(config_names)):
        raise ValueError("recolección y síntesis no cubren los mismos repos configurados")
    if not isinstance(previous, dict):
        raise ValueError("estado previo inválido")

    generated = _utc(collected.get("generated_at"))
    if _utc(summaries.get("generated_at")) != generated:
        raise ValueError("síntesis de otra recolección")
    if generated > datetime.now(timezone.utc) + timedelta(minutes=5):
        raise ValueError("fecha de recolección futura")
    if summaries.get("source_collected_sha256") != hashlib.sha256(raw_collected).hexdigest():
        raise ValueError("síntesis desacoplada del JSON de recolección")
    if expected_run_id:
        if (not RUN_ID.fullmatch(expected_run_id)
                or collected.get("github_run_id") != expected_run_id
                or summaries.get("github_run_id") != expected_run_id):
            raise ValueError("origen de otro GITHUB_RUN_ID")
    elif collected.get("github_run_id") != summaries.get("github_run_id"):
        raise ValueError("origen GitHub no coincide")

    new_previous = dict(previous)
    narratives: dict[str, str] = {}
    for name in config_names:
        raw = c[name]
        summary = s[name]
        start = _utc(raw.get("since"))
        end = _utc(raw.get("until"))
        if not start <= end <= generated:
            raise ValueError(f"intervalo inválido: {name}")
        if _utc(summary.get("since")) != start or _utc(summary.get("until")) != end:
            raise ValueError(f"síntesis de otro intervalo: {name}")
        old = previous.get(name, {})
        if not isinstance(old, dict):
            raise ValueError(f"estado previo ilegible: {name}")
        if "since" in old and end < _utc(old["since"]):
            raise ValueError(f"retroceso del estado: {name}")
        tags = raw.get("tags_all")
        if not isinstance(tags, list) or any(not isinstance(t, str) for t in tags):
            raise ValueError(f"etiquetas inválidas: {name}")
        narrative = summary.get("narrativa_actualizada")
        if not isinstance(narrative, str) or not narrative.strip():
            raise ValueError(f"narrativa ausente: {name}")
        basename = name.split("/")[1]
        key = basename.casefold()
        if key in narratives:
            raise ValueError("dos repositorios colisionan en la ruta de narrativa")
        narratives[key] = narrative.strip() + "\n"
        new_previous[name] = {"since": raw["until"], "tags_seen": tags}

    return {"last_run": new_previous, "narratives": {
        name.split("/")[1] + ".md": narratives[name.split("/")[1].casefold()]
        for name in config_names}}


def _check_target(path: Path, expected_parent: Path) -> None:
    if path.is_symlink() or path.parent.is_symlink() or path.parent.resolve() != expected_parent.resolve():
        raise ValueError(f"destino de estado inseguro: {path}")


def _temp_file(parent: Path, content: bytes) -> Path:
    with tempfile.NamedTemporaryFile(prefix=".devlog-stage-", dir=parent,
                                     delete=False) as f:
        name = Path(f.name)
        f.write(content)
        f.flush()
        os.fsync(f.fileno())
    return name


def install_state(updates: dict[Path, bytes], state_dir: Path, narrative_dir: Path) -> None:
    """Stage every write; best-effort rollback of previous state on I/O errors."""
    staged: dict[Path, Path] = {}
    backups: dict[Path, Path | None] = {}
    replaced: list[Path] = []
    preserve_backups = False
    for path in updates:
        _check_target(path, narrative_dir if path.parent == narrative_dir else state_dir)
    narrative_dir.mkdir(parents=True, exist_ok=True)
    try:
        for target, data in updates.items():
            staged[target] = _temp_file(target.parent, data)
            backups[target] = (_temp_file(target.parent, target.read_bytes())
                               if target.exists() else None)
        for target, stage in staged.items():
            os.replace(stage, target)
            replaced.append(target)
    except Exception:
        errors = []
        for target in reversed(replaced):
            try:
                backup = backups[target]
                if backup is not None:
                    os.replace(backup, target)
                else:
                    target.unlink()
            except OSError as exc:
                errors.append(f"{target}: {exc}")
        if errors:
            # NEVER destroy the only recoverable copies if rollback failed.
            # Keep every existing backup so an operator can inspect/recover
            # the previous state. Restrictive tempfile permissions are kept.
            preserve_backups = True
            recovery = ", ".join(
                f"{target} <- {backup}" for target, backup in backups.items()
                if backup is not None and backup.exists()
            )
            raise RuntimeError(
                "rollback del estado incompleto: " + "; ".join(errors)
                + "; respaldos conservados para recuperación manual: " + recovery
            )
        raise
    finally:
        for temp in staged.values():
            temp.unlink(missing_ok=True)
        if not preserve_backups:
            for backup in backups.values():
                if backup is not None:
                    backup.unlink(missing_ok=True)


def validated_updates() -> dict[Path, bytes]:
    """One shared, read-only validation gate for preflight and final commit."""
    import yaml

    collected, raw = _read_json(COLLECTED_PATH)
    summaries, _ = _read_json(SUMMARIES_PATH)
    _check_target(LAST_RUN_PATH, LAST_RUN_PATH.parent)
    previous = json.loads(LAST_RUN_PATH.read_text(encoding="utf-8")) if LAST_RUN_PATH.exists() else {}
    if not isinstance(previous, dict):
        raise ValueError("estado anterior inválido")
    if CONFIG_PATH.is_symlink():
        raise ValueError("configuración de repos insegura")
    config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    if not isinstance(config, dict) or not isinstance(config.get("repos"), list):
        raise ValueError("configuración de repos inválida")
    names = [item["name"] for item in config["repos"]]
    plan = prepare_state(collected, raw, summaries, previous, names,
                         os.environ.get("GITHUB_RUN_ID"))
    updates = {LAST_RUN_PATH: (json.dumps(plan["last_run"], indent=2,
                                   ensure_ascii=False) + "\n").encode("utf-8")}
    for filename, narrative in plan["narratives"].items():
        path = NARRATIVE_DIR / filename
        _check_target(path, NARRATIVE_DIR)
        updates[path] = narrative.encode("utf-8")
    return updates


def check_state() -> int:
    """Pre-publish gate: reject incoherent inputs without writing any state."""
    updates = validated_updates()
    count = len(updates) - 1
    print(f"Prepublicación validada: {count} repositorios, estado intacto")
    return count


def confirm_state() -> int:
    updates = validated_updates()
    install_state(updates, LAST_RUN_PATH.parent, NARRATIVE_DIR)
    count = len(updates) - 1
    print(f"Estado semanal confirmado: {count} repositorios, un solo origen validado")
    return count


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-only", action="store_true",
                        help="Valida procedencia y estado sin escribir archivos.")
    options = parser.parse_args()
    if options.check_only:
        check_state()
    else:
        confirm_state()
