"""Turn visual, audio, speech, and OCR measurements into a useful creative read."""

from __future__ import annotations

import math
import re
from collections import Counter
from pathlib import Path
from typing import Iterable

from .utils import clean_inline, format_list, format_time, spoken_sentence

TOPIC_RULES: tuple[dict, ...] = (
    {
        "key": "beauty",
        "label": "Beauty & care",
        "terms": (
            "beauty",
            "hair",
            "haircare",
            "hair care",
            "hairtok",
            "skin",
            "skincare",
            "glow",
            "makeup",
            "shampoo",
            "conditioner",
            "dandruff",
            "shine",
            "silky",
            "smooth",
            "salon",
            "lashes",
            "fragrance",
            "perfume",
            "self care",
            "selfcare",
            "routine",
            "glow up",
            "glowup",
            "serum",
            "moisture",
        ),
    },
    {
        "key": "fashion",
        "label": "Fashion & style",
        "terms": (
            "fashion",
            "outfit",
            "style",
            "styled",
            "lookbook",
            "collection",
            "runway",
            "jewelry",
            "jewellery",
            "dress",
            "sneaker",
            "wardrobe",
            "vintage",
            "couture",
            "accessory",
            "wear",
        ),
    },
    {
        "key": "food",
        "label": "Food & drink",
        "terms": (
            "food",
            "recipe",
            "cooking",
            "cook",
            "coffee",
            "cafe",
            "restaurant",
            "taste",
            "flavor",
            "flavour",
            "eat",
            "eating",
            "meal",
            "dessert",
            "bake",
            "baking",
            "kitchen",
            "drink",
            "cocktail",
            "breakfast",
            "brunch",
            "delicious",
            "chef",
        ),
    },
    {
        "key": "travel",
        "label": "Travel & places",
        "terms": (
            "travel",
            "trip",
            "journey",
            "explore",
            "destination",
            "beach",
            "mountain",
            "adventure",
            "wander",
            "wanderlust",
            "roadtrip",
            "road trip",
            "hotel",
            "vacation",
            "holiday",
            "passport",
            "city",
            "island",
            "sunset",
            "sunrise",
        ),
    },
    {
        "key": "fitness",
        "label": "Fitness & movement",
        "terms": (
            "fitness",
            "workout",
            "gym",
            "training",
            "training",
            "run",
            "running",
            "strength",
            "sweat",
            "yoga",
            "pilates",
            "movement",
            "exercise",
            "athlete",
            "wellness",
            "progress",
        ),
    },
    {
        "key": "nature",
        "label": "Nature & outdoors",
        "terms": (
            "nature",
            "forest",
            "ocean",
            "sea",
            "sky",
            "tree",
            "garden",
            "hike",
            "hiking",
            "trail",
            "outdoor",
            "wild",
            "landscape",
            "flowers",
            "mountain",
            "lake",
            "camping",
        ),
    },
    {
        "key": "tech",
        "label": "Tech & product",
        "terms": (
            "tech",
            "technology",
            "artificial intelligence",
            " ai ",
            "app",
            "code",
            "coding",
            "software",
            "product",
            "startup",
            "design",
            "build",
            "gadget",
            "robot",
            "future",
            "digital",
            "developer",
            "launch",
            "saas",
        ),
    },
    {
        "key": "music",
        "label": "Music & performance",
        "terms": (
            "music",
            "song",
            "beat",
            "remix",
            "dance",
            "dancing",
            "singer",
            "album",
            "track",
            "concert",
            "studio",
            "audio",
            "melody",
            "performance",
            "artist",
        ),
    },
    {
        "key": "gaming",
        "label": "Gaming & play",
        "terms": (
            "gaming",
            "game",
            "gamer",
            "gameplay",
            "player",
            "stream",
            "streamer",
            "esports",
            "console",
            "playstation",
            "xbox",
            "nintendo",
            "level up",
        ),
    },
    {
        "key": "business",
        "label": "Business & creative work",
        "terms": (
            "business",
            "brand",
            "founder",
            "startup",
            "team",
            "strategy",
            "marketing",
            "agency",
            "entrepreneur",
            "office",
            "leadership",
            "creative",
            "campaign",
            "client",
            "workshop",
            "process",
        ),
    },
    {
        "key": "home",
        "label": "Home & interiors",
        "terms": (
            "home",
            "interior",
            "decor",
            "apartment",
            "house",
            "renovation",
            "cozy",
            "cosy",
            "furniture",
            "room",
            "space",
            "bedroom",
            "living room",
        ),
    },
    {
        "key": "pets",
        "label": "Pets & animals",
        "terms": (
            "dog",
            "dogs",
            "cat",
            "cats",
            "puppy",
            "kitten",
            "pet",
            "animal",
            "rescue",
            "fur",
            "paw",
        ),
    },
    {
        "key": "art",
        "label": "Art & film",
        "terms": (
            "art",
            "artist",
            "painting",
            "gallery",
            "illustration",
            "sketch",
            "film",
            "filmmaking",
            "photography",
            "photo",
            "camera",
            "creative direction",
            "exhibition",
        ),
    },
    {
        "key": "lifestyle",
        "label": "Lifestyle & everyday",
        "terms": (
            "life",
            "lifestyle",
            "moment",
            "moments",
            "everyday",
            "aesthetic",
            "slow",
            "morning",
            "evening",
            "day",
            "living",
            "happy",
            "joy",
            "simple",
            "ritual",
        ),
    },
)

