"""Read videos with ffmpeg and turn a few frames into a small visual profile."""

from __future__ import annotations

import json
import math
import re
import subprocess
import wave
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable

import numpy as np
from PIL import Image, ImageFilter, ImageOps

from . import config
from .utils import SceneScribeError, format_time

ProgressCallback = Callable[[int, int], None]


# Deliberately human colour names rather than hexadecimal soup.
MIME_BY_EXTENSION = {
    ".mp4": "video/mp4",
    ".m4v": "video/mp4",
    ".mov": "video/quicktime",
    ".webm": "video/webm",
    ".mkv": "video/x-matroska",
    ".avi": "video/x-msvideo",
}


def _run(command: list[str], *, timeout: int | None = None) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout or config.FFMPEG_TIMEOUT,
            check=False,
        )
    except FileNotFoundError as exc:
        raise SceneScribeError(
            "ffmpeg was not found. Install ffmpeg or set SCENESCRIBE_FFMPEG to its full path."
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise SceneScribeError("The video took too long to read. Try a shorter clip.") from exc


def _optional_float(value: object, default: float = 0.0) -> float:
    try:
        parsed = float(value)  # type: ignore[arg-type]
        return parsed if math.isfinite(parsed) else default
    except (TypeError, ValueError):
        return default


def _rate(value: object) -> float:
    if not value:
        return 0.0
    text = str(value)
    if "/" in text:
        numerator, _, denominator = text.partition("/")
        try:
            return float(numerator) / max(float(denominator), 1.0)
        except ValueError:
            return 0.0
    return _optional_float(text)


def probe_video(path: Path) -> dict:
    """Return a compact, display-friendly description of the source file."""
    if not config.FFPROBE:
        raise SceneScribeError(
            "ffprobe was not found. Install ffmpeg or set SCENESCRIBE_FFPROBE to its full path."
        )
    result = _run(
        [
            config.FFPROBE,
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(path),
        ],
        timeout=90,
    )
    if result.returncode != 0:
        raise SceneScribeError(
            "I couldn't open this video. Try exporting it as an MP4 or MOV first."
        )
    try:
        payload = json.loads(result.stdout)
    except ValueError as exc:
        raise SceneScribeError("The video's metadata was unreadable.") from exc

    streams = payload.get("streams") or []
    video_stream = next(
        (stream for stream in streams if stream.get("codec_type") == "video"), None
    )
    audio_stream = next(
        (stream for stream in streams if stream.get("codec_type") == "audio"), None
    )
    if not video_stream:
        raise SceneScribeError("That file does not contain a video track.")

    file_format = payload.get("format") or {}
    duration = _optional_float(file_format.get("duration")) or _optional_float(
        video_stream.get("duration")
    )
    if duration <= 0.05:
        raise SceneScribeError("The video appears to be empty or unreadable.")
    if duration > 60 * 60 * 4:
        raise SceneScribeError("That video is over four hours long. Try a shorter excerpt.")

    width = int(video_stream.get("width") or 0)
    height = int(video_stream.get("height") or 0)
    if not width or not height:
        raise SceneScribeError("I couldn't determine the video's dimensions.")

    rotation = 0
    for side_data in video_stream.get("side_data_list") or []:
        if "rotation" in side_data:
            rotation = int(_optional_float(side_data.get("rotation")))
    rotation_tag = (video_stream.get("tags") or {}).get("rotate")
    if rotation_tag:
        rotation = int(_optional_float(rotation_tag))
    if abs(rotation) % 180 == 90:
        width, height = height, width

    ratio = width / max(height, 1)
    if ratio < 0.88:
        orientation = "Vertical"
        framing = f"{ratio:.2f}:1 vertical"
    elif ratio > 1.12:
        orientation = "Landscape"
        framing = f"{ratio:.2f}:1 landscape"
    else:
        orientation = "Square"
        framing = "1:1 square"

    fps = _rate(video_stream.get("avg_frame_rate")) or _rate(video_stream.get("r_frame_rate"))
    if not fps or not math.isfinite(fps) or fps > 240:
        fps = 0.0

    size_bytes = path.stat().st_size if path.exists() else 0
    has_audio = bool(audio_stream)
    codec = str(video_stream.get("codec_name") or "video").upper()
    extension = path.suffix.lower()

    return {
        "duration": round(duration, 3),
        "duration_label": format_time(duration),
        "width": width,
        "height": height,
        "orientation": orientation,
        "orientation_key": orientation.lower(),
        "framing": framing,
        "aspect_ratio": round(ratio, 3),
        "fps": round(fps, 2) if fps else None,
        "has_audio": has_audio,
        "audio_codec": str(audio_stream.get("codec_name") or "").upper()
        if audio_stream
        else None,
        "video_codec": codec,
        "size_bytes": size_bytes,
        "mime_type": MIME_BY_EXTENSION.get(extension, "video/mp4"),
    }


def _frame_count_for(duration: float) -> int:
    # Very short clips still deserve enough frames to see rhythm and colour.
    if duration <= 2.5:
        return 5
    if duration <= 5:
        return 8
    return max(8, min(config.FRAME_COUNT, 14))


def _extract_one_frame(
    source: Path,
    timestamp: float,
    destination: Path,
) -> tuple[bool, str]:
    result = _run(
        [
            config.FFMPEG or "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-ss",
            f"{timestamp:.3f}",
            "-i",
            str(source),
            "-map",
            "0:v:0",
            "-frames:v",
            "1",
            "-vf",
            "scale='min(960,iw)':-2",
            "-q:v",
            "3",
            "-y",
            str(destination),
        ],
        timeout=60,
    )
    if result.returncode != 0 or not destination.exists():
        return False, (result.stderr or "").strip()
    return True, ""


def extract_frames(
    source: Path,
    duration: float,
    output_dir: Path,
    on_progress: ProgressCallback | None = None,
) -> list[dict]:
    """Sample the cut at regular intervals and profile each frame."""
    output_dir.mkdir(parents=True, exist_ok=True)
    count = _frame_count_for(duration)
    timestamps = [max(0.02, duration * (index + 0.5) / count) for index in range(count)]
    timestamps = [min(duration - 0.04, timestamp) for timestamp in timestamps]

    def task(index: int, timestamp: float) -> tuple[int, float, Path, bool, str]:
        destination = output_dir / f"frame_{index + 1:02d}.jpg"
        ok, error = _extract_one_frame(source, timestamp, destination)
        return index, timestamp, destination, ok, error

    extracted: list[tuple[int, float, Path]] = []
    errors: list[str] = []
    # A handful of ffmpeg seeks in parallel is much snappier than one long decode.
    with ThreadPoolExecutor(max_workers=min(4, count)) as pool:
        futures = {
            pool.submit(task, index, timestamp): index
            for index, timestamp in enumerate(timestamps)
        }
        completed = 0
        for future in as_completed(futures):
            index, timestamp, destination, ok, error = future.result()
            completed += 1
            if ok:
                extracted.append((index, timestamp, destination))
            elif error:
                errors.append(error)
            if on_progress:
                on_progress(completed, count)

    if not extracted:
        detail = errors[0].splitlines()[-1] if errors else "No frames could be decoded."
        raise SceneScribeError(f"I couldn't read any frames from this video. {detail}")

    extracted.sort(key=lambda item: item[0])
    frames: list[dict] = []
    previous_small: np.ndarray | None = None
    for position, (_, timestamp, path) in enumerate(extracted):
        features = analyze_frame_image(path, previous_small)
        previous_small = features.pop("_small_image")
        frames.append(
            {
                "index": position + 1,
                "time": round(timestamp, 3),
                "time_label": format_time(timestamp),
                "filename": path.name,
                **features,
            }
        )

    diffs = [frame["difference"] for frame in frames]
    transition_threshold = _transition_threshold(diffs)
    for frame in frames:
        frame["is_transition"] = frame["difference"] >= transition_threshold and frame["difference"] > 0.12
    for position, frame in enumerate(frames):
        frame["beat_index"] = position + 1

    transitions = sum(1 for frame in frames[1:] if frame["is_transition"])
    avg_shot = duration / max(transitions + 1, 1)
    palette = aggregate_palette(frames)

    avg = {
        "brightness": round(float(np.mean([frame["brightness"] for frame in frames])), 3),
        "saturation": round(float(np.mean([frame["saturation"] for frame in frames])), 3),
        "warmth": round(float(np.mean([frame["warmth"] for frame in frames])), 3),
        "contrast": round(float(np.mean([frame["contrast"] for frame in frames])), 3),
        "colorfulness": round(
            float(np.mean([frame["colorfulness"] for frame in frames])), 3
        ),
    }
    visual = {
        "frames": frames,
        "palette": palette,
        "averages": avg,
        "transitions": transitions,
        "average_shot_seconds": round(avg_shot, 2),
        "pace": _pace_for(avg_shot, transitions, duration, len(frames)),
        "visual_difference": round(float(np.mean(diffs[1:])) if len(diffs) > 1 else 0.0, 3),
    }
    return visual


def _transition_threshold(differences: list[float]) -> float:
    usable = [value for value in differences[1:] if value >= 0]
    if not usable:
        return 1.0
    array = np.asarray(usable, dtype=np.float32)
    median = float(np.median(array))
    # A fixed-ish floor behaves better than a purely relative threshold: an
    # edit where every other frame is a cut is fast, not "one big transition".
    return min(0.23, max(0.15, median * 0.45 + 0.08))


def _pace_for(avg_shot: float, transitions: int, duration: float, frame_count: int) -> dict:
    if duration <= 4 or (frame_count <= 6 and transitions >= 2):
        average = min(avg_shot, 1.1)
    else:
        average = avg_shot
    if transitions == 0 and duration < 4:
        average = 1.8
    if average <= 1.15:
        key, label, note = "fast", "Fast-cut", "quick visual rhythm"
    elif average <= 2.6:
        key, label, note = "snappy", "Snappy", "a brisk, edit-led rhythm"
    elif average <= 5.5:
        key, label, note = "steady", "Steady", "room to let each frame land"
    elif average <= 10:
        key, label, note = "slow", "Slow-burn", "a patient, lingering rhythm"
    else:
        key, label, note = "unhurried", "Unhurried", "a quiet, observational rhythm"
    return {
        "key": key,
        "label": label,
        "note": note,
        "average_shot_seconds": round(average, 2),
        "transitions": transitions,
    }


def analyze_frame_image(path: Path, previous_small: np.ndarray | None) -> dict:
    with Image.open(path) as opened:
        image = ImageOps.exif_transpose(opened).convert("RGB")
        width, height = image.size
        # Ignore the extreme edges: letterboxing and UI chrome distort colour reads.
        crop = image.crop(
            (
                int(width * 0.035),
                int(height * 0.035),
                int(width * 0.965),
                int(height * 0.965),
            )
        )
        thumbnail = crop.copy()
        thumbnail.thumbnail((180, 180), Image.Resampling.LANCZOS)
        small = crop.copy()
        small.thumbnail((64, 64), Image.Resampling.BILINEAR)

        dominant, colors = _dominant_colors(crop)
        edge_image = thumbnail.convert("L").filter(ImageFilter.FIND_EDGES)
        detail = float(np.asarray(edge_image, dtype=np.float32).mean() / 255.0)

    array = np.asarray(thumbnail, dtype=np.float32) / 255.0
    small_array = np.asarray(small, dtype=np.float32) / 255.0
    red, green, blue = array[..., 0], array[..., 1], array[..., 2]
    luma = 0.2126 * red + 0.7152 * green + 0.0722 * blue
    maximum = array.max(axis=2)
    minimum = array.min(axis=2)
    saturation_map = np.divide(
        maximum - minimum,
        maximum,
        out=np.zeros_like(maximum),
        where=maximum > 0.001,
    )

    mean_red = float(red.mean())
    mean_blue = float(blue.mean())
    rg = red - green
    yb = 0.5 * (red + green) - blue
    colorfulness = math.sqrt(
        float(rg.std()) ** 2 + float(yb.std()) ** 2
    ) + 0.3 * math.sqrt(float(rg.mean()) ** 2 + float(yb.mean()) ** 2)
    colorfulness = min(1.0, colorfulness / 0.35)

    brightness = float(luma.mean())
    saturation = float(saturation_map.mean())
    warmth = min(1.0, max(0.0, 0.5 + (mean_red - mean_blue) * 0.95))
    contrast = float(luma.std())

    difference = 0.0
    if previous_small is not None and previous_small.shape == small_array.shape:
        difference = float(np.mean(np.abs(small_array - previous_small)))

    return {
        "brightness": round(min(1.0, max(0.0, brightness)), 3),
        "saturation": round(min(1.0, max(0.0, saturation)), 3),
        "warmth": round(warmth, 3),
        "contrast": round(min(1.0, contrast), 3),
        "colorfulness": round(colorfulness, 3),
        "detail": round(min(1.0, detail * 5.5), 3),
        "difference": round(min(1.0, difference * 2.4), 3),
        "dominant": dominant,
        "colors": colors[:5],
        "thumbnail_url": None,
        "_small_image": small_array,
    }


def rgb_to_hsv(rgb: tuple[int, int, int] | list[int]) -> tuple[float, float, float]:
    red, green, blue = (max(0, min(255, int(channel))) / 255.0 for channel in rgb)
    maximum = max(red, green, blue)
    minimum = min(red, green, blue)
    delta = maximum - minimum
    if maximum <= 0.0001:
        saturation = 0.0
    else:
        saturation = delta / maximum
    if delta <= 0.0001:
        hue = 0.0
    elif maximum == red:
        hue = 60.0 * (((green - blue) / delta) % 6)
    elif maximum == green:
        hue = 60.0 * (((blue - red) / delta) + 2)
    else:
        hue = 60.0 * (((red - green) / delta) + 4)
    return (hue % 360.0, saturation, maximum)


def color_name(rgb: tuple[int, int, int] | list[int]) -> str:
    """A readable colour name based on hue, chroma, and light."""
    hue, saturation, value = rgb_to_hsv(tuple(rgb))
    if saturation < 0.13:
        if value > 0.88:
            return "cream"
        if value > 0.64:
            return "greige"
        if value > 0.34:
            return "stone"
        return "charcoal"
    if saturation < 0.3 and value > 0.72:
        return "sand" if 18 <= hue <= 65 else "cream"

    if hue < 12 or hue >= 348:
        if value < 0.48:
            return "cherry"
        return "coral" if saturation > 0.48 else "rose"
    if hue < 28:
        if value > 0.7 and saturation < 0.48:
            return "peach"
        return "coral" if value > 0.58 else "terracotta"
    if hue < 48:
        if saturation < 0.48:
            return "sand"
        return "amber" if value > 0.52 else "terracotta"
    if hue < 68:
        return "gold" if value > 0.55 else "olive"
    if hue < 100:
        return "lime" if value > 0.55 else "moss"
    if hue < 150:
        return "sage" if saturation < 0.52 or value > 0.62 else "forest"
    if hue < 180:
        return "seafoam" if value > 0.52 else "teal"
    if hue < 205:
        return "sky" if value > 0.55 and saturation < 0.55 else "teal"
    if hue < 245:
        if value < 0.36:
            return "navy"
        if saturation > 0.55 and value > 0.48:
            return "electric blue"
        return "cobalt"
    if hue < 285:
        return "lilac" if value > 0.52 else "violet"
    if hue < 330:
        return "rose" if value > 0.55 else "plum"
    return "rose"


def _rgb_saturation(rgb: tuple[int, int, int]) -> float:
    maximum = max(rgb) / 255.0
    minimum = min(rgb) / 255.0
    return 0.0 if maximum <= 0.001 else (maximum - minimum) / maximum


def _accent_colors(image: Image.Image) -> list[dict]:
    """Find the intentional colour accents, not just the largest dark area."""
    sample = image.copy()
    sample.thumbnail((360, 360), Image.Resampling.BILINEAR)
    rgb_array = np.asarray(sample, dtype=np.float32)
    hsv_array = np.asarray(sample.convert("HSV"), dtype=np.float32)
    saturation = hsv_array[..., 1] / 255.0
    value = hsv_array[..., 2] / 255.0
    hue = hsv_array[..., 0] * (360.0 / 255.0)
    mask = (saturation >= 0.42) & (value >= 0.18)
    total_pixels = max(1, rgb_array.shape[0] * rgb_array.shape[1])
    if int(mask.sum()) < 20:
        return []

    hue_bins = np.floor(hue / 30.0).astype(np.int16) % 12
    energy = saturation * (0.55 + value * 0.45)
    results: list[dict] = []
    for hue_index in np.unique(hue_bins[mask]):
        bin_mask = mask & (hue_bins == hue_index)
        count = int(bin_mask.sum())
        if count / total_pixels < 0.003:
            continue
        energetic = bin_mask & (energy >= float(np.percentile(energy[bin_mask], 65)))
        selected = energetic if int(energetic.sum()) >= 8 else bin_mask
        mean_rgb = tuple(int(round(channel)) for channel in rgb_array[selected].mean(axis=0))
        mean_saturation = float(saturation[selected].mean())
        mean_value = float(value[selected].mean())
        score = (count / total_pixels) * (0.32 + mean_saturation * 1.85) * (
            0.84 + mean_value * 0.16
        )
        name = color_name(mean_rgb)
        existing = next((item for item in results if item["name"] == name), None)
        if existing:
            existing["score"] = round(existing["score"] + score, 4)
            continue
        results.append(
            {
                "hex": "#{:02x}{:02x}{:02x}".format(*mean_rgb),
                "name": name,
                "share": round(count / total_pixels, 3),
                "score": round(score, 4),
            }
        )
    results.sort(key=lambda item: item["score"], reverse=True)
    return results[:3]


def _dominant_colors(image: Image.Image) -> tuple[dict, list[dict]]:
    sample = image.copy()
    sample.thumbnail((320, 320), Image.Resampling.LANCZOS)
    quantized = sample.quantize(colors=8, method=Image.Quantize.MEDIANCUT)
    palette = quantized.getpalette() or []
    counts = quantized.getcolors(maxcolors=100000) or []
    colors: list[tuple[int, tuple[int, int, int]]] = []
    for count, palette_index in sorted(counts, reverse=True):
        offset = palette_index * 3
        rgb = tuple(palette[offset : offset + 3])
        if len(rgb) != 3:
            continue
        colors.append((int(count), rgb))  # type: ignore[arg-type]
    if not colors:
        gray = int(ImageOps.grayscale(sample).resize((1, 1)).getpixel((0, 0)))
        colors = [(1, (gray, gray, gray))]

    total = sum(count for count, _ in colors) or 1
    dominant_rgb = max(colors, key=lambda item: item[0])[1]
    dominant = {
        "hex": "#{:02x}{:02x}{:02x}".format(*dominant_rgb),
        "name": color_name(dominant_rgb),
        "share": round(max(count for count, _ in colors) / total, 3),
        "score": 0.0,
    }

    # Large dark areas are stylish but not the whole palette. Weight colour by
    # both presence and chromatic energy so neon hair and coral walls show up.
    scored = []
    seen: set[str] = set()
    for count, rgb in colors:
        share = count / total
        saturation = _rgb_saturation(rgb)
        brightness = max(rgb) / 255.0
        score = share * (0.22 + saturation * 2.75) * (0.86 + brightness * 0.14)
        hex_value = "#{:02x}{:02x}{:02x}".format(*rgb)
        name = color_name(rgb)
        key = f"{name}:{hex_value[:4]}"
        if key in seen:
            continue
        seen.add(key)
        scored.append(
            {
                "hex": hex_value,
                "name": name,
                "share": round(share, 3),
                "score": round(score, 4),
            }
        )

    scored.sort(key=lambda item: item["score"], reverse=True)
    output = scored[:4]
    # Add chromatic accents when the area-based clusters blurred them away.
    for accent in _accent_colors(image):
        if not any(
            math.dist(
                tuple(int(item["hex"][index : index + 2], 16) for index in (1, 3, 5)),
                tuple(int(accent["hex"][index : index + 2], 16) for index in (1, 3, 5)),
            )
            < 42
            for item in output
        ):
            output.append(accent)
    dominant["score"] = next(
        (item["score"] for item in output if item["hex"] == dominant["hex"]),
        round(dominant["share"] * 0.35, 4),
    )
    if not any(item["hex"] == dominant["hex"] for item in output):
        output.append(dominant)
    output.sort(key=lambda item: item["score"], reverse=True)
    return dominant, output[:6]


def aggregate_palette(frames: list[dict], limit: int = 3) -> list[dict]:
    """Merge per-frame colours into a short palette for the UI and the writer."""
    clusters: list[dict] = []
    for frame in frames:
        for rank, color in enumerate(frame.get("colors") or []):
            value = str(color.get("hex", ""))
            match = re.fullmatch(r"#?([0-9a-fA-F]{6})", value)
            if not match:
                continue
            digits = match.group(1)
            rgb = tuple(int(digits[index : index + 2], 16) for index in (0, 2, 4))
            weight = float(color.get("score") or 0) + (0.12 / (rank + 1.0))
            placed = False
            for cluster in clusters:
                center = cluster["_rgb"]
                distance = math.dist(rgb, center)  # type: ignore[arg-type]
                if distance < 48:
                    cluster["_weight"] += weight
                    for index in range(3):
                        cluster["_rgb"][index] = round(
                            cluster["_rgb"][index] * 0.72 + rgb[index] * 0.28
                        )
                    placed = True
                    break
            if not placed:
                clusters.append(
                    {"_rgb": list(rgb), "_weight": weight, "name": color_name(rgb)}
                )

    clusters.sort(key=lambda cluster: cluster["_weight"], reverse=True)

    def cluster_payload(cluster: dict) -> dict:
        rgb = tuple(int(value) for value in cluster["_rgb"])
        name = color_name(rgb)
        saturation = _rgb_saturation(rgb)
        return {
            "hex": "#{:02x}{:02x}{:02x}".format(*rgb),
            "name": name,
            "weight": round(float(cluster["_weight"]), 2),
            "role": "neutral" if saturation < 0.24 else "accent",
        }

    palette: list[dict] = []
    used_names: set[str] = set()

    def add(cluster: dict) -> None:
        item = cluster_payload(cluster)
        if item["name"] in used_names:
            return
        used_names.add(item["name"])
        palette.append(item)

    # Lead with the colours people actually remember, then ground them with the
    # dominant neutral. Dark clothing shouldn't erase neon hair.
    for cluster in clusters:
        if _rgb_saturation(tuple(int(v) for v in cluster["_rgb"])) >= 0.24:
            add(cluster)
        if len(palette) >= max(1, limit - 1):
            break
    for cluster in clusters:
        add(cluster)
        if len(palette) >= limit:
            break
    return palette or [{"hex": "#7d766c", "name": "stone", "weight": 1.0, "role": "neutral"}]


def extract_audio(
    source: Path,
    destination: Path,
    duration: float,
    on_progress: ProgressCallback | None = None,
) -> bool:
    """Extract mono 16 kHz audio. Returns False when there is no usable sound."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    seconds = min(duration, config.MAX_ANALYSIS_SECONDS)
    result = _run(
        [
            config.FFMPEG or "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(source),
            "-map",
            "0:a:0?",
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-c:a",
            "pcm_s16le",
            "-t",
            f"{seconds:.3f}",
            "-y",
            str(destination),
        ]
    )
    if result.returncode != 0 or not destination.exists():
        return False
    if on_progress:
        on_progress(1, 1)
    return True


def read_audio_profile(audio_path: Path) -> dict:
    """Measure loudness and create the little waveform shown in the studio."""
    try:
        with wave.open(str(audio_path), "rb") as handle:
            channels = handle.getnchannels()
            width = handle.getsampwidth()
            sample_rate = handle.getframerate()
            frame_count = handle.getnframes()
            raw = handle.readframes(frame_count)
    except (wave.Error, OSError):
        return {"available": False}

    if width != 2 or not raw or channels != 1:
        return {"available": False}

    samples = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    if samples.size == 0:
        return {"available": False}

    window = max(1, int(sample_rate * 0.5))
    usable = samples[: (samples.size // window) * window]
    if usable.size:
        frames = usable.reshape(-1, window)
        rms = np.sqrt(np.mean(frames * frames, axis=1))
    else:
        rms = np.asarray([float(np.sqrt(np.mean(samples * samples)))])

    db = 20 * np.log10(np.maximum(rms, 1e-6))
    mean_db = float(np.mean(db))
    peak_db = float(np.max(db))
    silence_ratio = float(np.mean(db < -42))
    dynamic_range = float(np.percentile(db, 92) - np.percentile(db, 8))

    bar_count = 56
    edges = np.linspace(0, samples.size, bar_count + 1).astype(int)
    bars = []
    for index in range(bar_count):
        chunk = samples[edges[index] : edges[index + 1]]
        value = float(np.sqrt(np.mean(chunk * chunk))) if chunk.size else 0.0
        bars.append(value)
    bars_array = np.asarray(bars)
    reference = float(np.percentile(bars_array, 94)) if bars_array.size else 1.0
    reference = max(reference, 1e-5)
    normalized = [
        round(min(1.0, max(0.05, float(value / reference) ** 0.74)), 3)
        for value in bars_array
    ]

    if mean_db < -34:
        character = "Soft soundbed"
        character_key = "soft"
    elif dynamic_range > 20:
        character = "Dynamic mix"
        character_key = "dynamic"
    elif peak_db > -4:
        character = "Punchy mix"
        character_key = "punchy"
    else:
        character = "Balanced mix"
        character_key = "balanced"

    return {
        "available": True,
        "waveform": normalized,
        "mean_db": round(mean_db, 1),
        "peak_db": round(peak_db, 1),
        "silence_ratio": round(silence_ratio, 2),
        "dynamic_range": round(dynamic_range, 1),
        "character": character,
        "character_key": character_key,
        "duration": round(samples.size / max(sample_rate, 1), 2),
    }
