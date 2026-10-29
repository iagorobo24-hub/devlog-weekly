"""deck -> Drive. Sube out/deck.pdf (o out/portfolio.pdf/.mp4) a Google Drive vía rclone.

Sigue la estructura del skeleton:
    Portfolio/
    ├── semanal/<ISO-week>/devlog.pdf
    ├── master/portfolio.pdf
    ├── master/portfolio.mp4
    └── assets/

--target semanal (por defecto) sube out/deck.pdf. La semana se calcula a
partir de "generated_at" en out/summaries.json, no de la fecha de hoy: así
el destino es determinista a partir de los datos que ya recogió el
pipeline, no de cuándo por casualidad se ejecuta publish.py.

--target master sube out/portfolio.pdf a Portfolio/master/portfolio.pdf, y
out/portfolio.mp4 (si existe) a Portfolio/master/portfolio.mp4 — el vídeo
narrado que genera render_video.py. Cada archivo se evalúa por separado: si
no existe (render_master.py / render_video.py decidieron saltarse esta
semana por el umbral de actividad), no es un error, solo se loguea y se
sigue con el resto.

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
import hashlib
import re
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
PORTFOLIO_MP4_PATH = ROOT / "out" / "portfolio.mp4"
PORTFOLIO_SRT_PATH = ROOT / "out" / "portfolio.srt"

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


def master_video_remote_path(remote: str) -> str:
    return f"{remote}:Portfolio/master/portfolio.mp4"


def master_subtitle_remote_path(remote: str) -> str:
    return f"{remote}:Portfolio/master/portfolio.srt"


def verified_master_release(uploads: list[tuple[Path, str]], rclone_conf: str,
                            remote: str, run_id: str) -> None:
    """Version all outputs + SHA256 readback before replacing live aliases."""
    if not re.fullmatch(r"[0-9]{5,20}-[0-9]{1,6}", run_id):
        raise ValueError("GITHUB_RUN_ID inválido para publicación versionada")
    stage_paths = []
    for local, alias in uploads:
        versioned = f"{remote}:Portfolio/master/versions/{run_id}/{local.name}"
        upload(local, versioned, rclone_conf, remote, immutable=True)
        stage_paths.append((local, alias, versioned))
    with tempfile.TemporaryDirectory(prefix="master-v2-verify-") as tempdir:
        for local, _, remote_version in stage_paths:
            restored = Path(tempdir) / local.name
            upload(Path(remote_version), str(restored), rclone_conf, remote)
            if hashlib.sha256(local.read_bytes()).digest() != hashlib.sha256(restored.read_bytes()).digest():
                raise ValueError(f"Drive no devolvió bytes idénticos: {local.name}")
    for _, alias, versioned in stage_paths:
        upload(Path(versioned), alias, rclone_conf, remote)
    log.info("master V2 versionado, verificado y actualizado: %s", run_id)


def upload(local_path: Path, dest: str, rclone_conf: str, remote: str, immutable: bool = False) -> None:
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
        # Permite migrar a OAuth propio sin reescribir RCLONE_CONF ni exponer
        # client_secret en los argumentos visibles del proceso.
        env = os.environ.copy()
        own_client_id = env.get("RCLONE_DRIVE_CLIENT_ID", "")
        own_client_secret = env.get("RCLONE_DRIVE_CLIENT_SECRET", "")
        if own_client_id and own_client_secret:
            prefix = f"RCLONE_CONFIG_{remote.upper().replace('-', '_')}"
            env[f"{prefix}_CLIENT_ID"] = own_client_id
            env[f"{prefix}_CLIENT_SECRET"] = own_client_secret
        else:
            log.warning("OAuth Drive propio no configurado; el client_id compartido de rclone dejará de funcionar en 2026")
        command = [rclone, "--config", str(conf_path)]
        if immutable:
            command.append("--immutable")
        command.extend(["copyto", str(local_path), dest])
        subprocess.run(command, check=True, env=env)
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
        uploads = []
        v2_release = os.environ.get("PORTFOLIO_V2_RELEASE") == "1"
        paths = (
            (PORTFOLIO_PDF_PATH, master_remote_path(args.remote)),
            (PORTFOLIO_MP4_PATH, master_video_remote_path(args.remote)),
            (PORTFOLIO_SRT_PATH, master_subtitle_remote_path(args.remote)),
        )
        if v2_release:
            if any(p.exists() for p, _ in paths) and not all(p.is_file() for p, _ in paths):
                raise RuntimeError("publicación parcial bloqueada: faltan artefactos V2")
            uploads = [(p, alias) for p, alias in paths if p.is_file()]
        else:
            # Legacy caller keeps previous behavior (PDF/MP4 optional).
            uploads = [(p, alias) for p, alias in paths[:2] if p.is_file()]
        if not uploads:
            log.info("sin cambios showcase: no hay PDF/MP4 de master que publicar")
    else:
        if not DECK_PDF_PATH.exists():
            log.error("%s no existe; corre render.py primero", DECK_PDF_PATH)
            sys.exit(1)
        week = iso_week_folder(load_generated_at())
        uploads = [(DECK_PDF_PATH, weekly_remote_path(args.remote, week))]

    if args.dry_run:
        for local_path, dest in uploads:
            log.info("dry-run: subiría %s -> %s", local_path, dest)
        return

    if not uploads:
        return

    rclone_conf = os.environ.get("RCLONE_CONF")
    if not rclone_conf:
        log.error("falta la variable de entorno RCLONE_CONF")
        sys.exit(1)

    if args.target == "master" and os.environ.get("PORTFOLIO_V2_RELEASE") == "1":
        try:
            verified_master_release(uploads, rclone_conf, args.remote, os.environ.get("GITHUB_RUN_ID", "") + "-" + os.environ.get("GITHUB_RUN_ATTEMPT", "1"))
        except (ValueError, subprocess.CalledProcessError) as exc:
            log.error("Publicación master V2 bloqueada: %s", exc)
            sys.exit(1)
        return

    for local_path, dest in uploads:
        try:
            upload(local_path, dest, rclone_conf, args.remote)
        except subprocess.CalledProcessError as e:
            log.error("rclone falló subiendo a %s (código %d)", dest, e.returncode)
            sys.exit(1)
        log.info("subido %s -> %s", local_path, dest)


if __name__ == "__main__":
    main()