STOPWORDS = {
    "about",
    "after",
    "again",
    "against",
    "all",
    "almost",
    "along",
    "also",
    "always",
    "and",
    "another",
    "any",
    "are",
    "around",
    "because",
    "been",
    "before",
    "being",
    "best",
    "better",
    "between",
    "both",
    "but",
    "can",
    "could",
    "day",
    "did",
    "does",
    "doing",
    "don't",
    "dont",
    "down",
    "each",
    "even",
    "ever",
    "every",
    "for",
    "from",
    "get",
    "gets",
    "getting",
    "go",
    "going",
    "gone",
    "good",
    "got",
    "had",
    "has",
    "have",
    "having",
    "he",
    "her",
    "here",
    "hers",
    "him",
    "his",
    "how",
    "i",
    "if",
    "in",
    "into",
    "is",
    "it",
    "its",
    "just",
    "know",
    "let",
    "like",
    "look",
    "looking",
    "made",
    "make",
    "makes",
    "many",
    "more",
    "most",
    "much",
    "my",
    "need",
    "not",
    "now",
    "of",
    "off",
    "on",
    "once",
    "one",
    "only",
    "or",
    "other",
    "our",
    "out",
    "over",
    "own",
    "put",
    "really",
    "right",
    "rn",
    "said",
    "same",
    "say",
    "says",
    "see",
    "she",
    "should",
    "so",
    "some",
    "something",
    "still",
    "such",
    "take",
    "than",
    "that",
    "the",
    "their",
    "them",
    "then",
    "there",
    "these",
    "they",
    "thing",
    "things",
    "think",
    "this",
    "those",
    "through",
    "time",
    "to",
    "too",
    "up",
    "us",
    "use",
    "very",
    "want",
    "was",
    "way",
    "we",
    "well",
    "were",
    "what",
    "when",
    "where",
    "which",
    "while",
    "who",
    "why",
    "will",
    "with",
    "would",
    "you",
    "your",
    "yourself",
    "video",
    "clip",
    "reel",
    "reels",
    "ad",
    "ads",
    "promo",
    "final",
    "copy",
    "draft",
    "edit",
    "edited",
    "render",
    "rendered",
    "export",
    "version",
    "voiceover",
    "voice",
    "over",
    "sound",
    "audio",
    "music",
    "footage",
    "raw",
    "test",
    "v1",
    "v2",
    "mp4",
    "mov",
    "webm",
    "1080p",
    "720p",
    "4k",
    "follow",
    "like",
    "share",
    "watch",
    "link",
    "bio",
    "comment",
    "subscribe",
    "shop",
    "buy",
    "pov",
}

