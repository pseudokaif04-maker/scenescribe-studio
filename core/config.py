"""Application-wide configuration, all overridable with environment variables."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = ROOT_DIR / "static"
DATA_DIR = Path(os.getenv("SCENESCRIBE_DATA_DIR", ROOT_DIR / "data")).expanduser().resolve()
JOBS_DIR = DATA_DIR / "jobs"
CLIP_RUNS_DIR = DATA_DIR / "clip_runs"

APP_NAME = "SceneScribe Studio"
APP_VERSION = "1.0.0"

# Uploads
MAX_UPLOAD_MB = int(os.getenv("SCENESCRIBE_MAX_UPLOAD_MB", "500"))
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024
ALLOWED_EXTENSIONS = {".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi"}
EXTENSION_BY_MIME = {
    "video/mp4": ".mp4",
    "video/quicktime": ".mov",
    "video/webm": ".webm",
    "video/x-matroska": ".mkv",
    "video/x-msvideo": ".avi",
}

# Analysis
FRAME_COUNT = int(os.getenv("SCENESCRIBE_FRAME_COUNT", "12"))
MAX_ANALYSIS_SECONDS = int(os.getenv("SCENESCRIBE_MAX_ANALYSIS_SECONDS", "1800"))
FFMPEG_TIMEOUT = int(os.getenv("SCENESCRIBE_FFMPEG_TIMEOUT", "300"))
ENABLE_OCR = os.getenv("SCENESCRIBE_ENABLE_OCR", "1").lower() not in {"0", "false", "no"}
OCR_MIN_CONFIDENCE = float(os.getenv("SCENESCRIBE_OCR_MIN_CONFIDENCE", "0.55"))

# Speech
ENABLE_SPEECH = os.getenv("SCENESCRIBE_ENABLE_SPEECH", "1").lower() not in {"0", "false", "no"}
WHISPER_MODEL = os.getenv("SCENESCRIBE_WHISPER_MODEL", "base")
WHISPER_DEVICE = os.getenv("SCENESCRIBE_WHISPER_DEVICE", "cpu")
WHISPER_COMPUTE_TYPE = os.getenv("SCENESCRIBE_WHISPER_COMPUTE_TYPE", "int8")
WHISPER_BEAM_SIZE = int(os.getenv("SCENESCRIBE_WHISPER_BEAM_SIZE", "3"))
WHISPER_TRANSLATE = os.getenv("SCENESCRIBE_WHISPER_TRANSLATE", "0").lower() in {"1", "true", "yes"}

# Worker settings
MAX_WORKERS = int(os.getenv("SCENESCRIBE_MAX_WORKERS", "2"))


def find_binary(name: str, env_var: str) -> str | None:
    """Find ffmpeg/ffprobe, allowing an explicit override."""
    override = os.getenv(env_var)
    if override:
        return override
    found = shutil.which(name)
    if found:
        return found
    if os.name == "nt":
        for candidate in (
            Path("C:/ffmpeg/bin") / f"{name}.exe",
            Path("C:/Program Files/ffmpeg/bin") / f"{name}.exe",
            Path.home() / "ffmpeg/bin" / f"{name}.exe",
        ):
            if candidate.exists():
                return str(candidate)
    return None


FFMPEG = find_binary("ffmpeg", "SCENESCRIBE_FFMPEG")
FFPROBE = find_binary("ffprobe", "SCENESCRIBE_FFPROBE")


def ensure_directories() -> None:
    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    CLIP_RUNS_DIR.mkdir(parents=True, exist_ok=True)
