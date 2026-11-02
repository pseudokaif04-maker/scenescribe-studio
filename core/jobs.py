"""Job state, background work, and small on-disk results for deep links."""

from __future__ import annotations

import logging
import re
import threading
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import config
from .utils import SceneScribeError, read_json, write_json_atomic

LOGGER = logging.getLogger(__name__)
JOB_ID_RE = re.compile(r"^[a-f0-9]{32}$")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Job:
    id: str
    source_file: str
    original_name: str
    tone: str
    platform: str
    status: str = "queued"
    stage: str = "queued"
    progress: int = 0
    message: str = "Queued"
    warnings: list[str] = field(default_factory=list)
    error: str | None = None
    result: dict | None = None
    origin: dict | None = None
    created_at: str = field(default_factory=utc_now)
    completed_at: str | None = None

    @property
    def directory(self) -> Path:
        return config.JOBS_DIR / self.id

    @property
    def source_path(self) -> Path:
        return self.directory / self.source_file

    def public(self) -> dict:
        return {
            "id": self.id,
            "status": self.status,
            "stage": self.stage,
            "progress": self.progress,
            "message": self.message,
            "tone": self.tone,
            "platform": self.platform,
            "original_name": self.original_name,
            "warnings": self.warnings,
            "error": self.error,
            "result": self.result,
            "origin": self.origin,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
        }


class JobStore:
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = threading.RLock()
        self._executor = ThreadPoolExecutor(
            max_workers=max(1, config.MAX_WORKERS),
            thread_name_prefix="scenescribe",
        )

    # ------------------------------------------------------------------ create
    def create(
        self,
        *,
        original_name: str,
        extension: str,
        tone: str,
        platform: str,
        origin: dict | None = None,
    ) -> Job:
        job_id = uuid.uuid4().hex
        source_file = f"source{extension}"
        job = Job(
            id=job_id,
            source_file=source_file,
            original_name=original_name,
            tone=tone,
            platform=platform,
            origin=origin,
        )
        job.directory.mkdir(parents=True, exist_ok=True)
        with self._lock:
            self._jobs[job_id] = job
        return job

    # -------------------------------------------------------------------- work
    def start(self, job: Job) -> None:
        self._executor.submit(self._run, job.id)

    def _run(self, job_id: str) -> None:
        job = self._jobs.get(job_id)
        if not job:
            return
        self._update(
            job_id,
            status="processing",
            stage="queued",
            progress=1,
            message="Warming up the projector",
        )
        try:
            from .pipeline import run_pipeline

            def progress(stage: str, percent: int, message: str) -> None:
                self._update(
                    job_id,
                    status="processing",
                    stage=stage,
                    progress=percent,
                    message=message,
                )

            result, warnings = run_pipeline(
                job_id=job.id,
                source=job.source_path,
                job_dir=job.directory,
                filename=job.original_name,
                tone=job.tone,
                platform=job.platform,
                progress=progress,
            )
            self.complete(job_id, result, warnings)
        except SceneScribeError as exc:
            self.fail(job_id, str(exc))
        except Exception:
            LOGGER.exception("Job %s failed", job_id)
            error_path = job.directory / "error.log"
            try:
                error_path.write_text(traceback.format_exc(), encoding="utf-8")
            except OSError:
                pass
            self.fail(
                job_id,
                "Something went wrong while reading this video. Try another export or a shorter clip.",
            )

    def _update(self, job_id: str, **changes: Any) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return
            for key, value in changes.items():
                if hasattr(job, key):
                    setattr(job, key, value)

    def complete(self, job_id: str, result: dict, warnings: list[str]) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return
            job.status = "complete"
            job.stage = "done"
            job.progress = 100
            job.message = "Your captions are ready"
            job.warnings = warnings
            job.result = result
            job.completed_at = utc_now()
            job.error = None
            persisted = job.public()
        write_json_atomic(job.directory / "result.json", persisted)

    def fail(self, job_id: str, message: str) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return
            job.status = "error"
            job.stage = "error"
            job.progress = 100
            job.message = "Something went wrong"
            job.error = message
            job.completed_at = utc_now()

    # -------------------------------------------------------------------- read
    def get(self, job_id: str) -> dict | None:
        if not JOB_ID_RE.fullmatch(job_id or ""):
            return None
        with self._lock:
            job = self._jobs.get(job_id)
            if job:
                return job.public()
        path = config.JOBS_DIR / job_id / "result.json"
        payload = read_json(path)
        if isinstance(payload, dict) and payload.get("status") == "complete":
            return payload
        return None

    def get_internal(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def analysis_for(self, job_id: str) -> dict | None:
        payload = self.get(job_id)
        if not payload:
            return None
        result = payload.get("result") or {}
        analysis = result.get("analysis")
        return analysis if isinstance(analysis, dict) else None

    def path_for(self, job_id: str) -> Path | None:
        if not JOB_ID_RE.fullmatch(job_id or ""):
            return None
        directory = config.JOBS_DIR / job_id
        if not directory.is_dir():
            return None
        return directory

    def source_for(self, job_id: str) -> Path | None:
        directory = self.path_for(job_id)
        if not directory:
            return None
        for extension in config.ALLOWED_EXTENSIONS:
            candidate = directory / f"source{extension}"
            if candidate.exists() and candidate.is_file():
                return candidate
        return None

    # ------------------------------------------------------------------ remix
    def remix(self, job_id: str, *, tone: str, platform: str, seed: int) -> dict | None:
        if not JOB_ID_RE.fullmatch(job_id or ""):
            return None
        from .writer import build_caption_set

        with self._lock:
            job = self._jobs.get(job_id)
            if job:
                if job.status != "complete" or not job.result:
                    raise RuntimeError("This video is still being read.")
                caption_set = build_caption_set(
                    job.result["analysis"],
                    tone=tone,
                    platform=platform,
                    seed=seed,
                )
                job.result["caption_set"] = caption_set
                job.tone = caption_set["tone"]
                job.platform = platform
                persisted = job.public()
                write_json_atomic(job.directory / "result.json", persisted)
                return caption_set

        path = config.JOBS_DIR / job_id / "result.json"
        payload = read_json(path)
        if not isinstance(payload, dict) or payload.get("status") != "complete":
            return None
        result = payload.get("result") or {}
        analysis = result.get("analysis")
        if not isinstance(analysis, dict):
            return None
        caption_set = build_caption_set(
            analysis,
            tone=tone,
            platform=platform,
            seed=seed,
        )
        result["caption_set"] = caption_set
        payload["result"] = result
        payload["tone"] = caption_set["tone"]
        payload["platform"] = platform
        write_json_atomic(path, payload)
        return caption_set

    def discard(self, job_id: str) -> None:
        with self._lock:
            self._jobs.pop(job_id, None)

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)


STORE = JobStore()