BRAND_STOPWORDS = {
    "POV",
    "NOT",
    "THE",
    "AND",
    "FOR",
    "LINK",
    "BIO",
    "SMOOTH",
    "SILKY",
    "GLOW",
    "NEW",
    "NOW",
    "ALL",
    "YOU",
    "YOUR",
    "THIS",
    "THAT",
    "WITH",
    "FROM",
    "WATCH",
    "FOLLOW",
    "SHOP",
    "BUY",
    "USA",
    "HD",
    "UHD",
    "MP4",
}

MOODS = {
    "vivid": {
        "label": "Vivid & playful",
        "description": "Saturated colour and a lively rhythm give this edit a bright, direct personality.",
        "tone": "playful",
    },
    "warm": {
        "label": "Warm & golden",
        "description": "Sun-warmed colour and an easy pace make this feel inviting and quietly cinematic.",
        "tone": "warm",
    },
    "moody": {
        "label": "Moody & cinematic",
        "description": "Low light and deep contrast give the frames a considered, atmospheric pull.",
        "tone": "cinematic",
    },
    "cool": {
        "label": "Cool & composed",
        "description": "Clean, cool tones keep the edit calm, modern, and lightly editorial.",
        "tone": "minimal",
    },
    "minimal": {
        "label": "Soft & minimal",
        "description": "Muted colour and uncluttered frames leave plenty of room for the idea.",
        "tone": "minimal",
    },
    "cinematic": {
        "label": "Cinematic & considered",
        "description": "Balanced colour, intentional framing, and a steady edit hold the mood together.",
        "tone": "cinematic",
    },
}


def _normalize(value: str) -> str:
    return f" {re.sub(r'[^a-z0-9]+', ' ', (value or '').lower()).strip()} "


def _term_count(term: str, text: str) -> int:
    normalized_term = re.sub(r"[^a-z0-9 ]+", " ", term.lower()).strip()
    if not normalized_term:
        return 0
    if " " in normalized_term:
        return len(re.findall(rf"\b{re.escape(normalized_term)}\b", text))
    return len(re.findall(rf"\b{re.escape(normalized_term)}(?:s|es|ing|ed)?\b", text))


def _score_topics(sources: dict[str, str]) -> tuple[dict, list[str]]:
    weights = {"filename": 1.8, "onscreen": 1.35, "transcript": 1.0}
    scored: list[tuple[float, dict, list[str]]] = []
    for topic in TOPIC_RULES:
        score = 0.0
        matches: list[str] = []
        for source, text in sources.items():
            normalized = _normalize(text)
            for term in topic["terms"]:
                count = _term_count(term.strip(), normalized)
                if count:
                    score += count * weights.get(source, 1.0)
                    if term not in matches:
                        matches.append(term.strip())
        scored.append((score, topic, matches))
    scored.sort(key=lambda item: item[0], reverse=True)
    best_score, best_topic, best_matches = scored[0]
    if best_score < 0.95:
        fallback = next(topic for topic in TOPIC_RULES if topic["key"] == "lifestyle")
        return fallback, []
    return best_topic, best_matches


