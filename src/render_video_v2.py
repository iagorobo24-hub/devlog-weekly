"""Audio/video rendering for the validated, editorial portfolio V2.

Uses its source-backed slide manifest, not the old accumulated AI narrative.
The smoke mode uses a generated tone without network access. No Drive writes.
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import shutil
import subprocess
from pathlib import Path

try:
    from src.portfolio_data import ROOT, load_portfolio, recent_activity, revision_alerts
    from src.render_portfolio_v2 import (
        MANIFEST_PATH, MD_PATH, THEME, build_slides, render_markdown, write_preview
    )
except ModuleNotFoundError:
    from portfolio_data import ROOT, load_portfolio, recent_activity, revision_alerts
    from render_portfolio_v2 import (
        MANIFEST_PATH, MD_PATH, THEME, build_slides, render_markdown, write_preview
    )

VIDEO_PATH = ROOT / "out" / "portfolio-v2.mp4"
SRT_PATH = ROOT / "out" / "portfolio-v2.srt"
WORK_DIR = ROOT / "out" / "v2-video"
DEFAULT_VOICE = "es-ES-AlvaroNeural"
LOG = logging.getLogger("portfolio-v2-video")


def run(args: list[str]) -> None:
    subprocess.run(args, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


def numbered_images(path: Path) -> list[Path]:
    found = list(path.glob("slide.*.png"))
    indexes = {}
    for img in found:
        match = re.fullmatch(r"slide\.(\d+)\.png", img.name)
        if not match or img.is_symlink():
            raise ValueError("imagen inesperada")
        number = int(match.group(1))
        if number in indexes:
            raise ValueError("índice de imagen duplicado")
        indexes[number] = img
    if sorted(indexes) != list(range(1, len(indexes)+1)):
        raise ValueError("secuencia de diapositivas incompleta")
    return [indexes[n] for n in sorted(indexes)]


def export_images(target: Path) -> list[Path]:
    marp = shutil.which("marp")
    if not marp:
        raise RuntimeError("marp-cli no instalado")
    target.mkdir(parents=True, exist_ok=True)
    run([marp, str(MD_PATH), "--images", "png", "--no-stdin", "--html",
         "--allow-local-files", "--theme-set", str(THEME), "-o", str(target / "slide.png")])
    return numbered_images(target)


def synthesize_audio(text: str, filename: Path, voice: str, *, smoke: bool = False) -> None:
    if smoke:
        run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
             "-i", "sine=frequency=440:duration=0.8", "-q:a", "9", str(filename)])
    else:
        inp = filename.with_suffix(".txt")
        inp.write_text(text, encoding="utf-8")
        run(["edge-tts", "--voice", voice, "--file", str(inp), "--write-media", str(filename)])


def audio_duration(path: Path) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, check=True)
    length = float(result.stdout.strip())
    if length <= 0 or length > 120:
        raise ValueError(f"duración fuera de límites: {length}")
    return length


def create_segment(image: Path, audio: Path, destination: Path, duration: float) -> None:
    fade_out = max(0.3, duration - 0.28)
    run(["ffmpeg", "-y", "-v", "error", "-loop", "1", "-framerate", "25", "-i", str(image),
         "-i", str(audio), "-t", f"{duration:.3f}",
         "-vf", f"fade=t=in:st=0:d=0.22,fade=t=out:st={fade_out:.3f}:d=0.22",
         "-c:v", "libx264", "-preset", "veryfast", "-tune", "stillimage",
         "-c:a", "aac", "-b:a", "160k", "-pix_fmt", "yuv420p",
         "-r", "25", "-movflags", "+faststart", str(destination)])


def clean_narration(text: str) -> str:
    """Normalize concatenated facts before speech AND subtitle generation."""
    cleaned = re.sub(r"\s+", " ", text).strip()
    cleaned = re.sub(r"\.+\s*;", ";", cleaned)
    cleaned = re.sub(r"([.!?])\1+", r"\1", cleaned)
    cleaned = re.sub(r";[.;]+", ";", cleaned)
    cleaned = re.sub(r"\s+([,.;!?])", r"\1", cleaned)
    return cleaned


def srt_stamp(seconds: float) -> str:
    millis = max(0, round(seconds * 1000))
    hours, rem = divmod(millis, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    sec, milli = divmod(rem, 1000)
    return f"{hours:02}:{minutes:02}:{sec:02},{milli:03}"


def build_subtitles(scripts: list[str], segment_durations: list[float]) -> str:
    if len(scripts) != len(segment_durations):
        raise ValueError("desincronización de subtítulos")
    lines = []
    cursor = 0.0
    index = 1
    for text, duration in zip(scripts, segment_durations):
        # Slide-by-slide timing, with text broken into readable captions.
        tokens = clean_narration(text).split()
        chunks, current = [], []
        for token in tokens:
            if current and len(" ".join(current + [token])) > 76:
                chunks.append(" ".join(current))
                current = []
            current.append(token)
        if current:
            chunks.append(" ".join(current))
        total_words = sum(len(chunk.split()) for chunk in chunks)
        timeline = cursor
        for chunk in chunks:
            width = (duration - 0.1) * len(chunk.split()) / max(1, total_words)
            lines.extend([str(index), f"{srt_stamp(timeline)} --> {srt_stamp(timeline + width)}", chunk, ""])
            timeline += width
            index += 1
        cursor += duration
    return "\n".join(lines)


def render(*, image_dir: Path | None = None, smoke: bool = False,
           voice: str = DEFAULT_VOICE, destination: Path = VIDEO_PATH,
           subtitles: Path = SRT_PATH) -> dict:
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise RuntimeError("ffmpeg y ffprobe son obligatorios")
    if not smoke and not shutil.which("edge-tts"):
        raise RuntimeError("edge-tts no disponible")
    data = load_portfolio()
    if not MANIFEST_PATH.exists():
        raise ValueError("falta el manifiesto de diapositivas")
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    slides = build_slides(data, recent_activity(data['projects']),
                          generation_stamp=manifest.get("generated_utc", "Vista previa"),
                          drift=revision_alerts(data["projects"]))
    expected_md = render_markdown(slides)
    if not MD_PATH.exists() or MD_PATH.read_text(encoding="utf-8") != expected_md:
        raise ValueError("portfolio-v2.md no coincide con las fichas de proyecto; regenerar")
    if [s["narration"] for s in slides] != [s["narration"] for s in manifest["slides"]]:
        raise ValueError("guion desincronizado con el manifiesto")
    if WORK_DIR.resolve().is_symlink() or WORK_DIR.is_symlink():
        raise ValueError("directorio de trabajo no seguro")
    if WORK_DIR.exists():
        shutil.rmtree(WORK_DIR)
    WORK_DIR.mkdir(parents=True)
    images = numbered_images(image_dir) if image_dir is not None else export_images(WORK_DIR)
    if len(images) != len(slides):
        raise ValueError(f"esperadas {len(slides)} diapositivas, disponibles {len(images)}")
    lengths, files = [], []
    for n, (slide, img) in enumerate(zip(slides, images), 1):
        stem = f"{n:03}"
        audio = WORK_DIR / f"audio-{stem}.mp3"
        movie = WORK_DIR / f"clip-{stem}.mp4"
        synthesize_audio(clean_narration(slide["narration"]), audio, voice, smoke=smoke)
        duration = audio_duration(audio) + 0.35
        create_segment(img, audio, movie, duration)
        lengths.append(duration)
        files.append(movie)
        LOG.info("clip %d/%d correcto", n, len(slides))
    concat = WORK_DIR / "concat.txt"
    concat.write_text("".join(f"file '{path.resolve()}'\n" for path in files), encoding="utf-8")
    destination.parent.mkdir(parents=True, exist_ok=True)
    run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(concat),
         "-c", "copy", "-movflags", "+faststart", str(destination)])
    subtitles.parent.mkdir(parents=True, exist_ok=True)
    subtitles.write_text(build_subtitles([s["narration"] for s in slides], lengths),
                         encoding="utf-8")
    return {"slides": len(slides), "seconds_expected": round(sum(lengths), 2),
            "bytes": destination.stat().st_size, "video": str(destination),
            "subtitles": str(subtitles), "smoke": smoke}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--images-dir", type=Path, default=None)
    parser.add_argument("--voice", default=DEFAULT_VOICE)
    parser.add_argument("--smoke-tone", action="store_true",
                        help="Vídeo de prueba sin llamada a servicios de voz")
    parser.add_argument("--output", type=Path, default=VIDEO_PATH)
    args = parser.parse_args()
    result = render(image_dir=args.images_dir, smoke=args.smoke_tone,
                    voice=args.voice, destination=args.output)
    print(json.dumps(result, indent=2))
