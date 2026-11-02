from core.semantics import build_analysis

JOB_ID = "0123456789abcdef0123456789abcdef"


def make_inputs() -> tuple[dict, dict, dict, dict]:
    meta = {
        "duration": 8.0,
        "width": 1280,
        "height": 720,
        "orientation": "Landscape",
        "orientation_key": "landscape",
        "fps": 24,
        "has_audio": True,
    }
    visual = {
        "frames": [
            {
                "filename": "frame_01.jpg",
                "time": 0.0,
                "time_label": "0:00",
                "is_transition": False,
                "thumbnail_url": "/unused.jpg",
            },
            {
                "filename": "frame_02.jpg",
                "time": 2.0,
                "time_label": "0:02",
                "is_transition": True,
                "thumbnail_url": "/unused.jpg",
            },
        ],
        "palette": [
            {"name": "cyan", "hex": "#16D5E8", "role": "accent"},
            {"name": "coral", "hex": "#F96854", "role": "accent"},
        ],
        "averages": {"contrast": 0.42},
        "pace": {
            "key": "fast",
            "label": "Fast-cut",
            "transitions": 7,
            "average_shot_seconds": 0.9,
        },
    }
    audio = {
        "available": True,
        "character": "Punchy mix",
        "energy": 0.7,
    }
    transcript = {
        "available": True,
        "text": "FlakeOut keeps my hair smooth and silky every single day.",
        "segments": [
            {
                "start": 0.2,
                "end": 4.5,
                "text": "FlakeOut keeps my hair smooth and silky every single day.",
            }
        ],
        "word_count": 10,
        "words_per_minute": 130,
        "language": "en",
        "language_probability": 0.95,
        "quote_ready": True,
    }
    onscreen = {
        "available": True,
        "text": "POV: your hair is NOT the vibe rn",
        "lines": [
            {
                "text": "POV: your hair is NOT the vibe rn",
                "time": 1.0,
                "time_label": "0:01",
                "confidence": 0.94,
                "occurrences": 2,
                "placement": "middle",
            }
        ],
    }
    return meta, visual, audio, transcript, onscreen


def test_build_analysis_combines_all_signals():
    meta, visual, audio, transcript, onscreen = make_inputs()
    analysis = build_analysis(
        JOB_ID,
        filename="FlakeOut_ad_with_voiceover.mp4",
        meta=meta,
        visual=visual,
        audio=audio,
        transcript=transcript,
        onscreen=onscreen,
    )

    assert analysis["caption_context"]["topic"] == "beauty"
    assert analysis["caption_context"]["brand"] == "FlakeOut"
    assert analysis["reading"]["quote"]["text"] == "POV: your hair is NOT the vibe rn"
    assert "fast" in analysis["reading"]["summary"].lower()
    assert analysis["video"]["poster_url"].startswith("/api/jobs/")
    assert analysis["video"]["video_url"].endswith("/video")
    assert analysis["video"]["download_url"].endswith("?download=1")
    assert analysis["frames"][0]["url"].endswith("/frame_01.jpg")
    assert "_center_y" not in analysis["onscreen"]["lines"][0]
    assert analysis["caption_context"]["has_speech"] is True
    assert analysis["caption_context"]["has_onscreen"] is True


def test_build_analysis_handles_a_silent_camera_clip():
    meta, visual, _, _, _ = make_inputs()
    meta = {**meta, "duration": 4.0, "has_audio": False, "orientation": "Vertical"}
    silent = {
        "available": False,
        "reason": "No audio track.",
        "text": "",
        "segments": [],
        "quote_ready": False,
    }
    no_text = {
        "available": False,
        "reason": "No readable on-screen text was found.",
        "text": "",
        "lines": [],
    }

    analysis = build_analysis(
        JOB_ID,
        filename="IMG_4821.mov",
        meta=meta,
        visual=visual,
        audio={"available": False},
        transcript=silent,
        onscreen=no_text,
    )

    assert analysis["reading"]["quote"] is None
    assert analysis["caption_context"]["has_speech"] is False
    assert analysis["caption_context"]["has_onscreen"] is False
    assert "pure visuals" in analysis["reading"]["summary"]
    assert analysis["transcript"]["quality"] is None