def _brand_candidates(
    filename: str, onscreen_lines: Iterable[dict]
) -> tuple[str | None, int]:
    counts: Counter[str] = Counter()
    display: dict[str, str] = {}

    def add(candidate: str, weight: int) -> None:
        candidate = candidate.strip(" .,:;!?~-_")
        if len(candidate) < 3:
            return
        if candidate.upper() in BRAND_STOPWORDS:
            return
        if candidate.lower() in STOPWORDS:
            return
        key = candidate.lower()
        counts[key] += weight
        # Keep the best-looking original casing.
        current = display.get(key, "")
        if len(candidate) > len(current) or (
            candidate != candidate.lower() and current == current.lower()
        ):
            display[key] = candidate

    camel_case = re.compile(r"\b[A-Z][a-z0-9]+(?:[A-Z][a-z0-9]+)+\b")
    all_caps = re.compile(r"\b[A-Z][A-Z0-9]{2,}\b")
    for line in onscreen_lines:
        text = str(line.get("text") or "")
        occurrences = max(1, int(line.get("occurrences") or 1))
        for pattern in (camel_case, all_caps):
            for candidate in pattern.findall(text):
                add(candidate, occurrences)

    stem = Path(filename or "").stem
    for raw_token in re.split(r"[\s._-]+", stem):
        if not raw_token or raw_token.lower() in STOPWORDS:
            continue
        if camel_case.fullmatch(raw_token) or all_caps.fullmatch(raw_token):
            add(raw_token, 3)
        # A familiar CamelCase brand survives lowercasing poorly; also compare
        # OCR candidates against a loose filename token.
        for existing in list(counts):
            if existing == raw_token.lower() or raw_token.lower().endswith(existing):
                counts[existing] += 2

    if not counts:
        return None, 0
    name, score = counts.most_common(1)[0]
    if score < 3:
        return None, 0
    return display.get(name, name.title()), score


def _keywords(
    *,
    filename: str,
    transcript: dict,
    onscreen: dict,
    brand: str | None,
    matched_topic_terms: list[str],
) -> list[str]:
    counter: Counter[str] = Counter()
    sources: list[tuple[str, float]] = [
        (onscreen.get("text", ""), 1.35),
        (Path(filename or "").stem.replace("_", " ").replace("-", " "), 0.9),
    ]
    # If the speech model itself isn't confident, its words are more likely to
    # pollute the hashtags than improve them.
    if transcript.get("quote_ready"):
        sources.append((transcript.get("text", ""), 1.0))
    for text, weight in sources:
        for raw in re.findall(r"[A-Za-z][A-Za-z0-9'’+-]{2,}", text or ""):
            word = raw.lower().strip("'’-+")
            if len(word) < 3 or word in STOPWORDS or word.isdigit():
                continue
            counter[word] += weight

    if brand:
        counter[brand.lower()] += 4.0
    for term in matched_topic_terms:
        for token in re.findall(r"[a-z0-9]+", term.lower()):
            if len(token) >= 3 and token not in STOPWORDS:
                counter[token] += 1.7

    ordered = sorted(
        counter.items(),
        key=lambda item: (item[1], len(item[0])),
        reverse=True,
    )
    output: list[str] = []
    seen_stems: set[str] = set()
    for word, _ in ordered:
        stem = word[: min(6, len(word))]
        if stem in seen_stems:
            continue
        seen_stems.add(stem)
        output.append(word)
        if len(output) >= 7:
            break

    if brand:
        brand_lower = brand.lower()
        if brand_lower not in output:
            output.insert(0, brand_lower)
        else:
            output.remove(brand_lower)
            output.insert(0, brand_lower)
    return output[:7]


def _tidy_quote(value: str) -> str:
    text = clean_inline(value).strip('"“”')
    text = re.sub(r"[~|]+$", "", text).strip()
    text = re.sub(r"\bvib\s+rn\b", "vibe rn", text)
    if text and text[0].islower():
        text = text[0].upper() + text[1:]
    return text


def _quote_score(text: str) -> float:
    value = _tidy_quote(text)
    words = value.split()
    if len(words) < 4 or len(value) < 16 or len(value) > 150:
        return 0.0
    if re.search(r"\b(link in bio|follow for|subscribe|shop now|buy now)\b", value, re.I):
        return 0.0
    if not spoken_sentence(value):
        return 0.0
    score = min(len(value), 100) / 55.0
    if re.search(r"\bpov\b", value, re.I):
        score += 3.0
    if "?" in value:
        score += 1.2
    if re.search(r"\b(you|your|i|we|my|our)\b", value, re.I):
        score += 1.0
    if re.search(r"\b(not|never|always|finally|best|love|need|wait)\b", value, re.I):
        score += 0.8
    if value.isupper():
        score -= 0.6
    return score


