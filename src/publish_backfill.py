"""Archivado histórico en carpeta nueva de Drive, inmutable y verificable.

Consume sólo los artefactos generados por backfill.py; nunca usa
state/last_run.json, ni rutas Portfolio/semanal o Portfolio/master.

El destino contiene la ventana exacta del archivo y siempre usa
--immutable para prohibir sobrescribir archivos ya existentes.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

try:
    from src.publish import upload
except ModuleNotFoundError:
    from publish import upload

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT = ROOT / "out" / "backfill"
WEEK_PATTERN = re.compile(r"^\d{4}-W\d{2}$")


def make_upload_plan(folder: Path, remote: str) -> list[tuple[Path, str]]:
    manifest_path = folder / "manifest.json"
    if not manifest_path.is_file():
        raise ValueError("falta manifest.json de la reconstrucción")
    info = json.loads(manifest_path.read_text(encoding="utf-8"))
    if info.get("source") != "public-github-metadata" or info.get("model") is not None:
        raise ValueError("manifiesto no acreditado como metadatos públicos sin IA")
    if info.get("state_modified") is not False or info.get("drive_uploaded") is not False:
        raise ValueError("manifiesto indica una operación distinta de backfill aislado")
    weeks = info.get("weeks", [])
    names = [w["week"] for w in weeks]
    if not names or len(set(names)) != len(names) or len(names) > 53:
        raise ValueError("semanas ausentes, repetidas o demasiadas")
    if names != sorted(names) or not all(WEEK_PATTERN.fullmatch(n) for n in names):
        raise ValueError("identificadores semanales no válidos")
    # Se conserva un path distinto de la publicación semanal normal.
    suffix = names[0] + "__" + names[-1]
    prefix = f"{remote}:Portfolio/historico-verificable/{suffix}"
    uploads = []
    for name in names:
        for extension in (".md", ".pdf"):
            source = folder / (name + extension)
            if not source.is_file() or source.stat().st_size == 0:
                raise ValueError(f"archivo histórico ausente o vacío: {source.name}")
            uploads.append((source, f"{prefix}/{source.name}"))
    uploads.append((manifest_path, f"{prefix}/manifest.json"))
    return uploads


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--remote", default=os.environ.get("RCLONE_REMOTE", "gdrive"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    try:
        uploads = make_upload_plan(args.output_dir, args.remote)
    except (ValueError, KeyError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    for src, destination in uploads:
        if args.dry_run:
            print(f"archivo validado: {src.name} -> {destination}")
            continue
        cfg = os.environ.get("RCLONE_CONF")
        if not cfg:
            parser.error("RCLONE_CONF requerido para la publicación")
        # --immutable: falla ante sobrescrituras de contenido distinto.
        upload(src, destination, cfg, args.remote, immutable=True)
        print(f"archivado: {src.name} -> {destination}")
    print(f"total: {len(uploads)} archivos (inmutable)")


if __name__ == "__main__":
    main()
