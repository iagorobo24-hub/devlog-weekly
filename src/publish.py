"""deck -> Drive. Sube out/deck.pdf a Google Drive vía rclone.

Sigue la estructura del skeleton:
    Portfolio/
    ├── semanal/<ISO-week>/devlog.pdf
    ├── master/portfolio.pdf   (deck maestro, fuera de alcance por ahora)
    └── assets/

La semana se calcula a partir de "generated_at" en out/summaries.json, no de
la fecha de hoy: así el destino es determinista a partir de los datos que ya
recogió el pipeline, no de cuándo por casualidad se ejecuta publish.py.

Necesita:
- rclone en el PATH.
- RCLONE_CONF: contenido completo de un rclone.conf con un remote de Google
  Drive ya configurado vía service account (sin flujo interactivo — así
  funciona en GitHub Actions). Se escribe a un archivo temporal con
  permisos 600 durante la subida y se borra al terminar; nunca se toca
  ~/.config/rclone/.
- RCLONE_REMOTE: nombre del remote dentro de ese rclone.conf (por defecto
  "gdrive").

Flags:
  --dry-run          no sube nada; imprime el destino calculado y sale
  --remote NOMBRE    nombre del remote de rclone (por defecto RCLONE_REMOTE
                      o "gdrive")
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SUMMARIES_PATH = ROOT / "out" / "summaries.json"
DECK_PDF_PATH = ROOT / "out" / "deck.pdf"

DEFAULT_REMOTE = os.environ.get("RCLONE_REMOTE", "gdrive")

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("publish")


def load_generated_at() -> datetime:
    if not SUMMARIES_PATH.exists():
        log.error("%s no existe; corre synthesize.py primero", SUMMARIES_PATH)
        sys.exit(1)
    data = json.loads(SUMMARIES_PATH.read_text(encoding="utf-8"))
    return datetime.fromisoformat(data["generated_at"])


def iso_week_folder(dt: datetime) -> str:
    year, week, _ = dt.isocalendar()
    return f"{year}-W{week:02d}"


def remote_path(remote: str, week: str) -> str:
    return f"{remote}:Portfolio/semanal/{week}/devlog.pdf"


def upload(local_path: Path, dest: str, rclone_conf: str) -> None:
    rclone = shutil.which("rclone")
    if rclone is None:
        log.error("rclone no está instalado (ver https://rclone.org/install/)")
        sys.exit(1)

    # mkstemp crea el archivo con permisos 600 por defecto: el contenido
    # (credenciales de la service account) nunca queda legible por otros.
    fd, conf_path_str = tempfile.mkstemp(prefix="rclone-", suffix=".conf")
    conf_path = Path(conf_path_str)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(rclone_conf)
        subprocess.run([rclone, "--config", str(conf_path), "copyto", str(local_path), dest], check=True)
    finally:
        conf_path.unlink(missing_ok=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="No sube nada; imprime el destino calculado.")
    parser.add_argument("--remote", default=DEFAULT_REMOTE, help=f"Nombre del remote de rclone (por defecto {DEFAULT_REMOTE}).")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if not DECK_PDF_PATH.exists():
        log.error("%s no existe; corre render.py primero", DECK_PDF_PATH)
        sys.exit(1)

    generated_at = load_generated_at()
    week = iso_week_folder(generated_at)
    dest = remote_path(args.remote, week)

    if args.dry_run:
        log.info("dry-run: subiría %s -> %s", DECK_PDF_PATH, dest)
        return

    rclone_conf = os.environ.get("RCLONE_CONF")
    if not rclone_conf:
        log.error("falta la variable de entorno RCLONE_CONF")
        sys.exit(1)

    try:
        upload(DECK_PDF_PATH, dest, rclone_conf)
    except subprocess.CalledProcessError as e:
        log.error("rclone falló subiendo a %s (código %d)", dest, e.returncode)
        sys.exit(1)
    log.info("subido %s -> %s", DECK_PDF_PATH, dest)


if __name__ == "__main__":
    main()
