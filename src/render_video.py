"""portfolio.md -> vídeo narrado. Determinista salvo por la voz sintética.

El vídeo que el skeleton dejaba pendiente ("ffmpeg + Piper TTS sobre el
deck"), aplicado al deck MAESTRO (out/portfolio.md), no al semanal: una
slide por repo showcase, narrando el pitch + la narrativa acumulada que
ya escribió synthesize.py. No hay llamada al modelo aquí tampoco — el
texto que se narra es el mismo que ya se maqueta en render_master.py,
solo que hablado en vez de leído.

La voz es edge-tts (voces neuronales de Microsoft Edge, gratis, sin API
key), no Piper como decía el skeleton original: Piper se probó primero
y sonaba demasiado robótico, edge-tts es sensiblemente más natural. Es
la misma idea que usa MoneyPrinterTurbo (harry0703/MoneyPrinterTurbo)
como motor de TTS por defecto.

Reutiliza el umbral de render_master.py (mismo criterio: se salta si
ningún repo showcase tuvo actividad esta semana) para no generar un vídeo
idéntico al de la semana pasada. --force lo ignora.

Pipeline por slide:
  1. Marp exporta cada slide de out/portfolio.md a PNG (--images png).
  2. edge-tts sintetiza la narración de esa slide a MP3.
  3. ffmpeg combina imagen fija + audio en un clip .mp4, con un margen de
     ~0.35s de vídeo extra sobre la duración del audio (si no, el redondeo
     de fps corta la última sílaba — visto en proyectos similares como
     MoneyPrinterTurbo).
  4. Los clips se concatenan (concat demuxer, sin recodificar) en
     out/portfolio.mp4.

Necesita:
- ffmpeg y ffprobe en el PATH.
- marp-cli (como render.py / render_master.py).
- El paquete Python edge-tts (dependencia del proyecto). Llama al
  servicio de Microsoft por red — hace falta conexión a internet al
  generar (no hace falta API key).

Flags:
  --force    ignora el umbral de actividad; genera igual si hay narrativa
  --voice    voz de edge-tts (por defecto es-ES-AlvaroNeural; `edge-tts
             --list-voices` lista las disponibles)
"""

from __future__ import annotations

import argparse
import logging
import shutil
import subprocess
import sys
from pathlib import Path

from render_master import (
    PORTFOLIO_MD_PATH,
    THEME_PATH,
    had_showcase_activity_this_week,
    load_narrative,
    load_showcase_repos,
)

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_VOICE = "es-ES-AlvaroNeural"
WORK_DIR = ROOT / "out" / "video"
PORTFOLIO_MP4_PATH = ROOT / "out" / "portfolio.mp4"

TITLE_NARRATION = "Portfolio de proyectos personales."
SEGMENT_PADDING_SECONDS = 0.35

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("render_video")


def require_tool(name: str, hint: str) -> str:
    path = shutil.which(name)
    if path is None:
        log.error("%s no está instalado (%s)", name, hint)
        sys.exit(1)
    return path


def narration_text(entry: dict) -> str:
    parts = [entry["name"].split("/")[-1] + "."]
    if entry.get("pitch"):
        parts.append(entry["pitch"] + ".")
    parts.append(entry["narrativa"])
    return " ".join(parts)


def synthesize_audio(text: str, text_path: Path, audio_path: Path, voice: str) -> None:
    text_path.write_text(text, encoding="utf-8")
    subprocess.run(
        ["edge-tts", "--voice", voice, "--file", str(text_path), "--write-media", str(audio_path)],
        check=True,
        capture_output=True,
    )


def audio_duration_seconds(audio_path: Path) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(audio_path)],
        check=True,
        capture_output=True,
        text=True,
    )
    return float(result.stdout.strip())


