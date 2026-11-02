from pathlib import Path

from core.utils import (
    clean_filename,
    format_bytes,
    format_duration,
    format_time,
    hashtag,
    read_json,
    slugify,
    truncated_word,
    write_json_atomic,
)


def test_time_and_duration_formatting():
    assert format_time(0) == "0:00"
    assert format_time(65) == "1:05"
    assert format_time(3661) == "1:01:01"
    assert format_time(None) == "0:00"
    assert format_duration(8.4) == "8.4 sec"
    assert format_duration(8.0) == "8 sec"
    assert format_duration(72) == "1:12"


def test_byte_formatting():
    assert format_bytes(None) == "0 MB"
    assert format_bytes(0) == "0 MB"
    assert format_bytes(1024) == "1 KB"
    assert format_bytes(5 * 1024 * 1024) == "5.0 MB"


def test_clean_filename_strips_paths_and_reserved_characters():
    assert clean_filename(r"../../private\clip?.mp4") == "clip .mp4"
    assert clean_filename("  ..  ") == "video"
    assert clean_filename("a" * 300).__len__() == 180


def test_slug_and_hashtag_are_ascii_and_safe():
    assert slugify("Café — Morning Edit!") == "cafe-morning-edit"
    assert slugify("!!!") == "video"
    assert hashtag("Beauty & Care") == "#beautycare"
    assert hashtag("!!!") == ""


def test_truncated_word_never_splits_a_word():
    result = truncated_word("the quick brown fox jumps", 15)
    assert result == "the quick…"
    assert not result.endswith("bro…")


def test_json_round_trip(tmp_path: Path):
    target = tmp_path / "nested" / "result.json"
    payload = {"title": "Café", "items": [1, 2, 3]}
    write_json_atomic(target, payload)
    assert read_json(target) == payload
    assert read_json(tmp_path / "missing.json") is None
