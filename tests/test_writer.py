from core.writer import (
    PLATFORM_OPTIONS,
    build_caption_set,
    caption_set_as_text,
)


def make_analysis(tone: str = "playful") -> dict:
    return {
        "video": {"filename": "FlakeOut_ad_with_voiceover.mp4"},
        "reading": {
            "quote": {
                "text": "POV: your hair is NOT the vibe rn",
                "source": "onscreen",
            },
            "keywords": ["hair", "shine", "FlakeOut"],
        },
        "caption_context": {
            "topic": "beauty",
            "topic_label": "Beauty & care",
            "brand": "FlakeOut",
            "keywords": ["hair", "shine", "FlakeOut"],
            "mood": {"label": "Vivid & playful", "tone": tone},
            "pace": {"key": "fast", "label": "Fast-cut", "average_shot_seconds": 0.9},
            "sound": {"key": "voice", "label": "Voice-led"},
            "palette": [
                {"name": "cyan", "hex": "#16D5E8", "role": "accent"},
                {"name": "coral", "hex": "#F96854", "role": "accent"},
            ],
            "summary": "A fast, neon beauty ad with on-screen copy and a voiceover.",
            "duration": 8.0,
            "has_onscreen": True,
            "has_speech": True,
        },
    }


def test_caption_set_has_six_distinct_directions():
    caption_set = build_caption_set(make_analysis(), tone="playful", platform="instagram")

    assert caption_set["tone"] == "playful"
    assert caption_set["tone_requested"] == "playful"
    assert caption_set["tone_auto"] is False
    assert caption_set["platform"] == "instagram"
    assert len(caption_set["captions"]) == 6
    assert [item["id"] for item in caption_set["captions"]] == [
        "scroll-stopper",
        "story",
        "short",
        "question",
        "quote",
        "manifesto",
    ]
    assert sum(card["recommended"] for card in caption_set["captions"]) == 1
    assert all(card["body"] for card in caption_set["captions"])


def test_auto_tone_uses_the_videos_mood():
    caption_set = build_caption_set(make_analysis("warm"), tone="auto", platform="instagram")

    assert caption_set["tone"] == "warm"
    assert caption_set["tone_auto"] is True
    assert caption_set["tone_requested"] == "auto"


def test_writer_is_deterministic_for_the_same_seed():
    analysis = make_analysis()
    first = build_caption_set(analysis, tone="playful", platform="tiktok", seed=11)
    second = build_caption_set(analysis, tone="playful", platform="tiktok", seed=11)
    third = build_caption_set(analysis, tone="playful", platform="tiktok", seed=12)

    assert first == second
    assert first["captions"] != third["captions"]


def test_platform_limits_and_hashtag_counts_are_respected():
    analysis = make_analysis()
    for platform, settings in PLATFORM_OPTIONS.items():
        caption_set = build_caption_set(
            analysis, tone="bold", platform=platform, seed=3
        )
        assert caption_set["platform"] == platform
        for card in caption_set["captions"]:
            assert len(card["text"]) <= settings["limit"]
        if platform == "x":
            assert max(len(card["hashtags"]) for card in caption_set["captions"]) <= 2


def test_quote_led_caption_uses_video_copy():
    caption_set = build_caption_set(make_analysis(), tone="playful", platform="instagram")
    quote = next(card for card in caption_set["captions"] if card["id"] == "quote")
    assert "POV: your hair is NOT the vibe rn" in quote["body"]


def test_plain_text_export_contains_every_direction():
    caption_set = build_caption_set(make_analysis(), tone="playful", platform="instagram")
    export = caption_set_as_text(caption_set)
    assert "SceneScribe captions" in export
    assert "Instagram / Playful" in export
    for card in caption_set["captions"]:
        assert card["label"] in export
        assert card["text"] in export
