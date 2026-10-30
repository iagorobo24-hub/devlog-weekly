"""deck -> Drive. Sube out/deck.pdf (o out/portfolio.pdf/.mp4) a Google Drive vía rclone.

Sigue la estructura del skeleton:
    Portfolio/
    ├── semanal/<ISO-week>/devlog.pdf
    ├── master/portfolio.pdf
    ├── master/portfolio.mp4
    └── assets/

--target semanal (por defecto) publica out/deck.pdf con versión inmutable
y verifica mediante SHA256 tanto la versión como el alias semanal. La
semana se calcula a partir de "generated_at" en out/summaries.json, no
de la fecha de hoy: así el destino es determinista a partir de los datos
que ya recogió el pipeline, no de cuándo por casualidad se ejecuta.
La versión usa GITHUB_RUN_ID-GITHUB_RUN_ATTEMPT en Actions, o una
marca temporal UTC distinta al ejecutar la publicación manualmente.

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
from datetime import datetime, timezone
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


def master_current_remote_path(remote: str) -> str:
    """One release pointer for readers requiring a coherent PDF/MP4/SRT set."""
    return f"{remote}:Portfolio/master/current.json"


MASTER_FILES = ("portfolio.pdf", "portfolio.mp4", "portfolio.srt")


def _master_release_document(remote: str, run_id: str, frozen: dict) -> dict:
    return {
        "schema": 1,
        "run_id": run_id,
        "files": {
            name: {
                "path": f"Portfolio/master/versions/{run_id}/{name}",
                "sha256": frozen[name].hex(),
            }
            for name in MASTER_FILES
        },
    }


def _validate_master_release_document(document: object, remote: str) -> dict:
    """Fail closed before following a remote path from a published pointer."""
    if not isinstance(document, dict) or set(document) != {"schema", "run_id", "files"}:
        raise ValueError("puntero master inválido")
    run_id = document.get("run_id")
    if (document.get("schema") != 1 or not isinstance(run_id, str)
            or not re.fullmatch(r"[0-9]{5,20}-[0-9]{1,6}", run_id)):
        raise ValueError("puntero master con ejecución inválida")
    files = document.get("files")
    if not isinstance(files, dict) or set(files) != set(MASTER_FILES):
        raise ValueError("puntero master incompleto")
    for name in MASTER_FILES:
        entry = files[name]
        if (not isinstance(entry, dict) or set(entry) != {"path", "sha256"}
                or entry["path"] != f"Portfolio/master/versions/{run_id}/{name}"
                or not isinstance(entry["sha256"], str)
                or not re.fullmatch(r"[0-9a-f]{64}", entry["sha256"])):
            raise ValueError("puntero master con versión o hash no canónicos")
    return document


def download_verified_master_snapshot(remote: str, rclone_conf: str,
                                      destination: Path) -> dict:
    """Download a coherent immutable master release, never the mutable aliases.

    Caller should supply a fresh empty local directory. No files are written
    until the remote pointer is parsed and all three bytes are verified.
    """
    if not re.fullmatch(r"[A-Za-z0-9_-]+", remote):
        raise ValueError("nombre remoto inválido")
    if (destination.exists() or destination.is_symlink()
            or not destination.parent.is_dir()
            or destination.parent.is_symlink()):
        raise ValueError("directorio destino debe ser nuevo y tener padre seguro")
    with tempfile.TemporaryDirectory(
            prefix="devlog-master-snapshot-", dir=destination.parent) as folder:
        temp = Path(folder)
        pointer_path = temp / "current.json"
        upload(Path(master_current_remote_path(remote)), str(pointer_path),
               rclone_conf, remote)
        try:
            document = _validate_master_release_document(
                json.loads(pointer_path.read_text(encoding="utf-8")), remote)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ValueError("puntero master JSON inválido") from exc
        for name in MASTER_FILES:
            info = document["files"][name]
            local = temp / name
            upload(Path(f"{remote}:{info['path']}"), str(local), rclone_conf, remote)
            if hashlib.sha256(local.read_bytes()).hexdigest() != info["sha256"]:
                raise ValueError(f"snapshot master corrupto: {name}")
        # Publish the local set as one directory rename, not three
        # independently visible files that a reader could observe half-written.
        complete = temp / "complete"
        complete.mkdir()
        for name in MASTER_FILES:
            shutil.copyfile(temp / name, complete / name)
        os.replace(complete, destination)
    return document


def verified_weekly_release(local: Path, alias: str, rclone_conf: str,
                            remote: str, run_id: str) -> None:
    """Preserve a version; read it back before making the weekly alias visible.

    Upload failures or corrupted staged bytes never update the public weekly
    path. A failure while replacing the alias leaves the pinned version
    intact and prevents the pipeline from confirming GitHub state.
    """
    if not re.fullmatch(r"[0-9]{5,20}-[0-9]{1,6}", run_id):
        raise ValueError("GITHUB_RUN_ID inválido para publicación semanal versionada")
    expected_prefix = f"{remote}:Portfolio/semanal/"
    match = re.fullmatch(re.escape(expected_prefix) +
                         r"(20[0-9]{2}-W(?:0[1-9]|[1-4][0-9]|5[0-3]))/devlog\.pdf",
                         alias)
    if match is None:
        raise ValueError("ruta semanal no canónica")
    if not local.is_file() or local.is_symlink() or local.stat().st_size == 0:
        raise ValueError("PDF semanal inexistente o inválido")
    with local.open("rb") as stream:
        if stream.read(5) != b"%PDF-":
            raise ValueError("archivo semanal sin cabecera PDF")
    frozen_digest = hashlib.sha256(local.read_bytes()).digest()
    versioned = (f"{remote}:Portfolio/semanal/{match.group(1)}"
                 f"/versions/{run_id}/devlog.pdf")
    upload(local, versioned, rclone_conf, remote, immutable=True)

    with tempfile.TemporaryDirectory(prefix="weekly-verify-") as tmp:
        verified = Path(tmp) / "staged.pdf"
        upload(Path(versioned), str(verified), rclone_conf, remote)
        if (hashlib.sha256(verified.read_bytes()).digest() != frozen_digest
                or hashlib.sha256(local.read_bytes()).digest() != frozen_digest):
            raise ValueError("Drive no devolvió bytes idénticos del PDF semanal versionado")

        # Only after the versioned bytes match the original do we replace
        # the visible weekly alias, then read the alias back as well.
        upload(Path(versioned), alias, rclone_conf, remote)
        restored_alias = Path(tmp) / "published.pdf"
        upload(Path(alias), str(restored_alias), rclone_conf, remote)
        if hashlib.sha256(restored_alias.read_bytes()).digest() != frozen_digest:
            raise ValueError("Drive no devolvió bytes idénticos del PDF semanal publicado")
    log.info("PDF semanal versionado y comprobado: %s", run_id)


def verified_master_release(uploads: list[tuple[Path, str]], rclone_conf: str,
                            remote: str, run_id: str,
                            expected_sha256: dict[str, str] | None = None) -> None:
    """Version all outputs + SHA256 readback before replacing live aliases."""
    if not re.fullmatch(r"[0-9]{5,20}-[0-9]{1,6}", run_id):
        raise ValueError("GITHUB_RUN_ID inválido para publicación versionada")
    stage_paths = []
    for local, alias in uploads:
        if not local.is_file() or local.is_symlink() or local.stat().st_size == 0:
            raise ValueError(f"artefacto master inválido: {local.name}")
    # Freeze every source before the first external write, so a changed
    # local source cannot silently produce a mixed PDF/video/subtitle release.
    frozen = {local: hashlib.sha256(local.read_bytes()).digest()
              for local, _ in uploads}
    if expected_sha256 is not None:
        if (not isinstance(expected_sha256, dict)
                or any(expected_sha256.get(
                    {"portfolio.pdf": "pdf", "portfolio.mp4": "mp4",
                     "portfolio.srt": "srt"}.get(local.name, local.name))
                    != frozen[local].hex()
                    for local, _ in uploads)):
            raise ValueError("artefactos master distintos del recibo aprobado")
    for local, alias in uploads:
        versioned = f"{remote}:Portfolio/master/versions/{run_id}/{local.name}"
        upload(local, versioned, rclone_conf, remote, immutable=True)
        stage_paths.append((local, alias, versioned))
    with tempfile.TemporaryDirectory(prefix="master-v2-verify-") as tempdir:
        for local, _, remote_version in stage_paths:
            restored = Path(tempdir) / ("stage-" + local.name)
            upload(Path(remote_version), str(restored), rclone_conf, remote)
            if (frozen[local] != hashlib.sha256(restored.read_bytes()).digest()
                    or frozen[local] != hashlib.sha256(local.read_bytes()).digest()):
                raise ValueError(f"Drive no devolvió bytes idénticos: {local.name}")
        for local, alias, versioned in stage_paths:
            upload(Path(versioned), alias, rclone_conf, remote)
            restored = Path(tempdir) / ("alias-" + local.name)
            upload(Path(alias), str(restored), rclone_conf, remote)
            if hashlib.sha256(restored.read_bytes()).digest() != frozen[local]:
                raise ValueError(f"Drive no devolvió bytes idénticos del alias master: {local.name}")
    # Readers of current.json always resolve *versioned* bytes. A failed
    # stage or mutable-alias update never advances this single release marker.
    # Direct PDF/MP4/SRT aliases remain non-atomic for legacy consumers.
    names = {local.name for local, _ in uploads}
    if len(uploads) == len(MASTER_FILES) and names == set(MASTER_FILES):
        frozen_by_name = {local.name: frozen[local] for local, _ in uploads}
        document = _master_release_document(remote, run_id, frozen_by_name)
        _validate_master_release_document(document, remote)
        payload = (json.dumps(document, ensure_ascii=False, sort_keys=True,
                              separators=(",", ":")) + "\n").encode("utf-8")
        expected = hashlib.sha256(payload).digest()
        stage = f"{remote}:Portfolio/master/versions/{run_id}/release.json"
        current = master_current_remote_path(remote)
        with tempfile.TemporaryDirectory(prefix="master-release-marker-") as folder:
            source = Path(folder) / "release.json"
            source.write_bytes(payload)
            upload(source, stage, rclone_conf, remote, immutable=True)
            staged = Path(folder) / "staged.json"
            upload(Path(stage), str(staged), rclone_conf, remote)
            if hashlib.sha256(staged.read_bytes()).digest() != expected:
                raise ValueError("manifiesto master versionado no coincide")
            upload(Path(stage), current, rclone_conf, remote)
            checked = Path(folder) / "current.json"
            upload(Path(current), str(checked), rclone_conf, remote)
            if hashlib.sha256(checked.read_bytes()).digest() != expected:
                raise ValueError("puntero master actual no coincide")
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
            # Versioned retries must compare bytes, not the mtime of a newly
            # created local manifest containing exactly the same JSON.
            command.extend(["--immutable", "--checksum"])
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

    if args.target == "semanal":
        # A verified Drive upload proves byte integrity, not that the PDF
        # corresponds to this run's collected and synthesized data.
        try:
            from src import deck_provenance
        except ModuleNotFoundError:
            import deck_provenance
        deck_provenance.verify_manifest(
            summary=SUMMARIES_PATH, collected=ROOT / "out" / "collected.json",
            pdf=DECK_PDF_PATH,
            markdown=ROOT / "out" / "deck.md",
            template=ROOT / "templates" / "deck.md.j2",
            theme=ROOT / "templates" / "theme.css",
            manifest=ROOT / "out" / "deck-provenance.json",
            expected_run_id=os.environ.get("GITHUB_RUN_ID"))

    release_proof = None
    if args.target == "master" and os.environ.get("PORTFOLIO_V2_RELEASE") == "1":
        # A complete set of files is not proof that this invocation rendered
        # and quality-checked it. Skipped/failed builds leave no release proof.
        try:
            from src import master_release_provenance as master_proof
        except ModuleNotFoundError:
            import master_release_provenance as master_proof
        release_proof = master_proof.verify_receipt(
            receipt=ROOT / "out" / "portfolio-master-release-proof.json",
            expected_run_id=os.environ.get("GITHUB_RUN_ID"),
            projects=ROOT / "content" / "portfolio" / "projects.yml",
            manifest=ROOT / "out" / "portfolio-v2-manifest.json",
            markdown=ROOT / "out" / "portfolio-v2.md",
            theme=ROOT / "templates" / "portfolio.css",
            pdf=PORTFOLIO_PDF_PATH, video=PORTFOLIO_MP4_PATH,
            subtitles=PORTFOLIO_SRT_PATH)

    rclone_conf = os.environ.get("RCLONE_CONF")
    if not rclone_conf:
        log.error("falta la variable de entorno RCLONE_CONF")
        sys.exit(1)

    if args.target == "master" and os.environ.get("PORTFOLIO_V2_RELEASE") == "1":
        try:
            verified_master_release(
                uploads, rclone_conf, args.remote,
                os.environ.get("GITHUB_RUN_ID", "") + "-"
                + os.environ.get("GITHUB_RUN_ATTEMPT", "1"),
                expected_sha256=release_proof["sha256"])
        except (ValueError, subprocess.CalledProcessError) as exc:
            log.error("Publicación master V2 bloqueada: %s", exc)
            sys.exit(1)
        return

    if args.target == "semanal":
        # GitHub Actions provides immutable run ID + attempt. Local manual
        # publishing gets a distinct timestamp-based attempt identifier.
        ident = os.environ.get("GITHUB_RUN_ID") or datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        attempt = os.environ.get("GITHUB_RUN_ATTEMPT", "1")
        try:
            verified_weekly_release(uploads[0][0], uploads[0][1], rclone_conf,
                                    args.remote, f"{ident}-{attempt}")
        except (ValueError, OSError, subprocess.CalledProcessError) as exc:
            log.error("Publicación semanal bloqueada: %s", exc)
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