def build_segment(image_path: Path, audio_path: Path, out_path: Path) -> None:
    duration = audio_duration_seconds(audio_path) + SEGMENT_PADDING_SECONDS
    subprocess.run(
        [
            "ffmpeg", "-y", "-loop", "1", "-i", str(image_path), "-i", str(audio_path),
            "-c:v", "libx264", "-tune", "stillimage", "-c:a", "aac", "-b:a", "192k",
            "-pix_fmt", "yuv420p", "-t", f"{duration:.3f}", str(out_path),
        ],
        check=True,
        capture_output=True,
    )


def export_slide_images() -> list[Path]:
    marp = require_tool("marp", "npm install -g @marp-team/marp-cli")
    subprocess.run(
        [
            marp, str(PORTFOLIO_MD_PATH), "--images", "png", "--allow-local-files",
            "--theme-set", str(THEME_PATH), "-o", str(WORK_DIR / "slide.png"),
        ],
        check=True,
    )
    return sorted(WORK_DIR.glob("slide.*.png"))


def concat_segments(segments: list[Path]) -> None:
    list_path = WORK_DIR / "concat.txt"
    list_path.write_text("".join(f"file '{seg}'\n" for seg in segments), encoding="utf-8")
    subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(list_path), "-c", "copy", str(PORTFOLIO_MP4_PATH)],
        check=True,
        capture_output=True,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--force", action="store_true", help="Ignora el umbral de actividad; genera igual si hay narrativa.")
    parser.add_argument("--voice", default=DEFAULT_VOICE, help=f"Voz de edge-tts (por defecto {DEFAULT_VOICE}).")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    showcase_repos = load_showcase_repos()
    if not showcase_repos:
        log.info("ningún repo marcado como showcase: true; no genero vídeo")
        return

    entries = []
    for repo_cfg in showcase_repos:
        narrativa = load_narrative(repo_cfg["name"])
        if not narrativa:
            continue
        entries.append({"name": repo_cfg["name"], "pitch": repo_cfg.get("pitch"), "narrativa": narrativa})

    if not entries:
        log.info("ningún repo showcase tiene narrativa acumulada todavía; no genero vídeo")
        return

    if not args.force:
        showcase_names = {r["name"] for r in showcase_repos}
        if not had_showcase_activity_this_week(showcase_names):
            log.info("ningún repo showcase tuvo actividad esta semana; me salto el vídeo (usa --force para generarlo igual)")
            return

    if not PORTFOLIO_MD_PATH.exists():
        log.error("%s no existe; corre render_master.py primero", PORTFOLIO_MD_PATH)
        sys.exit(1)

    require_tool("ffmpeg", "https://ffmpeg.org/download.html")
    require_tool("ffprobe", "viene con ffmpeg")
    require_tool("edge-tts", "pip install edge-tts")

    if WORK_DIR.exists():
        shutil.rmtree(WORK_DIR)
    WORK_DIR.mkdir(parents=True)

    slide_images = export_slide_images()
    if len(slide_images) != len(entries) + 1:
        log.error(
            "%d slides exportadas pero %d esperadas (1 título + %d repos); ¿out/portfolio.md desincronizado?",
            len(slide_images), len(entries) + 1, len(entries),
        )
        sys.exit(1)
    log.info("exportadas %d slides", len(slide_images))

    segments = []
    for i, (image_path, text) in enumerate(
        zip(slide_images, [TITLE_NARRATION] + [narration_text(e) for e in entries]), start=1
    ):
        text_path = WORK_DIR / f"narration.{i:03d}.txt"
        audio_path = WORK_DIR / f"narration.{i:03d}.mp3"
        seg_path = WORK_DIR / f"segment.{i:03d}.mp4"
        synthesize_audio(text, text_path, audio_path, args.voice)
        build_segment(image_path, audio_path, seg_path)
        segments.append(seg_path)
        log.info("clip %d/%d listo", i, len(slide_images))

    concat_segments(segments)
    log.info("escrito %s (%d slides narradas)", PORTFOLIO_MP4_PATH, len(segments))


if __name__ == "__main__":
    main()