def _best_quote(transcript: dict, onscreen: dict) -> dict | None:
    candidates: list[dict] = []
    if transcript.get("available") and transcript.get("quote_ready"):
        sentences = re.split(r"(?<=[.!?])\s+", transcript.get("text", ""))
        for sentence in sentences:
            score = _quote_score(sentence)
            if score > 0:
                candidates.append(
                    {
                        "text": _tidy_quote(sentence),
                        "score": score,
                        "source": "spoken",
                        "source_label": "Spoken",
                        "time": _time_for_text(sentence, transcript.get("segments") or []),
                    }
                )
    if onscreen.get("available"):
        for line in onscreen.get("lines") or []:
            score = _quote_score(line.get("text", ""))
            if score > 0:
                # On-screen copy is deliberately written, so it gets a small edge.
                score += 0.4
                candidates.append(
                    {
                        "text": _tidy_quote(line.get("text", "")),
                        "score": score,
                        "source": "onscreen",
                        "source_label": "On-screen",
                        "time": float(line.get("time") or 0),
                    }
                )
    if not candidates:
        return None
    best = max(candidates, key=lambda item: item["score"])
    if best["score"] < 2.8:
        return None
    best["time"] = round(float(best["time"]), 2)
    best["time_label"] = format_time(best["time"])
    best["score"] = round(best["score"], 2)
    return best


def _time_for_text(text: str, segments: list[dict]) -> float:
    needle = re.sub(r"[^a-z0-9 ]+", "", text.lower())[:24]
    for segment in segments:
        haystack = re.sub(r"[^a-z0-9 ]+", "", str(segment.get("text", "")).lower())
        if needle and needle in haystack:
            return float(segment.get("start") or 0)
    return float(segments[0].get("start") or 0) if segments else 0.0


def _sound_profile(
    meta: dict, transcript: dict, onscreen: dict, audio: dict
) -> dict:
    has_audio = bool(meta.get("has_audio")) and bool(audio.get("available"))
    clear_speech = bool(transcript.get("available") and transcript.get("quote_ready"))
    any_speech = bool(transcript.get("available"))
    if not has_audio:
        return {
            "key": "silent",
            "label": "Silent",
            "detail": "No audio track",
            "phrase": "pure visuals, no audio",
            "has_speech": False,
        }
    if clear_speech:
        detail = f"{transcript.get('word_count', 0)} words"
        if transcript.get("words_per_minute"):
            detail += f" · {transcript['words_per_minute']} wpm"
        return {
            "key": "voice",
            "label": "Voice-led",
            "detail": detail,
            "phrase": "a conversational voiceover",
            "has_speech": True,
        }
    if any_speech:
        return {
            "key": "voice-mixed",
            "label": "Voice + sound",
            "detail": "Speech is present but hard to pin down",
            "phrase": "a sound-led edit with a little voice",
            "has_speech": True,
        }
    character = audio.get("character") or "Sound-led"
    return {
        "key": "sound",
        "label": "Sound-led",
        "detail": character,
        "phrase": "a sound-led edit",
        "has_speech": False,
    }


def _palette_phrase(palette: list[dict]) -> str:
    names = [str(item.get("name")) for item in palette if item.get("name")]
    unique: list[str] = []
    for name in names:
        if name not in unique:
            unique.append(name)
    if not unique:
        return "clean, neutral"
    return format_list(unique[:2])


