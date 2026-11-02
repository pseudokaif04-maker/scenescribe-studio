"""Speech-to-text with faster-whisper, kept optional and fault tolerant."""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Callable

from . import config
from .utils import SceneScribeError, clean_inline

LOGGER = logging.getLogger(__name__)
ProgressCallback = Callable[[float], None]

_MODEL = None
_MODEL_LOCK = threading.Lock()


def is_available() -> bool:
    if not config.ENABLE_SPEECH:
        return False
    try:
        import faster_whisper  # noqa: F401
    except Exception:
        return False
    return True


def _load_model():
    global _MODEL
    if _MODEL is not None:
        return _MODEL
    with _MODEL_LOCK:
        if _MODEL is not None:
            return _MODEL
        try:
            from faster_whisper import WhisperModel
        except Exception as exc:  # pragma: no cover - depends on local install
            raise SceneScribeError(
                "Speech recognition is not installed, so this edit was written from the visuals."
            ) from exc

        try:
            _MODEL = WhisperModel(
                config.WHISPER_MODEL,
                device=config.WHISPER_DEVICE,
                compute_type=config.WHISPER_COMPUTE_TYPE,
            )
        except Exception as exc:
            LOGGER.exception("Could not load the Whisper model")
            raise SceneScribeError(
                "The speech model could not be loaded. Check your connection and try again."
            ) from exc
        return _MODEL


def transcribe_audio(
    audio_path: Path,
    duration: float,
    on_progress: ProgressCallback | None = None,
) -> dict:
    """Transcribe an audio file and return clean segments plus confidence signals."""
    if not is_available():
        raise SceneScribeError("Speech recognition is not available.")
    model = _load_model()
    if on_progress:
        on_progress(0.015)

    try:
        with _MODEL_LOCK:
            segment_iterator, info = model.transcribe(
                str(audio_path),
                beam_size=config.WHISPER_BEAM_SIZE,
                vad_filter=True,
                vad_parameters={"min_silence_duration_ms": 350},
                condition_on_previous_text=False,
                task="translate" if config.WHISPER_TRANSLATE else "transcribe",
                word_timestamps=False,
            )
            raw_segments = list(segment_iterator)
    except Exception as exc:
        LOGGER.exception("Whisper transcription failed")
        raise SceneScribeError(
            "I couldn't make out the speech in this video, so I used the visuals instead."
        ) from exc

    segments: list[dict] = []
    for segment in raw_segments:
        text = clean_inline(segment.text)
        if not text:
            continue
        start = max(0.0, float(segment.start))
        end = max(start, float(segment.end))
        if end - start < 0.08:
            continue
        segments.append(
            {
                "start": round(start, 2),
                "end": round(end, 2),
                "text": text,
                "no_speech_probability": round(float(segment.no_speech_prob), 3),
                "avg_logprob": round(float(segment.avg_logprob), 3),
            }
        )
        if on_progress:
            fraction = 0.05 + 0.93 * min(1.0, end / max(duration, 0.1))
            on_progress(min(0.98, fraction))

    if not segments:
        if on_progress:
            on_progress(1.0)
        return {
            "available": False,
            "reason": "No clear speech was found.",
            "segments": [],
            "text": "",
            "word_count": 0,
        }

    text = " ".join(segment["text"] for segment in segments).strip()
    word_count = sum(len(segment["text"].split()) for segment in segments)
    speech_seconds = sum(segment["end"] - segment["start"] for segment in segments)
    wpm = round(word_count / max(speech_seconds / 60, 0.15)) if speech_seconds else 0
    avg_logprob = sum(segment["avg_logprob"] for segment in segments) / len(segments)
    speech_probability = 1 - (
        sum(segment["no_speech_probability"] for segment in segments) / len(segments)
    )
    language_probability = float(getattr(info, "language_probability", 0.0) or 0.0)

    # A short clip often produces a low language-confidence score even when the
    # words are correct, so combine a few signals before calling it usable.
    quote_ready = bool(
        word_count >= 4
        and avg_logprob > -0.7
        and language_probability >= 0.45
        and speech_probability >= 0.35
    )
    if on_progress:
        on_progress(1.0)

    return {
        "available": True,
        "segments": segments,
        "text": text,
        "word_count": word_count,
        "language": str(getattr(info, "language", "") or ""),
        "language_probability": round(language_probability, 3),
        "speech_seconds": round(speech_seconds, 2),
        "words_per_minute": wpm,
        "avg_logprob": round(avg_logprob, 3),
        "quote_ready": quote_ready,
        "reason": None,
    }
