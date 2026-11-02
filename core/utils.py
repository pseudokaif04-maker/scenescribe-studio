"""Small, dependency-free helpers used across the application."""

from __future__ import annotations

import json
import math
import os
import re
import tempfile
import unicodedata
from pathlib import Path
from typing import Any


class SceneScribeError(Exception):
    """An error that is safe and useful to show to the person using the app."""


def format_time(seconds: float | int | None, *, force_hours: bool = False) -> str:
    if seconds is None or not math.isfinite(float(seconds)):
        return "0:00"
    total = max(0, int(round(float(seconds))))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours or force_hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def format_duration(seconds: float | int | None) -> str:
    if seconds is None or not math.isfinite(float(seconds)):
        return "0 sec"
    value = max(0.0, float(seconds))
    if value < 1:
        return f"{max(1, round(value * 10) / 10):g} sec"
    if value < 60:
        return f"{value:.0f} sec" if abs(value - round(value)) < 0.2 else f"{value:.1f} sec"
    return format_time(value)


def format_bytes(size: int | float | None) -> str:
    if not size or size < 0:
        return "0 MB"
    units = ("B", "KB", "MB", "GB")
    value = float(size)
    index = 0
    while value >= 1024 and index < len(units) - 1:
        value /= 1024
        index += 1
    precision = 0 if index <= 1 or value >= 100 else 1
    return f"{value:.{precision}f} {units[index]}"


def slugify(value: str, *, max_length: int = 48) -> str:
    text = unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode()
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return text[:max_length].strip("-") or "video"


def hashtag(value: str) -> str:
    text = unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode()
    text = re.sub(r"[^a-zA-Z0-9]+", "", text)
    return f"#{text.lower()}" if text else ""


def clean_inline(value: str, *, limit: int | None = None) -> str:
    text = re.sub(r"\s+", " ", (value or "").replace("\u00a0", " ")).strip()
    if limit and len(text) > limit:
        text = text[: max(0, limit - 1)].rstrip(" ,;:.") + "…"
    return text


def clean_filename(value: str) -> str:
    base = Path(value or "video").name
    base = re.sub(r"[\x00-\x1f<>:\"/\\|?*]+", " ", base)
    base = re.sub(r"\s+", " ", base).strip(" .")
    return base[:180] or "video"


def truncated_word(text: str, limit: int) -> str:
    """Trim at a word boundary so exports never cut a word in half."""
    if len(text) <= limit:
        return text
    if limit <= 1:
        return "…"
    cut = text[: limit - 1].rsplit(" ", 1)[0].rstrip(" ,;:.-")
    return (cut or text[: limit - 1].rstrip()) + "…"


def write_json_atomic(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            try:
                os.unlink(tmp_name)
            except OSError:
                pass


def read_json(path: Path) -> Any | None:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return None


def spoken_sentence(text: str) -> bool:
    """Loose sanity check for short, usable transcript lines."""
    value = clean_inline(text)
    if len(value) < 12:
        return False
    words = re.findall(r"[A-Za-z']+", value)
    if len(words) < 3:
        return False
    letters = sum(character.isalpha() for character in value)
    return letters / max(1, len(value)) > 0.56


def format_list(items: list[str]) -> str:
    cleaned = [item for item in items if item]
    if not cleaned:
        return ""
    if len(cleaned) == 1:
        return cleaned[0]
    if len(cleaned) == 2:
        return f"{cleaned[0]} and {cleaned[1]}"
    return f"{', '.join(cleaned[:-1])}, and {cleaned[-1]}"