def _mood_for(visual: dict, palette_phrase: str) -> dict:
    averages = visual.get("averages") or {}
    brightness = float(averages.get("brightness") or 0.5)
    saturation = float(averages.get("saturation") or 0.3)
    warmth = float(averages.get("warmth") or 0.5)
    contrast = float(averages.get("contrast") or 0.2)
    palette_names = {str(item.get("name")) for item in visual.get("palette") or []}
    cool_names = {"sky", "cobalt", "navy", "teal", "electric blue", "seafoam"}
    cool_score = len(palette_names & cool_names)

    colorfulness = float(averages.get("colorfulness") or 0.3)
    if brightness < 0.3 and colorfulness < 0.4:
        key = "moody"
    elif colorfulness > 0.4 and saturation > 0.22 and brightness > 0.32:
        key = "vivid"
    elif warmth > 0.56 and brightness > 0.42:
        key = "warm"
    elif colorfulness < 0.28 and saturation < 0.21:
        key = "minimal"
    elif cool_score >= 2 and saturation < 0.42:
        key = "cool"
    else:
        key = "cinematic"

    mood = dict(MOODS[key])
    mood["key"] = key
    mood["palette_phrase"] = palette_phrase
    if key == "vivid":
        pace_label = str(visual.get("pace", {}).get("label", "lively")).lower()
        mood["description"] = (
            f"Big colour and a {pace_label} rhythm give this edit a bright, "
            "scroll-stopping personality."
        )
    elif key == "warm":
        mood["description"] = (
            f"{palette_phrase.capitalize()} frames and an easy pace make this feel "
            "inviting and quietly cinematic."
        )
    elif key == "moody":
        mood["description"] = (
            "Low light and deep contrast give the frames a considered, atmospheric pull."
        )
    return mood


def _format_type(filename: str, onscreen: dict) -> str:
    lower = f" {filename.lower()} "
    if re.search(r"\b(ad|ads|advert|commercial|promo|spot|campaign)\b", lower):
        return "promo"
    text = str(onscreen.get("text") or "").lower()
    if "link in bio" in text or "shop now" in text:
        return "promo"
    return "short video"


def _duration_adjective(duration: float) -> str:
    if duration < 1:
        return "one-second"
    if duration < 60:
        return f"{round(duration)}-second"
    minutes = duration / 60
    if abs(minutes - round(minutes)) < 0.08:
        return f"{round(minutes)}-minute"
    return f"{minutes:.1f}-minute"


def _text_phrase(onscreen: dict, sound: dict) -> str:
    clear_voice = sound.get("key") == "voice"
    if onscreen.get("available") and clear_voice:
        return "on-screen hooks and a clear voiceover"
    if onscreen.get("available"):
        return "on-screen copy doing the talking"
    if clear_voice:
        return "a conversational voiceover"
    if sound.get("key") == "silent":
        return "pure visuals, no audio"
    return "a sound-led edit"


