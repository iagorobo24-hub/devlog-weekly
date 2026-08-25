"""deck -> Drive. Sube out/deck.pdf (o out/portfolio.pdf) a Google Drive vía rclone.

Sigue la estructura del skeleton:
    Portfolio/
    ├── semanal/<ISO-week>/devlog.pdf
    ├── master/portfolio.pdf
    └── assets/

--target semanal (por defecto) sube out/deck.pdf. La semana se calcula a
partir de "generated_at" en out/summaries.json, no de la fecha de hoy: así
el destino es determinista a partir de los datos que ya recogió el
pipeline, no de cuándo por casualidad se ejecuta publish.py.

--target master sube out/portfolio.pdf a Portfolio/master/portfolio.pdf. Si
ese archivo no existe (render_master.py decidió saltarse esta semana por el
umbral de actividad), no es un error: se loguea y se sale sin más.

Necesita:
- rclone en el PATH.
- RCLONE_CONF: contenido completo de un rclone.conf con un remote de Google
  Drive ya configurado (token OAuth con refresh_token — una service account
  NO funciona en Drive personal/Gmail: no tiene cuota propia ni siquiera en
  carpetas compartidas con ella, solo en Shared Drives de Workspace). Se
  escribe a un archivo temporal con permisos 600 durante la subida y se
  borra al terminar; nunca se toca ~/.config/rclone/.
- RCLONE_REMOTE: nombre del remote dentro de ese rclone.conf (por defecto
  "gdrive").

Flags:
  --dry-run          no sube nada; imprime el destino calculado y sale
  --target {semanal,master}   qué deck subir (por defecto semanal)
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
PORTFOLIO_PDF_PATH = ROOT / "out" / "portfolio.pdf"

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


def weekly_remote_path(remote: str, week: str) -> str:
    return f"{remote}:Portfolio/semanal/{week}/devlog.pdf"


def master_remote_path(remote: str) -> str:
    return f"{remote}:Portfolio/master/portfolio.pdf"


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
    parser.add_argument("--target", choices=["semanal", "master"], default="semanal", help="Qué deck subir (por defecto semanal).")
    parser.add_argument("--remote", default=DEFAULT_REMOTE, help=f"Nombre del remote de rclone (por defecto {DEFAULT_REMOTE}).")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.target == "master":
        local_path = PORTFOLIO_PDF_PATH
        if not local_path.exists():
            log.info("%s no existe (el deck maestro no se generó esta semana); nada que publicar", local_path)
            return
        dest = master_remote_path(args.remote)
    else:
        local_path = DECK_PDF_PATH
        if not local_path.exists():
            log.error("%s no existe; corre render.py primero", local_path)
            sys.exit(1)
        week = iso_week_folder(load_generated_at())
        dest = weekly_remote_path(args.remote, week)

    if args.dry_run:
        log.info("dry-run: subiría %s -> %s", local_path, dest)
        return

    rclone_conf = os.environ.get("RCLONE_CONF")
    if not rclone_conf:
        log.error("falta la variable de entorno RCLONE_CONF")
        sys.exit(1)

    try:
        upload(local_path, dest, rclone_conf)
    except subprocess.CalledProcessError as e:
        log.error("rclone falló subiendo a %s (código %d)", dest, e.returncode)
        sys.exit(1)
    log.info("subido %s -> %s", local_path, dest)


if __name__ == "__main__":
    main()
