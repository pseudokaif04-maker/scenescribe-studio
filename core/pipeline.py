"""The end-to-end reading of a video and the first set of captions."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from . import config
from .media import (
    extract_audio,
    extract_frames,
    probe_video,
    read_audio_profile,
)
from .semantics import build_analysis
from .transcribe import is_available as speech_is_available
from .transcribe import transcribe_audio
from .utils import (
    SceneScribeError,
    clean_inline,
    format_bytes,
    format_duration,
)
from .vision import read_on_screen_text
from .writer import build_caption_set

LOGGER = logging.getLogger(__name__)
Progress = Callable[[str, int, str], None]

STAGES = (
    "probe",
    "frames",
    "onscreen",
    "audio",
    "speech",
    "read",
    "write",
)


def _display_name(filename: str) -> str:
    stem = Path(filename).stem
    stem = re.sub(r"[_]+", " ", stem)
    stem = re.sub(r"\s+", " ", stem).strip()
    stem = re.sub(r"\b(final|copy|export|render|compressed)\b", "", stem, flags=re.I)
    stem = re.sub(r"\s+", " ", stem).strip(" -_")
    if not stem:
        return "Your video"
    if len(stem) > 72:
        stem = clean_inline(stem, limit=72)
    return stem


def _empty_transcript(reason: str) -> dict:
    return {
        "available": False,
        "reason": reason,
        "segments": [],
        "text": "",
        "word_count": 0,
        "words_per_minute": 0,
        "language": "",
        "language_probability": 0,
        "quote_ready": False,
    }


def run_pipeline(
    *,
    job_id: str,
    source: Path,
    job_dir: Path,
    filename: str,
    tone: str,
    platform: str,
    progress: Progress,
) -> tuple[dict, list[str]]:
    warnings: list[str] = []
    last_percent = 0

    def report(stage: str, percent: int, message: str) -> None:
        nonlocal last_percent
        last_percent = max(last_percent, min(99, int(percent)))
        progress(stage, last_percent, message)

    report("probe", 5, "Opening the cut")
    meta = probe_video(source)

    frames_dir = job_dir / "frames"
    report("frames", 11, "Reading the frames")

    def frame_progress(done: int, total: int) -> None:
        percent = 11 + round(15 * done / max(total, 1))
        report("frames", percent, f"Reading frame {done} of {total}")

    visual = extract_frames(source, meta["duration"], frames_dir, frame_progress)
    frame_paths = {frame["filename"]: frames_dir / frame["filename"] for frame in visual["frames"]}

    report("onscreen", 28, "Catching on-screen text")
    onscreen: dict
    try:
        def ocr_progress(done: int, total: int) -> None:
            percent = 28 + round(17 * done / max(total, 1))
            report("onscreen", percent, "Catching on-screen text")

        onscreen = read_on_screen_text(visual["frames"], frame_paths, ocr_progress)
    except Exception:
        LOGGER.exception("On-screen text scan failed")
        onscreen = {
            "available": False,
            "reason": "On-screen text could not be read.",
            "lines": [],
            "text": "",
        }

    audio_profile: dict = {"available": False}
    transcript = _empty_transcript("No audio track.")
    if meta.get("has_audio"):
        report("audio", 48, "Listening to the audio")
        audio_path = job_dir / "audio.wav"
        try:
            extracted = extract_audio(source, audio_path, meta["duration"])
            if extracted:
                audio_profile = read_audio_profile(audio_path)
            else:
                warnings.append("The audio track was silent or unreadable.")
        except SceneScribeError as exc:
            warnings.append(str(exc))
            audio_profile = {"available": False}

        if audio_profile.get("available"):
            if not config.ENABLE_SPEECH:
                transcript = _empty_transcript("Speech recognition is turned off.")
            elif not speech_is_available():
                transcript = _empty_transcript("Speech recognition is not installed.")
                warnings.append(
                    "Speech recognition is not installed, so this edit was read from the visuals and on-screen text."
                )
            else:
                report("speech", 53, "Finding the words")

                def speech_progress(fraction: float) -> None:
                    percent = 53 + round(31 * max(0.0, min(1.0, fraction)))
                    report("speech", percent, "Finding the words")

                try:
                    transcript = transcribe_audio(
                        audio_path,
                        min(meta["duration"], config.MAX_ANALYSIS_SECONDS),
                        speech_progress,
                    )
                except SceneScribeError as exc:
                    transcript = _empty_transcript(str(exc))
                    warnings.append(str(exc))
                except Exception:
                    LOGGER.exception("Unexpected transcription failure")
                    transcript = _empty_transcript("The speech could not be read.")
                    warnings.append(
                        "The speech was hard to make out, so this edit leans on the visuals."
                    )
        if (
            transcript.get("available")
            and not transcript.get("quote_ready")
            and not transcript.get("reason")
        ):
            warnings.append(
                "The speech was hard to make out, so the on-screen copy and visual mood led the writing."
            )
    else:
        report("audio", 52, "Reading the mood")
        audio_profile = {"available": False}

    if not onscreen.get("available") and not transcript.get("available"):
        warnings.append(
            "With no clear speech or on-screen copy, these captions lean into the visual mood."
        )

    report("read", 86, "Building the mood")
    analysis = build_analysis(
        job_id,
        filename=filename,
        meta=meta,
        visual=visual,
        audio=audio_profile,
        transcript=transcript,
        onscreen=onscreen,
    )
    analysis["video"]["filename"] = filename
    analysis["video"]["display_name"] = _display_name(filename)
    analysis["video"]["size_label"] = format_bytes(meta.get("size_bytes"))
    analysis["video"]["duration_sentence"] = format_duration(meta.get("duration"))
    analysis["video"]["deep_link"] = f"/?job={job_id}"

    report("write", 93, "Writing your captions")
    caption_set = build_caption_set(
        analysis,
        tone=tone,
        platform=platform,
        seed=0,
    )
    caption_set["signals"]["duration_label"] = format_duration(meta.get("duration"))

    result = {
        "analysis": analysis,
        "caption_set": caption_set,
        "warnings": list(dict.fromkeys(warnings)),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    return result, result["warnings"]
