"""ClipForge integration: run the local clip engine from SceneScribe.

ClipForge stays the authority for source resolution, highlight selection, cutting,
reframing, and optional speech captions. SceneScribe owns the shared interface and
the social caption writer. This module runs ClipForge as a local subprocess so the
two projects can keep independent Python environments.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import threading
import uuid
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from . import config
from .utils import (
    SceneScribeError,
    clean_filename,
    clean_inline,
    format_duration,
    format_time,
    read_json,
    write_json_atomic,
)

LOGGER = logging.getLogger(__name__)

CLIP_RUN_ID_RE = re.compile(r"^[a-f0-9]{32}$")
ASPECTS = {
    "9:16": "Vertical 9:16",
    "1:1": "Square 1:1",
    "16:9": "Landscape 16:9",
}
ASPECT_ALIASES = {"reels": "9:16", "shorts": "9:16", "vertical": "9:16"}
REFRAMES = {
    "blur": "Blurred fill",
    "crop": "Crop to fill",
    "pad": "Black bars",
}
REFRAME_ALIASES = {"fit": "blur"}
MODES = {"auto", "heatmap", "audio", "hybrid"}
URL_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "music.youtube.com",
    "youtu.be",
    "twitch.tv",
    "www.twitch.tv",
    "m.twitch.tv",
    "clips.twitch.tv",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class ClipForgeTarget:
    home: Path | None
    python: Path | None
    available: bool
    reason: str | None = None

    def public(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "reason": self.reason,
            "home": str(self.home) if self.home else None,
            "max_clips": 10,
            "min_duration": 5,
            "max_duration": 180,
            "aspects": [
                {"value": value, "label": label}
                for value, label in ASPECTS.items()
            ],
            "reframes": [
                {"value": value, "label": label}
                for value, label in REFRAMES.items()
            ],
            "modes": ["auto", "heatmap", "audio", "hybrid"],
        }


def _discover_clipforge() -> ClipForgeTarget:
    configured = os.getenv("SCENESCRIBE_CLIPFORGE_HOME", "").strip()
    if configured:
        candidates = [Path(configured).expanduser()]
    else:
        candidates = [
            config.ROOT_DIR.parent / "clipforge",
            Path.home() / "clipforge",
        ]

    seen: set[Path] = set()
    first_issue: str | None = None
    for raw_home in candidates:
        try:
            home = raw_home.resolve()
        except OSError:
            continue
        if home in seen:
            continue
        seen.add(home)

        package_marker = home / "clipforge" / "cli.py"
        if not package_marker.is_file():
            if configured:
                first_issue = (
                    "SCENESCRIBE_CLIPFORGE_HOME does not point to a ClipForge folder."
                )
            continue

        python_override = os.getenv("SCENESCRIBE_CLIPFORGE_PYTHON", "").strip()
        if python_override:
            python = Path(python_override).expanduser()
            if not python.is_file():
                return ClipForgeTarget(
                    home=home,
                    python=None,
                    available=False,
                    reason=(
                        "SCENESCRIBE_CLIPFORGE_PYTHON does not point to a Python "
                        "executable."
                    ),
                )
        else:
            python_candidates = [
                home / ".venv" / "Scripts" / "python.exe",
                home / ".venv" / "bin" / "python",
                home / "venv" / "Scripts" / "python.exe",
                home / "venv" / "bin" / "python",
            ]
            python = next((item for item in python_candidates if item.is_file()), None)
            if python is None:
                return ClipForgeTarget(
                    home=home,
                    python=None,
                    available=False,
                    reason=(
                        "ClipForge was found, but its virtual environment is "
                        "missing. Run ClipForge's setup.ps1 or set "
                        "SCENESCRIBE_CLIPFORGE_PYTHON."
                    ),
                )

        return ClipForgeTarget(home=home, python=python, available=True)

    if not configured:
        first_issue = (
            "ClipForge was not found beside SceneScribe. Set "
            "SCENESCRIBE_CLIPFORGE_HOME to your ClipForge folder."
        )
    return ClipForgeTarget(
        home=None,
        python=None,
        available=False,
        reason=first_issue or "ClipForge is not available on this machine.",
    )


TARGET = _discover_clipforge()


class ClipForgeBusy(Exception):
    """Raised when another clip run is still using the local engine."""


@dataclass
class ClipRun:
    id: str
    source: str
    source_kind: str
    settings: dict[str, Any]
    run_dir: Path
    output_dir: Path
    status: str = "queued"
    stage: str = "queued"
    progress: int = 0
    message: str = "Queued"
    error: str | None = None
    created_at: str = field(default_factory=utc_now)
    completed_at: str | None = None
    source_info: dict[str, Any] = field(default_factory=dict)
    clips: list[dict[str, Any]] = field(default_factory=list)
    workdir: Path | None = None
    asset_paths: dict[str, dict[str, str]] = field(default_factory=dict)
    log_tail: deque[str] = field(default_factory=lambda: deque(maxlen=240))
    process: Any = field(default=None, repr=False)
    cancel_requested: bool = False

    def to_public(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "status": self.status,
            "stage": self.stage,
            "progress": self.progress,
            "message": self.message,
            "error": self.error,
            "source": self.source,
            "source_kind": self.source_kind,
            "settings": dict(self.settings),
            "source_info": dict(self.source_info),
            "clips": [dict(clip) for clip in self.clips],
            "created_at": self.created_at,
            "completed_at": self.completed_at,
            "log": "\n".join(self.log_tail),
        }

    def to_disk(self) -> dict[str, Any]:
        payload = self.to_public()
        payload["workdir"] = str(self.workdir) if self.workdir else None
        payload["asset_paths"] = self.asset_paths
        return payload


def _safe_int(value: Any, name: str, low: int, high: int) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SceneScribeError(f"{name} must be a whole number.")
    number = int(value)
    if number != value:
        raise SceneScribeError(f"{name} must be a whole number.")
    if number < low or number > high:
        raise SceneScribeError(f"{name} must be between {low} and {high}.")
    return number


def _safe_duration(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SceneScribeError("Clip length must be a number.")
    duration = float(value)
    if duration < 5 or duration > 180:
        raise SceneScribeError("Clip length must be between 5 and 180 seconds.")
    return duration


def validate_source(value: Any) -> tuple[str, str]:
    if not isinstance(value, str) or not value.strip():
        raise SceneScribeError("Paste a YouTube or Twitch link, or a local video path.")
    source = value.strip()
    if len(source) > 500:
        raise SceneScribeError("That source is too long.")
    if "\x00" in source or "\n" in source or "\r" in source:
        raise SceneScribeError("That source does not look right.")
    if source.startswith("-"):
        raise SceneScribeError("That source does not look right.")

    if re.match(r"^[a-z][a-z0-9+.-]*://", source, re.IGNORECASE):
        parsed = urlparse(source)
        if parsed.scheme.lower() not in {"http", "https"}:
            raise SceneScribeError("Use a YouTube or Twitch link.")
        host = (parsed.hostname or "").lower()
        if host not in URL_HOSTS:
            raise SceneScribeError(
                "ClipForge works with YouTube and Twitch links."
            )
        if parsed.username or parsed.password:
            raise SceneScribeError("That link does not look right.")
        return source, "url"

    path = Path(source).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    try:
        path = path.resolve()
    except OSError:
        raise SceneScribeError("That local video path could not be opened.")
    if not path.is_file():
        raise SceneScribeError("That local video does not exist.")
    if path.suffix.lower() not in config.ALLOWED_EXTENSIONS:
        raise SceneScribeError(
            "Local clips must be one of: MP4, MOV, M4V, WEBM, MKV, or AVI."
        )
    return str(path), "local"


def validate_settings(body: dict[str, Any]) -> dict[str, Any]:
    count = _safe_int(body.get("count", 3), "Clip count", 1, 10)
    duration = _safe_duration(body.get("duration", 30))

    aspect = str(body.get("aspect") or "9:16").strip().lower()
    aspect = ASPECT_ALIASES.get(aspect, aspect)
    if aspect not in ASPECTS:
        raise SceneScribeError("That clip shape is not available.")

    reframe = str(body.get("reframe") or "blur").strip().lower()
    reframe = REFRAME_ALIASES.get(reframe, reframe)
    if reframe not in REFRAMES:
        raise SceneScribeError("That framing option is not available.")

    mode = str(body.get("mode") or "auto").strip().lower()
    if mode not in MODES:
        raise SceneScribeError("That clip detection mode is not available.")

    captions = body.get("captions", False)
    if not isinstance(captions, bool):
        raise SceneScribeError("Speech captions must be on or off.")

    hook_raw = body.get("hook", "")
    if hook_raw is None:
        hook_raw = ""
    if not isinstance(hook_raw, str):
        raise SceneScribeError("The hook line must be text.")
    hook = clean_inline(hook_raw, limit=120)
    if "\x00" in hook:
        raise SceneScribeError("The hook line does not look right.")

    return {
        "count": count,
        "duration": duration,
        "aspect": aspect,
        "reframe": reframe,
        "mode": mode,
        "captions": captions,
        "hook": hook,
    }


def _command(run: ClipRun) -> list[str]:
    if TARGET.python is None:
        raise SceneScribeError("ClipForge is not available on this machine.")
    settings = run.settings
    command = [
        str(TARGET.python),
        "-m",
        "clipforge",
        run.source,
        "-n",
        str(settings["count"]),
        "-d",
        f"{settings['duration']:g}",
        "--aspect",
        settings["aspect"],
        "--reframe",
        settings["reframe"],
        "--mode",
        settings["mode"],
        "--out",
        str(run.output_dir),
    ]
    if settings["captions"]:
        command.extend(["--captions", "--whisper-model", config.WHISPER_MODEL])
    if settings["hook"]:
        command.extend(["--hook", settings["hook"]])
    return command


def _safe_child(root: Path, relative: str | None) -> Path | None:
    if not relative:
        return None
    try:
        root = root.resolve()
        candidate = (root / relative).resolve()
        candidate.relative_to(root)
    except (OSError, ValueError):
        return None
    return candidate


def _clip_public(
    run_id: str,
    index: int,
    record: dict[str, Any],
    workdir: Path,
) -> tuple[dict[str, Any], dict[str, str]]:
    relative_file = str(record.get("file") or "")
    relative_thumb = str(record.get("thumbnail") or "")
    video_path = _safe_child(workdir, relative_file)
    thumb_path = _safe_child(workdir, relative_thumb)
    if not video_path or not video_path.is_file():
        raise SceneScribeError("ClipForge produced a clip with a missing file.")

    title = clean_inline(str(record.get("title") or "").strip(), limit=110)
    if not title:
        title = f"Clip {index:02d}"

    clip = {
        "index": index,
        "label": f"Clip {index:02d}",
        "title": title,
        "duration": round(float(record.get("duration") or 0), 3),
        "duration_label": format_duration(record.get("duration")),
        "start": round(float(record.get("start") or 0), 3),
        "end": round(float(record.get("end") or 0), 3),
        "start_label": format_time(record.get("start")),
        "end_label": format_time(record.get("end")),
        "reason": clean_inline(str(record.get("reason") or ""), limit=120),
        "aspect": str(record.get("aspect") or ""),
        "reframe": str(record.get("reframe") or ""),
        "has_thumbnail": bool(thumb_path and thumb_path.is_file()),
        "video_url": f"/api/clip-runs/{run_id}/clips/{index}/video",
        "download_url": f"/api/clip-runs/{run_id}/clips/{index}/video?download=1",
        "thumbnail_url": (
            f"/api/clip-runs/{run_id}/clips/{index}/thumbnail"
            if thumb_path and thumb_path.is_file()
            else None
        ),
        "caption_job_id": None,
    }
    assets = {
        "video": str(video_path.relative_to(workdir)).replace("\\", "/"),
    }
    if thumb_path and thumb_path.is_file():
        assets["thumbnail"] = str(thumb_path.relative_to(workdir)).replace("\\", "/")
    return clip, assets


class ClipRunStore:
    """Track, persist, and execute ClipForge runs for the unified studio."""

    def __init__(self) -> None:
        self._runs: dict[str, ClipRun] = {}
        self._lock = threading.RLock()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="clipforge-run")

    # ------------------------------------------------------------------ create
    def create(self, *, source: str, source_kind: str, settings: dict[str, Any]) -> dict[str, Any]:
        if not TARGET.available:
            raise SceneScribeError(TARGET.reason or "ClipForge is not available.")
        with self._lock:
            if any(run.status in {"queued", "running"} for run in self._runs.values()):
                raise ClipForgeBusy(
                    "ClipForge is already making a set of clips. Wait for it to finish or cancel it."
                )

        run_id = uuid.uuid4().hex
        run_dir = config.CLIP_RUNS_DIR / run_id
        output_dir = run_dir / "output"
        output_dir.mkdir(parents=True, exist_ok=True)
        run = ClipRun(
            id=run_id,
            source=source,
            source_kind=source_kind,
            settings=dict(settings),
            run_dir=run_dir,
            output_dir=output_dir,
            message="Queued for ClipForge",
        )
        with self._lock:
            self._runs[run_id] = run
        self._persist(run)
        self._executor.submit(self._execute, run_id)
        return run.to_public()

    # -------------------------------------------------------------------- read
    def get(self, run_id: str) -> dict[str, Any] | None:
        if not CLIP_RUN_ID_RE.fullmatch(run_id or ""):
            return None
        with self._lock:
            run = self._runs.get(run_id)
            loaded = False
            if run is None:
                run = self._load(run_id)
                if run is None:
                    return None
                self._runs[run_id] = run
                loaded = True

            # A run cannot still be alive after the server process has restarted.
            if loaded and run.status in {"queued", "running"}:
                run.status = "error"
                run.stage = "error"
                run.progress = 100
                run.message = "The clip run was interrupted."
                run.error = (
                    "The studio restarted before ClipForge finished. Start the run again."
                )
                run.completed_at = utc_now()
                self._persist(run)

            return run.to_public()

    def folder_path(self, run_id: str) -> Path | None:
        if not CLIP_RUN_ID_RE.fullmatch(run_id or ""):
            return None
        with self._lock:
            run = self._runs.get(run_id) or self._load(run_id)
            if run is None:
                return None
            path = run.workdir or run.run_dir
            return path if path.is_dir() else None

    def asset_path(self, run_id: str, index: int, kind: str) -> Path | None:
        with self._lock:
            run = self._runs.get(run_id) or self._load(run_id)
            if run is None or not run.workdir:
                return None
            relative = (run.asset_paths.get(str(index)) or {}).get(kind)
            path = _safe_child(run.workdir, relative)
            if path and path.is_file():
                return path
            return None

    def clip_source_path(self, run_id: str, index: int) -> Path | None:
        return self.asset_path(run_id, index, "video")

    # ------------------------------------------------------------------- update
    def attach_caption_job(self, run_id: str, index: int, job_id: str) -> None:
        with self._lock:
            run = self._runs.get(run_id) or self._load(run_id)
            if run is None:
                return
            self._runs[run_id] = run
            for clip in run.clips:
                if int(clip.get("index", 0)) == index:
                    clip["caption_job_id"] = job_id
                    break
            else:
                return
            self._persist(run)

    # ------------------------------------------------------------------- cancel
    def cancel(self, run_id: str) -> bool:
        with self._lock:
            run = self._runs.get(run_id)
            if run is None or run.status not in {"queued", "running"}:
                return False
            run.cancel_requested = True
            process = run.process
            run.message = "Stopping ClipForge"
        if process is not None and process.poll() is None:
            self._kill_tree(process)
        return True

    @staticmethod
    def _kill_tree(process: Any) -> None:
        try:
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                    capture_output=True,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
            else:
                process.terminate()
        except Exception:
            try:
                process.kill()
            except Exception:
                pass

    def shutdown(self) -> None:
        with self._lock:
            active = [run for run in self._runs.values() if run.status in {"queued", "running"}]
        for run in active:
            self.cancel(run.id)
        self._executor.shutdown(wait=False, cancel_futures=True)

    # ---------------------------------------------------------------- run loop
    def _execute(self, run_id: str) -> None:
        with self._lock:
            run = self._runs.get(run_id)
            if run is None:
                return
            if run.cancel_requested:
                run.status = "cancelled"
                run.stage = "cancelled"
                run.progress = 100
                run.message = "Clip run stopped."
                run.completed_at = utc_now()
                self._persist(run)
                return
            run.status = "running"
            run.stage = "source"
            run.progress = 6
            run.message = "Opening the source"
            self._persist(run)
            command = _command(run)

        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUNBUFFERED"] = "1"
        env.setdefault("PYTHONUTF8", "1")
        if TARGET.home:
            env["PYTHONPATH"] = str(TARGET.home) + (
                os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else ""
            )

        popen_kwargs: dict[str, Any] = {}
        if os.name == "nt":
            popen_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

        try:
            process = subprocess.Popen(
                command,
                cwd=str(TARGET.home) if TARGET.home else None,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                env=env,
                **popen_kwargs,
            )
        except OSError as exc:
            self._fail(run_id, f"ClipForge could not start: {exc}")
            return

        with self._lock:
            current = self._runs.get(run_id)
            if current:
                current.process = process
                if current.cancel_requested:
                    self._kill_tree(process)

        assert process.stdout is not None
        for line in process.stdout:
            self._apply_line(run_id, line.rstrip("\n"))
        return_code = process.wait()

        with self._lock:
            run = self._runs.get(run_id)
            if run is None:
                return
            run.process = None
            cancelled = run.cancel_requested

        if cancelled:
            self._mark_cancelled(run_id)
            return
        if return_code != 0:
            self._fail(run_id, self._last_error(run_id))
            return

        try:
            self._complete(run_id)
        except Exception as exc:
            LOGGER.exception("ClipForge finished but its output could not be read")
            self._fail(run_id, str(exc) or "ClipForge finished without readable output.")

    def _apply_line(self, run_id: str, line: str) -> None:
        text = line.strip()
        if not text:
            return
        with self._lock:
            run = self._runs.get(run_id)
            if run is None:
                return
            run.log_tail.append(line)
            old_stage = run.stage

            if text.startswith("Source  :"):
                run.stage, run.progress = "source", 14
                run.message = "Opening the source"
            elif "Downloading" in text or "download" in text.lower():
                run.stage, run.progress = "source", max(run.progress, 20)
                run.message = "Fetching the source"
            elif "Analyzing audio" in text:
                run.stage, run.progress = "moments", 28
                run.message = "Finding the most replayable moments"
            elif "Heatmap" in text or "heatmap" in text:
                run.stage = "moments"
                run.progress = max(run.progress, 24)
            elif text.startswith("Signal :"):
                run.stage, run.progress = "moments", 35
                run.message = "Choosing the best moments"
            elif text.startswith("Clip ") and "/" in text:
                match = re.search(r"Clip\s+(\d+)/(\d+)", text)
                if match:
                    current, total = int(match.group(1)), max(1, int(match.group(2)))
                    run.stage = "render"
                    run.progress = min(94, 40 + round((current - 1) / total * 48))
                    run.message = f"Cutting clip {current} of {total}"
            elif "Transcribing" in text:
                run.stage = "render"
                run.progress = max(run.progress, 68)
                run.message = "Adding speech captions"
            elif text.startswith("Done:"):
                run.stage, run.progress = "package", 97
                run.message = "Packaging the clip deck"
            elif text.startswith("Output:"):
                run.stage, run.progress = "package", 98

            if old_stage != run.stage:
                self._persist(run)

    def _complete(self, run_id: str) -> None:
        with self._lock:
            run = self._runs.get(run_id)
            if run is None:
                return
            output_dir = run.output_dir
            settings = dict(run.settings)

        documents = sorted(
            output_dir.rglob("clips.json"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        if not documents:
            raise SceneScribeError("ClipForge finished without writing a clip deck.")
        document_path = documents[0]
        document = read_json(document_path)
        if not isinstance(document, dict):
            raise SceneScribeError("ClipForge's clip deck could not be read.")
        raw_clips = document.get("clips")
        if not isinstance(raw_clips, list) or not raw_clips:
            raise SceneScribeError("ClipForge did not produce any clips.")

        workdir = document_path.parent
        public_clips: list[dict[str, Any]] = []
        asset_paths: dict[str, dict[str, str]] = {}
        for fallback, record in enumerate(raw_clips, start=1):
            if not isinstance(record, dict):
                continue
            try:
                index = int(record.get("index") or fallback)
            except (TypeError, ValueError):
                index = fallback
            clip, assets = _clip_public(run_id, index, record, workdir)
            public_clips.append(clip)
            asset_paths[str(index)] = assets

        if not public_clips:
            raise SceneScribeError("ClipForge produced an empty clip deck.")
        public_clips.sort(key=lambda item: item["index"])

        source_info = document.get("source")
        if not isinstance(source_info, dict):
            source_info = {}
        source_info.setdefault("title", Path(str(source_info.get("source") or run.source)).stem)
        source_info.setdefault("channel", "ClipForge")
        source_info.setdefault("platform", run.source_kind)
        source_info["duration_label"] = format_duration(source_info.get("duration"))

        with self._lock:
            run = self._runs.get(run_id)
            if run is None:
                return
            run.workdir = workdir
            run.asset_paths = asset_paths
            run.clips = public_clips
            run.source_info = source_info
            run.status = "complete"
            run.stage = "done"
            run.progress = 100
            run.message = (
                f"{len(public_clips)} clip{'s' if len(public_clips) != 1 else ''} ready"
            )
            run.completed_at = utc_now()
            run.error = None
            self._persist(run)

    def _last_error(self, run_id: str) -> str:
        with self._lock:
            run = self._runs.get(run_id)
            lines = [line for line in (run.log_tail if run else []) if line.strip()]
        for line in reversed(lines):
            cleaned = clean_inline(line, limit=360)
            if cleaned.lower().startswith(("error:", "usage:")):
                return cleaned
        if lines:
            return clean_inline(lines[-1], limit=360)
        return "ClipForge stopped before it could make the clips."

    def _mark_cancelled(self, run_id: str) -> None:
        with self._lock:
            run = self._runs.get(run_id)
            if run is None:
                return
            run.status = "cancelled"
            run.stage = "cancelled"
            run.progress = 100
            run.message = "Clip run stopped."
            run.completed_at = utc_now()
            self._persist(run)

    def _fail(self, run_id: str, message: str) -> None:
        with self._lock:
            run = self._runs.get(run_id)
            if run is None:
                return
            run.status = "error"
            run.stage = "error"
            run.progress = 100
            run.message = "ClipForge stopped short."
            run.error = clean_inline(message, limit=600)
            run.completed_at = utc_now()
            self._persist(run)

    # -------------------------------------------------------------------- disk
    def _persist(self, run: ClipRun) -> None:
        try:
            write_json_atomic(run.run_dir / "run.json", run.to_disk())
        except OSError:
            LOGGER.exception("Could not persist ClipForge run %s", run.id)

    def _load(self, run_id: str) -> ClipRun | None:
        if not CLIP_RUN_ID_RE.fullmatch(run_id or ""):
            return None
        run_dir = config.CLIP_RUNS_DIR / run_id
        payload = read_json(run_dir / "run.json")
        if not isinstance(payload, dict):
            return None
        try:
            run_dir_value = Path(str(payload.get("workdir") or "")) if payload.get("workdir") else None
            run = ClipRun(
                id=run_id,
                source=str(payload.get("source") or ""),
                source_kind=str(payload.get("source_kind") or "url"),
                settings=dict(payload.get("settings") or {}),
                run_dir=run_dir,
                output_dir=run_dir / "output",
                status=str(payload.get("status") or "error"),
                stage=str(payload.get("stage") or "error"),
                progress=int(payload.get("progress") or 0),
                message=str(payload.get("message") or ""),
                error=payload.get("error"),
                created_at=str(payload.get("created_at") or utc_now()),
                completed_at=payload.get("completed_at"),
                source_info=dict(payload.get("source_info") or {}),
                clips=list(payload.get("clips") or []),
                workdir=run_dir_value,
                asset_paths=dict(payload.get("asset_paths") or {}),
            )
            log_text = payload.get("log")
            if isinstance(log_text, str):
                for line in log_text.splitlines()[-240:]:
                    run.log_tail.append(line)
            return run
        except (TypeError, ValueError):
            return None


CLIP_STORE = ClipRunStore()


def clipforge_public_status() -> dict[str, Any]:
    return TARGET.public()
