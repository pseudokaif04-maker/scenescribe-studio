"""Optional on-screen text recognition.

Burned-in hooks, titles, and product copy carry a lot of meaning in short-form
video. RapidOCR is light enough to run locally and makes the captions much more
specific when the narration is music-only or hard to hear.
"""

from __future__ import annotations

import logging
import re
import threading
from pathlib import Path
from typing import Callable

from . import config
from .utils import SceneScribeError, clean_inline

LOGGER = logging.getLogger(__name__)
ProgressCallback = Callable[[int, int], None]

_OCR = None
_OCR_LOCK = threading.Lock()
_IMPORT_ERROR: str | None = None


def _get_ocr():
    global _OCR, _IMPORT_ERROR
    if _OCR is not None:
        return _OCR
    with _OCR_LOCK:
        if _OCR is not None:
            return _OCR
        try:
            from rapidocr_onnxruntime import RapidOCR
        except Exception as exc:
            _IMPORT_ERROR = str(exc)
            raise SceneScribeError(
                "On-screen text scanning is not installed, so I used the rest of the video."
            ) from exc
        try:
            _OCR = RapidOCR()
        except Exception as exc:
            LOGGER.exception("RapidOCR failed to initialize")
            raise SceneScribeError("On-screen text scanning could not start.") from exc
        return _OCR


def is_available() -> bool:
    if not config.ENABLE_OCR:
        return False
    try:
        import rapidocr_onnxruntime  # noqa: F401
    except Exception:
        return False
    return True


def _clean_text(value: str) -> str:
    text = re.sub(r"\s+", " ", (value or "").replace("\u00a0", " ")).strip()
    text = text.replace("|", "I")
    text = re.sub(r"\s+([,.;:!?%])", r"\1", text)
    text = re.sub(r"(?<=[.!?])(?=[A-Z0-9])", " ", text)
    text = re.sub(r"\s{2,}", " ", text)
    text = text.strip(" -_=~`^*")
    return clean_inline(text, limit=180)


def _dedupe_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def read_on_screen_text(
    frames: list[dict],
    frame_paths: dict[str, Path],
    on_progress: ProgressCallback | None = None,
) -> dict:
    """OCR sampled frames and return a deduplicated, time-aware list of lines."""
    if not is_available():
        return {
            "available": False,
            "reason": "On-screen text scanning is turned off.",
            "lines": [],
            "text": "",
        }

    try:
        ocr = _get_ocr()
    except SceneScribeError as exc:
        return {"available": False, "reason": str(exc), "lines": [], "text": ""}

    found: list[dict] = []
    with _OCR_LOCK:
        for index, frame in enumerate(frames):
            path = frame_paths.get(frame["filename"])
            if path and path.exists():
                try:
                    result, _ = ocr(str(path))
                except Exception:
                    LOGGER.exception("OCR failed for %s", path.name)
                    result = None
                for entry in result or []:
                    if len(entry) < 3:
                        continue
                    box, raw_text, raw_confidence = entry[0], entry[1], entry[2]
                    try:
                        confidence = float(raw_confidence)
                    except (TypeError, ValueError):
                        continue
                    if confidence < config.OCR_MIN_CONFIDENCE:
                        continue
                    text = _clean_text(str(raw_text))
                    compact = re.sub(r"[^A-Za-z0-9]", "", text)
                    if len(compact) < 2:
                        continue
                    letters = sum(character.isalpha() for character in compact)
                    if letters / max(len(compact), 1) < 0.45:
                        continue
                    # Low-confidence single blobs are usually texture mistaken
                    # for type. Real titles and hooks are bolder than this.
                    if confidence < 0.8 and " " not in text.strip() and len(compact) > 12:
                        continue
                    vowels = sum(character.lower() in "aeiouy" for character in compact)
                    if letters >= 8 and vowels / max(letters, 1) < 0.16:
                        continue
                    center_y = 0.0
                    total_height = 0.0
                    try:
                        ys = [float(point[1]) for point in box]
                        if ys:
                            center_y = (min(ys) + max(ys)) / 2
                            # Bounding boxes are in the frame's pixel space.
                            total_height = max(ys) or 1.0
                    except (TypeError, ValueError, IndexError):
                        pass
                    found.append(
                        {
                            "text": text,
                            "raw_text": str(raw_text).strip(),
                            "confidence": round(confidence, 3),
                            "time": frame["time"],
                            "time_label": frame["time_label"],
                            "_center_y": center_y / max(total_height, 1),
                        }
                    )
            if on_progress:
                on_progress(index + 1, len(frames))

    merged: dict[str, dict] = {}
    for line in found:
        key = _dedupe_key(line["text"])
        if not key:
            continue
        existing = merged.get(key)
        if existing:
            existing["occurrences"] += 1
            if line["confidence"] > existing["confidence"]:
                existing["confidence"] = line["confidence"]
                existing["text"] = line["text"]
        else:
            merged[key] = {
                "text": line["text"],
                "time": line["time"],
                "time_label": line["time_label"],
                "confidence": line["confidence"],
                "occurrences": 1,
                "placement": "lower"
                if line["_center_y"] > 0.62
                else "upper"
                if line["_center_y"] < 0.36
                else "middle",
            }

    lines = sorted(merged.values(), key=lambda line: line["time"])
    return {
        "available": bool(lines),
        "reason": None if lines else "No readable on-screen text was found.",
        "lines": lines,
        "text": " · ".join(line["text"] for line in lines),
    }