def build_analysis(
    job_id: str,
    *,
    filename: str,
    meta: dict,
    visual: dict,
    audio: dict,
    transcript: dict,
    onscreen: dict,
) -> dict:
    palette_phrase = _palette_phrase(visual.get("palette") or [])
    mood = _mood_for(visual, palette_phrase)
    pace = visual.get("pace") or {}
    sound = _sound_profile(meta, transcript, onscreen, audio)
    sources = {
        "filename": Path(filename or "").stem,
        "onscreen": str(onscreen.get("text") or ""),
        "transcript": str(transcript.get("text") or ""),
    }
    topic, matched_terms = _score_topics(sources)
    brand, brand_score = _brand_candidates(
        filename, onscreen.get("lines") or []
    )
    quote = _best_quote(transcript, onscreen)
    keywords = _keywords(
        filename=filename,
        transcript=transcript,
        onscreen=onscreen,
        brand=brand,
        matched_topic_terms=matched_terms,
    )

    frame_base_url = f"/api/jobs/{job_id}/frames"
    frames = []
    for frame in visual.get("frames") or []:
        frames.append(
            {
                **{key: value for key, value in frame.items() if key != "thumbnail_url"},
                "url": f"{frame_base_url}/{frame['filename']}",
            }
        )

    for line in onscreen.get("lines") or []:
        line.pop("_center_y", None)

    if transcript.get("available"):
        excerpt = transcript.get("text", "")
    else:
        excerpt = ""
    if quote and quote.get("source") == "onscreen":
        excerpt = quote["text"]

    duration = float(meta.get("duration") or 0)
    content_type = _format_type(filename, onscreen)
    sound_phrase = _text_phrase(onscreen, sound)
    brand_phrase = f" for {brand}" if brand else ""
    pace_phrase = str(pace.get("label") or "Steady").lower()
    summary = (
        f"An {_duration_adjective(duration)} {meta.get('orientation', 'short').lower()} "
        f"{content_type}{brand_phrase} — {pace_phrase}, {palette_phrase}, "
        f"with {sound_phrase}."
    )

    look_phrase = f"{palette_phrase} frames"
    if float((visual.get("averages") or {}).get("contrast") or 0) > 0.3:
        look_phrase += " and high-contrast lighting"

    visual_beats = int(pace.get("transitions", 0) or 0)
    beat_word = "beat" if visual_beats == 1 else "beats"
    insights = [
        {
            "key": "pace",
            "label": "Pace",
            "value": pace.get("label", "Steady"),
            "detail": f"{visual_beats} visual {beat_word} · "
            f"{pace.get('average_shot_seconds', 0):.1f}s rhythm",
        },
        {
            "key": "mood",
            "label": "Mood",
            "value": mood.get("label", "Cinematic"),
            "detail": look_phrase,
        },
        {
            "key": "sound",
            "label": "Sound",
            "value": sound.get("label", "Sound-led"),
            "detail": sound.get("detail", ""),
        },
        {
            "key": "frame",
            "label": "Frame",
            "value": f"{meta.get('width', 0)} × {meta.get('height', 0)}",
            "detail": f"{meta.get('orientation', '')} · {meta.get('fps') or '—'} fps",
        },
    ]

    transcript_payload = {
        "available": bool(transcript.get("available")),
        "reason": transcript.get("reason"),
        "text": transcript.get("text", ""),
        "segments": transcript.get("segments", []),
        "word_count": transcript.get("word_count", 0),
        "words_per_minute": transcript.get("words_per_minute", 0),
        "language": transcript.get("language", ""),
        "language_probability": transcript.get("language_probability", 0),
        "quote_ready": bool(transcript.get("quote_ready")),
        "quality": "clear"
        if transcript.get("quote_ready")
        else "unclear"
        if transcript.get("available")
        else None,
        "excerpt": clean_inline(excerpt, limit=220),
    }
    onscreen_payload = {
        "available": bool(onscreen.get("available")),
        "reason": onscreen.get("reason"),
        "lines": onscreen.get("lines", []),
        "text": onscreen.get("text", ""),
    }

    video = {
        **meta,
        "video_url": f"/api/jobs/{job_id}/video",
        "poster_url": frames[0]["url"] if frames else None,
        "download_url": f"/api/jobs/{job_id}/video?download=1",
    }

    reading = {
        "summary": summary,
        "mood": mood,
        "pace": pace,
        "sound": sound,
        "look": look_phrase,
        "palette": visual.get("palette") or [],
        "insights": insights,
        "quote": quote,
        "keywords": keywords,
        "brand": brand,
        "brand_score": brand_score,
        "category": {"key": topic["key"], "label": topic["label"]},
    }

    return {
        "video": video,
        "frames": frames,
        "reading": reading,
        "transcript": transcript_payload,
        "onscreen": onscreen_payload,
        "audio": audio,
        "caption_context": {
            "topic": topic["key"],
            "topic_label": topic["label"],
            "brand": brand,
            "keywords": keywords,
            "quote": quote,
            "mood": mood,
            "pace": pace,
            "sound": sound,
            "palette": visual.get("palette") or [],
            "summary": summary,
            "duration": duration,
            "orientation": str(meta.get("orientation") or "").lower(),
            "has_onscreen": bool(onscreen.get("available")),
            "has_speech": bool(transcript.get("quote_ready")),
        },
    }
