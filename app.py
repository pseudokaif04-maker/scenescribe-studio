"""SceneScribe: a local-first video caption studio.

Run with:
    uvicorn app:app --host 127.0.0.1 --port 8000
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator, Callable

from starlette.applications import Starlette
from starlette.datastructures import UploadFile
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from core import config
from core.clipforge import (
    CLIP_STORE,
    ClipForgeBusy,
    clipforge_public_status,
    validate_settings as validate_clip_settings,
    validate_source as validate_clip_source,
)
from core.jobs import JOB_ID_RE, STORE
from core.media import MIME_BY_EXTENSION
from core.utils import SceneScribeError, clean_filename
from core.vision import is_available as ocr_is_available
from core.transcribe import is_available as speech_is_available
from core.writer import PLATFORM_OPTIONS, TONE_OPTIONS

LOGGER = logging.getLogger(__name__)
FRAME_RE = re.compile(r"^frame_\d{2}\.jpg$")
TONE_ALLOWED = set(TONE_OPTIONS) | {"auto"}
PLATFORM_ALLOWED = set(PLATFORM_OPTIONS)


class UploadTooLarge(Exception):
    pass


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        response.headers.setdefault(
            "Permissions-Policy", "camera=(), microphone=(), geolocation=()"
        )
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; "
            "img-src 'self' data: blob:; "
            "media-src 'self' blob:; "
            "style-src 'self' 'unsafe-inline'; "
            "script-src 'self'; "
            "font-src 'self'; "
            "connect-src 'self'; "
            "frame-ancestors 'none'; "
            "base-uri 'self'; "
            "form-action 'self'",
        )
        return response


@asynccontextmanager
async def lifespan(_: Starlette) -> AsyncIterator[None]:
    config.ensure_directories()
    LOGGER.info("SceneScribe %s starting", config.APP_VERSION)
    try:
        yield
    finally:
        CLIP_STORE.shutdown()
        STORE.shutdown()


async def homepage(request: Request) -> Response:
    index = config.STATIC_DIR / "index.html"
    if not index.exists():
        return Response("SceneScribe's interface has not been built yet.", status_code=503)
    return FileResponse(
        index,
        media_type="text/html; charset=utf-8",
        headers={"Cache-Control": "no-store"},
    )


async def favicon(_: Request) -> Response:
    path = config.STATIC_DIR / "favicon.svg"
    if path.exists():
        return FileResponse(path, media_type="image/svg+xml")
    return Response(status_code=204)


def _tone_options() -> list[dict]:
    options = [
        {
            "value": "auto",
            "label": "Auto (from the edit)",
            "description": "Reads the mood and pacing of the cut, then chooses the tone.",
        }
    ]
    options.extend(
        {
            "value": value,
            "label": data["label"],
            "description": data.get("description", ""),
        }
        for value, data in TONE_OPTIONS.items()
    )
    return options


def _platform_options() -> list[dict]:
    return [
        {
            "value": value,
            "label": data["label"],
            "limit": data["limit"],
        }
        for value, data in PLATFORM_OPTIONS.items()
    ]


async def health(_: Request) -> JSONResponse:
    return JSONResponse(
        {
            "status": "ok" if config.FFMPEG and config.FFPROBE else "degraded",
            "version": config.APP_VERSION,
            "ffmpeg": bool(config.FFMPEG),
            "ffprobe": bool(config.FFPROBE),
            "speech": speech_is_available(),
            "ocr": ocr_is_available(),
            "clipforge": clipforge_public_status(),
            "max_upload_mb": config.MAX_UPLOAD_MB,
            "tones": _tone_options(),
            "platforms": _platform_options(),
        },
        headers={"Cache-Control": "no-store"},
    )


def _extension_for(upload: UploadFile) -> str | None:
    filename = clean_filename(upload.filename or "video")
    extension = Path(filename).suffix.lower()
    if extension in config.ALLOWED_EXTENSIONS:
        return extension
    content_type = (upload.content_type or "").lower().split(";")[0].strip()
    if content_type in config.EXTENSION_BY_MIME:
        return config.EXTENSION_BY_MIME[content_type]
    return None


async def analyze(request: Request) -> Response:
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > config.MAX_UPLOAD_BYTES + (2 * 1024 * 1024):
                return JSONResponse(
                    {"error": f"That file is over the {config.MAX_UPLOAD_MB} MB limit."},
                    status_code=413,
                )
        except ValueError:
            return JSONResponse({"error": "Invalid upload size."}, status_code=400)

    try:
        form = await request.form()
    except Exception:
        LOGGER.exception("Multipart form could not be parsed")
        return JSONResponse(
            {"error": "That upload could not be read. Please try again."}, status_code=400
        )

    upload = form.get("video")
    if not isinstance(upload, UploadFile):
        return JSONResponse({"error": "Choose a video file first."}, status_code=400)

    extension = _extension_for(upload)
    if not extension:
        return JSONResponse(
            {
                "error": "Unsupported file type. Use MP4, MOV, M4V, WEBM, MKV, or AVI."
            },
            status_code=415,
        )

    tone = str(form.get("tone") or "auto").strip().lower()
    platform = str(form.get("platform") or "instagram").strip().lower()
    if tone not in TONE_ALLOWED:
        tone = "auto"
    if platform not in PLATFORM_ALLOWED:
        platform = "instagram"

    filename = clean_filename(upload.filename or f"video{extension}")
    job = STORE.create(
        original_name=filename,
        extension=extension,
        tone=tone,
        platform=platform,
    )
    target = job.source_path
    total = 0
    try:
        with target.open("wb") as handle:
            while True:
                chunk = await upload.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > config.MAX_UPLOAD_BYTES:
                    raise UploadTooLarge
                handle.write(chunk)
        await upload.close()
        if total < 1:
            raise SceneScribeError("That file is empty.")
    except UploadTooLarge:
        _discard_job(job.id, job.directory)
        return JSONResponse(
            {"error": f"That file is over the {config.MAX_UPLOAD_MB} MB limit."},
            status_code=413,
        )
    except SceneScribeError as exc:
        _discard_job(job.id, job.directory)
        return JSONResponse({"error": str(exc)}, status_code=400)
    except Exception:
        LOGGER.exception("Upload could not be saved")
        _discard_job(job.id, job.directory)
        return JSONResponse(
            {"error": "The upload could not be saved. Please try again."}, status_code=500
        )
    finally:
        try:
            await form.close()
        except Exception:
            pass

    STORE.start(job)
    payload = job.public()
    payload["status"] = "queued"
    payload["message"] = "Queued"
    return JSONResponse(payload, status_code=202, headers={"Cache-Control": "no-store"})


def _discard_job(job_id: str, directory: Path) -> None:
    STORE.discard(job_id)
    shutil.rmtree(directory, ignore_errors=True)


async def job_status(request: Request) -> Response:
    job_id = request.path_params["job_id"]
    payload = STORE.get(job_id)
    if not payload:
        return JSONResponse(
            {"error": "That video edit could not be found."},
            status_code=404,
            headers={"Cache-Control": "no-store"},
        )
    return JSONResponse(payload, headers={"Cache-Control": "no-store"})


async def remix(request: Request) -> Response:
    job_id = request.path_params["job_id"]
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Send a JSON body."}, status_code=400)
    if not isinstance(body, dict):
        return JSONResponse({"error": "Send a JSON body."}, status_code=400)

    tone = str(body.get("tone") or "auto").strip().lower()
    platform = str(body.get("platform") or "instagram").strip().lower()
    if tone not in TONE_ALLOWED:
        return JSONResponse({"error": "That tone is not available."}, status_code=400)
    if platform not in PLATFORM_ALLOWED:
        return JSONResponse({"error": "That platform is not available."}, status_code=400)
    try:
        seed = int(body.get("seed") or 0)
    except (TypeError, ValueError):
        return JSONResponse({"error": "The seed must be a number."}, status_code=400)
    seed = max(0, min(seed, 100_000))

    try:
        caption_set = STORE.remix(
            job_id,
            tone=tone,
            platform=platform,
            seed=seed,
        )
    except RuntimeError as exc:
        return JSONResponse({"error": str(exc)}, status_code=409)
    except SceneScribeError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    if not caption_set:
        return JSONResponse(
            {"error": "That video edit could not be found."}, status_code=404
        )
    return JSONResponse(
        {"caption_set": caption_set},
        headers={"Cache-Control": "no-store"},
    )


async def video(request: Request) -> Response:
    job_id = request.path_params["job_id"]
    if not JOB_ID_RE.fullmatch(job_id or ""):
        return Response(status_code=404)
    source = STORE.source_for(job_id)
    if not source or not source.exists():
        return JSONResponse({"error": "Video not found."}, status_code=404)
    payload = STORE.get(job_id) or {}
    result = payload.get("result") or {}
    analysis = result.get("analysis") or {}
    video_info = analysis.get("video") or {}
    display_name = video_info.get("display_name") or Path(payload.get("original_name", "video")).stem
    media_type = MIME_BY_EXTENSION.get(source.suffix.lower(), "video/mp4")
    headers = {"Cache-Control": "private, max-age=3600"}
    download = request.query_params.get("download") in {"1", "true", "yes"}

    if download:
        safe_name = clean_filename(f"{display_name}{source.suffix.lower()}")
        return FileResponse(
            source,
            media_type=media_type,
            filename=safe_name,
            content_disposition_type="attachment",
            headers=headers,
        )
    return FileResponse(source, media_type=media_type, headers=headers)


async def frame(request: Request) -> Response:
    job_id = request.path_params["job_id"]
    filename = request.path_params["filename"]
    if not JOB_ID_RE.fullmatch(job_id or "") or not FRAME_RE.fullmatch(filename or ""):
        return Response(status_code=404)
    directory = STORE.path_for(job_id)
    if not directory:
        return Response(status_code=404)
    path = directory / "frames" / filename
    if not path.exists() or not path.is_file():
        return Response(status_code=404)
    return FileResponse(
        path,
        media_type="image/jpeg",
        headers={"Cache-Control": "private, max-age=86400"},
    )


# ----------------------------------------------------------------- ClipForge
def _clip_error(message: str, status_code: int) -> JSONResponse:
    return JSONResponse(
        {"error": message},
        status_code=status_code,
        headers={"Cache-Control": "no-store"},
    )


def _find_clip(payload: dict, index: int) -> dict | None:
    for clip in payload.get("clips") or []:
        try:
            if int(clip.get("index")) == index:
                return clip
        except (TypeError, ValueError):
            continue
    return None


async def start_clip_run(request: Request) -> Response:
    if not clipforge_public_status()["available"]:
        return _clip_error(
            clipforge_public_status()["reason"]
            or "ClipForge is not available on this machine.",
            503,
        )
    try:
        body = await request.json()
    except Exception:
        return _clip_error("Send a JSON body.", 400)
    if not isinstance(body, dict):
        return _clip_error("Send a JSON body.", 400)

    try:
        source, source_kind = validate_clip_source(body.get("source"))
        settings = validate_clip_settings(body)
        payload = CLIP_STORE.create(
            source=source,
            source_kind=source_kind,
            settings=settings,
        )
    except ClipForgeBusy as exc:
        return _clip_error(str(exc), 409)
    except SceneScribeError as exc:
        return _clip_error(str(exc), 400)
    except OSError:
        LOGGER.exception("Clip run could not be created")
        return _clip_error("The clip run could not be started. Please try again.", 500)
    return JSONResponse(
        payload,
        status_code=202,
        headers={"Cache-Control": "no-store"},
    )


async def clip_run_status(request: Request) -> Response:
    run_id = request.path_params["run_id"]
    payload = CLIP_STORE.get(run_id)
    if not payload:
        return _clip_error("That clip run could not be found.", 404)
    return JSONResponse(payload, headers={"Cache-Control": "no-store"})


async def cancel_clip_run(request: Request) -> Response:
    run_id = request.path_params["run_id"]
    payload = CLIP_STORE.get(run_id)
    if not payload:
        return _clip_error("That clip run could not be found.", 404)
    if not CLIP_STORE.cancel(run_id):
        return _clip_error("That clip run has already finished.", 409)
    return JSONResponse(
        {"cancelled": True, "run": CLIP_STORE.get(run_id)},
        headers={"Cache-Control": "no-store"},
    )


async def open_clip_folder(request: Request) -> Response:
    run_id = request.path_params["run_id"]
    folder = CLIP_STORE.folder_path(run_id)
    if not folder:
        return _clip_error("That clip run could not be found.", 404)
    try:
        if os.name == "nt":
            os.startfile(str(folder))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(folder)])
        else:
            subprocess.Popen(["xdg-open", str(folder)])
    except OSError:
        LOGGER.exception("Clip folder could not be opened")
        return _clip_error("The output folder could not be opened.", 500)
    return JSONResponse({"opened": True}, headers={"Cache-Control": "no-store"})


async def clip_asset(request: Request) -> Response:
    run_id = request.path_params["run_id"]
    kind = request.path_params["kind"]
    try:
        index = int(request.path_params["index"])
    except (TypeError, ValueError):
        return Response(status_code=404)
    path = CLIP_STORE.asset_path(run_id, index, kind)
    if not path:
        return Response(status_code=404)
    payload = CLIP_STORE.get(run_id) or {}
    clip = _find_clip(payload, index) or {}
    media_type = (
        "image/jpeg"
        if kind == "thumbnail"
        else MIME_BY_EXTENSION.get(path.suffix.lower(), "video/mp4")
    )
    download = request.query_params.get("download") in {"1", "true", "yes"}
    headers = {
        "Cache-Control": (
            "private, max-age=86400"
            if kind == "thumbnail"
            else "private, max-age=3600"
        )
    }
    if download:
        safe_name = clean_filename(
            f"{clip.get('label') or f'clip_{index:02d}'}{path.suffix.lower()}"
        )
        return FileResponse(
            path,
            media_type=media_type,
            filename=safe_name,
            content_disposition_type="attachment",
            headers=headers,
        )
    return FileResponse(path, media_type=media_type, headers=headers)


async def clip_caption(request: Request) -> Response:
    run_id = request.path_params["run_id"]
    try:
        index = int(request.path_params["index"])
    except (TypeError, ValueError):
        return _clip_error("That clip could not be found.", 404)
    payload = CLIP_STORE.get(run_id)
    if not payload:
        return _clip_error("That clip run could not be found.", 404)
    if payload.get("status") != "complete":
        return _clip_error("Those clips are still being made.", 409)
    clip = _find_clip(payload, index)
    if not clip:
        return _clip_error("That clip could not be found.", 404)

    tone = "auto"
    platform = "instagram"
    try:
        body = await request.json()
    except Exception:
        body = None
    if isinstance(body, dict):
        tone = str(body.get("tone") or "auto").strip().lower()
        platform = str(body.get("platform") or "instagram").strip().lower()
        if tone not in TONE_ALLOWED:
            return _clip_error("That tone is not available.", 400)
        if platform not in PLATFORM_ALLOWED:
            return _clip_error("That platform is not available.", 400)

    existing_id = clip.get("caption_job_id")
    if isinstance(existing_id, str) and JOB_ID_RE.fullmatch(existing_id):
        existing = STORE.get(existing_id)
        if existing and existing.get("status") != "error":
            return JSONResponse(
                existing,
                status_code=200 if existing.get("status") == "complete" else 202,
                headers={"Cache-Control": "no-store"},
            )

    source = CLIP_STORE.clip_source_path(run_id, index)
    if not source or not source.is_file():
        return _clip_error("That clip's video file could not be found.", 404)

    label = str(clip.get("label") or f"clip_{index:02d}")
    job = STORE.create(
        original_name=clean_filename(f"{label}{source.suffix.lower()}"),
        extension=source.suffix.lower(),
        tone=tone,
        platform=platform,
        origin={
            "kind": "clipforge",
            "run_id": run_id,
            "clip_index": index,
            "label": label,
        },
    )
    try:
        try:
            os.link(source, job.source_path)
        except OSError:
            shutil.copy2(source, job.source_path)
    except OSError:
        LOGGER.exception("Clip could not be linked into a caption job")
        _discard_job(job.id, job.directory)
        return _clip_error("That clip could not be opened for captions.", 500)

    STORE.start(job)
    CLIP_STORE.attach_caption_job(run_id, index, job.id)
    result = job.public()
    result["status"] = "queued"
    result["message"] = "Queued"
    return JSONResponse(
        result,
        status_code=202,
        headers={"Cache-Control": "no-store"},
    )


async def not_found(request: Request, exc: Exception) -> Response:
    if request.url.path.startswith("/api/"):
        return JSONResponse({"error": "Not found."}, status_code=404)
    return Response("Not found.", status_code=404)


routes = [
    Route("/", homepage),
    Route("/favicon.svg", favicon),
    Route("/api/health", health),
    Route("/api/analyze", analyze, methods=["POST"]),
    Route("/api/jobs/{job_id}", job_status),
    Route("/api/jobs/{job_id}/remix", remix, methods=["POST"]),
    Route("/api/jobs/{job_id}/video", video),
    Route("/api/jobs/{job_id}/frames/{filename}", frame),
    Route("/api/clip-runs", start_clip_run, methods=["POST"]),
    Route("/api/clip-runs/{run_id}", clip_run_status),
    Route("/api/clip-runs/{run_id}/cancel", cancel_clip_run, methods=["POST"]),
    Route("/api/clip-runs/{run_id}/open-folder", open_clip_folder, methods=["POST"]),
    Route(
        "/api/clip-runs/{run_id}/clips/{index}/caption",
        clip_caption,
        methods=["POST"],
    ),
    Route("/api/clip-runs/{run_id}/clips/{index}/{kind}", clip_asset),
    Mount("/static", app=StaticFiles(directory=str(config.STATIC_DIR)), name="static"),
]

middleware = [Middleware(SecurityHeadersMiddleware)]
app = Starlette(
    debug=False,
    routes=routes,
    middleware=middleware,
    exception_handlers={404: not_found},
    lifespan=lifespan,
)


if __name__ == "__main__":  # pragma: no cover
    import uvicorn

    logging.basicConfig(level=logging.INFO)
    config.ensure_directories()
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=False)
