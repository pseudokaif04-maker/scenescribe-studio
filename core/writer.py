"""A local caption writer built around the actual signals in the video.

The goal is not to sound like a generic "AI caption". Each draft is assembled
from the edit's own rhythm, palette, on-screen copy, speech, and topic. Tone and
platform change the shape of the copy, not just a handful of emojis.
"""

from __future__ import annotations

import hashlib
import random
import re
from typing import Any

from .utils import format_duration, format_list, hashtag, truncated_word

TONE_OPTIONS: dict[str, dict] = {
    "cinematic": {
        "label": "Cinematic",
        "description": "Atmospheric, restrained, a little poetic.",
        "hooks": [
            "Some moments are better felt than explained.",
            "A small story, told in light and motion.",
            "Not every frame needs a caption. This one earns it.",
            "There’s a whole mood in these few seconds.",
            "A moment, held just long enough.",
            "The kind of scene you keep coming back to.",
            "No rush. Just the frame, doing its thing.",
        ],
        "reactions": [
            "The light does most of the talking.",
            "Every cut lands with intention.",
            "Quiet detail, steady rhythm, a little afterglow.",
            "It’s all in the way the frame moves.",
            "A little atmosphere goes a long way.",
            "Some stories live in the space between cuts.",
        ],
        "questions": [
            "What does this moment feel like to you?",
            "Would you stop scrolling for this? Honestly.",
            "What’s the feeling you get from this frame?",
        ],
        "statements": [
            "This is what a mood looks like in motion.",
            "Less noise. More feeling.",
            "Atmosphere is its own story.",
            "A reminder that a frame can hold a whole world.",
        ],
        "ctas": [
            "Watch it with the sound on.",
            "Save this for a slower moment.",
            "Stay for the last frame.",
            "Turn the volume up and let it play.",
        ],
    },
    "playful": {
        "label": "Playful",
        "description": "Bright, conversational, and built to be shared.",
        "hooks": [
            "POV: you found the good part.",
            "No thoughts, just vibes.",
            "This is your sign to press play.",
            "Main character energy, delivered.",
            "Okay, this is the fun part.",
            "Consider this your daily dose of good.",
            "The algorithm knew what it was doing.",
        ],
        "reactions": [
            "The vibe is immaculate, and the edit knows it.",
            "Warning: may cause an instant rewatch.",
            "A little chaotic. A lot of fun.",
            "We came for the aesthetic; we stayed for the energy.",
            "No notes. Just replaying it.",
            "This is the serotonin we ordered.",
        ],
        "questions": [
            "Okay, but can we talk about this?",
            "Who else needed this today?",
            "Be honest — how many times did you watch it?",
            "What part lives in your head rent-free?",
        ],
        "statements": [
            "The vibe? Unmatched.",
            "Fun looks good on you.",
            "A whole personality in eight seconds.",
            "This is what we mean by main character energy.",
        ],
        "ctas": [
            "Send this to someone who gets it.",
            "Save it, share it, rewatch it.",
            "Follow for more of this energy.",
            "Tag your group chat.",
        ],
    },
    "bold": {
        "label": "Bold",
        "description": "Punchy, confident, and impossible to skim past.",
        "hooks": [
            "Stop scrolling. This is the one.",
            "You’re not ready for this cut.",
            "This is what it looks like when it clicks.",
            "Watch it once. You’ll watch it again.",
            "No warm-up. Straight to the good part.",
            "This is the version worth posting.",
        ],
        "reactions": [
            "Every frame is doing its job.",
            "Confidence, in video form.",
            "Sharp edit. Clear point of view. No filler.",
            "It hits different when the details are right.",
            "Built to be remembered, not just seen.",
        ],
        "questions": [
            "What’s stopping you from making this yours?",
            "Ready to turn the ordinary into a feed-stopper?",
            "Why blend in when you can do this?",
        ],
        "statements": [
            "Make the scroll stop.",
            "The standard just moved.",
            "Don’t just post. Make an impression.",
            "Good is fine. This is better.",
        ],
        "ctas": [
            "Follow for more like this.",
            "Watch till the last frame.",
            "Save this and come back to it.",
            "Your turn. Make it yours.",
        ],
    },
    "warm": {
        "label": "Warm",
        "description": "Personal, generous, and close to the moment.",
        "hooks": [
            "The little things are the whole thing.",
            "A moment worth keeping.",
            "This felt like a deep breath.",
            "The best bits are rarely planned.",
            "A small pocket of joy, shared.",
            "Some days just feel like this.",
        ],
        "reactions": [
            "Soft light, good company, nowhere else to be.",
            "The kind of moment you want to hold on to.",
            "Simple, warm, and a little bit magic.",
            "This is what the good part feels like.",
            "A reminder to take the long way home.",
        ],
        "questions": [
            "What’s a little thing that made your day?",
            "Who would you share this moment with?",
            "When did you last slow down like this?",
        ],
        "statements": [
            "Save the little moments. They’re the big ones.",
            "There’s beauty in the everyday.",
            "A gentle reminder to be here.",
            "The ordinary is worth a closer look.",
        ],
        "ctas": [
            "Share this with someone you love.",
            "Save this for a softer day.",
            "Tag someone who feels like home.",
            "Stay for a slow minute.",
        ],
    },
    "minimal": {
        "label": "Minimal",
        "description": "Short, clean, and confident enough to say less.",
        "hooks": [
            "Just this.",
            "A moment, in full.",
            "No caption needed. Almost.",
            "Let it speak.",
            "This is enough.",
            "Quietly, this.",
        ],
        "reactions": [
            "Warm light. Easy pace. Nothing extra.",
            "A small frame with a long afterglow.",
            "Simple, clean, done.",
            "Soft light. Clear feeling.",
            "Less, but better.",
        ],
        "questions": [
            "What do you see here?",
            "Does this feel like you?",
            "Worth a pause?",
        ],
        "statements": [
            "Less, but better.",
            "Let the frame breathe.",
            "Enough said.",
            "Keep the good part.",
        ],
        "ctas": [
            "Here, for a moment.",
            "Keep this one.",
            "Press play. That’s it.",
            "Save it. No notes.",
        ],
    },
    "professional": {
        "label": "Professional",
        "description": "Polished, thoughtful, and clear about the craft.",
        "hooks": [
            "Craft, in motion.",
            "The details tell the story.",
            "A closer look at the work.",
            "Built with intention.",
            "This is what the process looks like.",
            "Good work has a rhythm.",
        ],
        "reactions": [
            "A clear idea, carried through every frame.",
            "The kind of finish that shows in the details.",
            "Considered from the first frame to the last.",
            "A visual point of view, not just a video.",
            "The craft is in the choices you don’t notice.",
        ],
        "questions": [
            "What detail stands out to you?",
            "Which part of the process would you like to see next?",
            "What makes this feel finished to you?",
        ],
        "statements": [
            "The work is in the details.",
            "Clarity is a creative choice.",
            "Good ideas deserve a good frame.",
            "Process is part of the product.",
        ],
        "ctas": [
            "Follow for more behind-the-scenes work.",
            "Save this for your next creative brief.",
            "What would you add to this?",
            "More process, less polish — follow along.",
        ],
    },
}

PLATFORM_OPTIONS: dict[str, dict] = {
    "instagram": {
        "label": "Instagram",
        "short_label": "Reels",
        "hashtag_count": 8,
        "limit": 2200,
        "ctas": [
            "Save this for later.",
            "Share this with someone who needs it.",
            "Follow for more moments like this.",
            "Tag someone who’d love this.",
        ],
        "tags": ["reels", "explorepage"],
    },
    "tiktok": {
        "label": "TikTok",
        "short_label": "TikTok",
        "hashtag_count": 6,
        "limit": 2200,
        "ctas": [
            "Watch till the last frame.",
            "Send this to your group chat.",
            "Follow for more.",
            "Save it before it disappears.",
        ],
        "tags": ["fyp", "foryou"],
    },
    "youtube": {
        "label": "YouTube Shorts",
        "short_label": "Shorts",
        "hashtag_count": 3,
        "limit": 5000,
        "ctas": [
            "Subscribe for more.",
            "Watch the full story.",
            "Save this for later.",
            "Like if this hit.",
        ],
        "tags": ["shorts"],
    },
    "linkedin": {
        "label": "LinkedIn",
        "short_label": "LinkedIn",
        "hashtag_count": 3,
        "limit": 3000,
        "ctas": [
            "What would you add?",
            "Follow along for more process.",
            "Save this for your next brief.",
            "Share your take below.",
        ],
        "tags": ["creativeprocess", "storytelling"],
    },
    "x": {
        "label": "X",
        "short_label": "X",
        "hashtag_count": 2,
        "limit": 280,
        "ctas": [
            "Watch it twice.",
            "Your take?",
            "Follow for more.",
            "Save it.",
        ],
        "tags": ["video"],
    },
}

TOPIC_WRITING: dict[str, dict] = {
    "beauty": {
        "label": "beauty & care",
        "core": [
            "Good hair days, on repeat.",
            "A little shine changes the whole frame.",
            "Care that looks as good as it feels.",
            "The kind of glow you can see from here.",
            "Soft, strong, and completely yours.",
            "A routine that earns its place on the shelf.",
        ],
        "details": [
            "The little details make the biggest difference.",
            "Smooth, soft, and ready for the close-up.",
            "A reset for the hair and the mood.",
            "Because the mirror should be on your side.",
        ],
        "questions": [
            "What’s the one step in your routine you never skip?",
            "What does your best hair day look like?",
            "Who would you send this to?",
        ],
        "hashtags": ["beauty", "haircare", "selfcare", "glowup", "hairtok"],
        "emojis": ["✨", "🫧", "💫"],
    },
    "fashion": {
        "label": "fashion",
        "core": [
            "Wear the mood.",
            "A fit that speaks before you do.",
            "Details make the look.",
            "Styled with a point of view.",
            "The kind of outfit that changes your posture.",
        ],
        "details": [
            "One look, everything in its place.",
            "It’s in the layers, the lines, and the little risks.",
            "A reminder that getting dressed can be the whole story.",
        ],
        "questions": [
            "Would you wear this?",
            "Which piece would you steal from this look?",
            "How would you style it?",
        ],
        "hashtags": ["fashion", "style", "outfit", "lookbook", "ootd"],
        "emojis": ["🖤", "✨", "👗"],
    },
    "food": {
        "label": "food",
        "core": [
            "Made slow, gone fast.",
            "The kind of plate worth pausing for.",
            "Good food, better company.",
            "A little comfort, served warm.",
            "Flavour first, always.",
        ],
        "details": [
            "The kind of meal that makes the room go quiet.",
            "Simple ingredients, no shortcuts.",
            "You can almost taste it through the screen.",
        ],
        "questions": [
            "What would you pair this with?",
            "Who are you sharing the next meal with?",
            "Sweet or savoury first?",
        ],
        "hashtags": ["food", "foodie", "homecooking", "recipe", "delicious"],
        "emojis": ["🍋", "✨", "🤌"],
    },
    "travel": {
        "label": "travel",
        "core": [
            "Collect moments, not plans.",
            "New streets, familiar wonder.",
            "Wander first, worry later.",
            "A little further from ordinary.",
            "The view is the plan.",
        ],
        "details": [
            "A detour worth taking.",
            "New light, new streets, nowhere else to be.",
            "The kind of place that makes time move differently.",
        ],
        "questions": [
            "Where would you go first?",
            "What’s on your travel list right now?",
            "Who’s coming with you?",
        ],
        "hashtags": ["travel", "wanderlust", "traveldiaries", "explore", "adventure"],
        "emojis": ["✈️", "🌤️", "🌍"],
    },
    "fitness": {
        "label": "fitness",
        "core": [
            "Show up. Sweat. Repeat.",
            "Progress is a practice.",
            "Strong looks good on you.",
            "A little stronger than yesterday.",
            "Movement is the mood.",
        ],
        "details": [
            "The hard part is starting. You’re already past it.",
            "No shortcuts, just the work.",
            "Every rep counts, even the quiet ones.",
        ],
        "questions": [
            "What’s moving you today?",
            "Ready to make the next rep count?",
            "What keeps you showing up?",
        ],
        "hashtags": ["fitness", "workout", "wellness", "movement", "progress"],
        "emojis": ["⚡", "💪", "🔥"],
    },
    "nature": {
        "label": "the outdoors",
        "core": [
            "A reminder to breathe.",
            "Nature doesn’t rush.",
            "Soft light, open air.",
            "Exactly where you need to be.",
            "The quiet can be the whole story.",
        ],
        "details": [
            "A little wildness, right on time.",
            "Wide open, and nowhere else to be.",
            "The kind of view that resets the pace.",
        ],
        "questions": [
            "When did you last get outside?",
            "Where would you go right now?",
            "Can you hear it through the screen?",
        ],
        "hashtags": ["nature", "outdoors", "slowliving", "explore", "earth"],
        "emojis": ["🌿", "🌞", "🍃"],
    },
    "tech": {
        "label": "tech",
        "core": [
            "Built different. Built with intention.",
            "Small details. Big difference.",
            "The future is already here.",
            "Designed to feel effortless.",
            "A closer look at what’s next.",
        ],
        "details": [
            "The kind of product you understand in one look.",
            "Good design removes steps, not adds them.",
            "Under the polish, a clear idea at work.",
        ],
        "questions": [
            "What would you build with this?",
            "Which detail do you want us to go deeper on?",
            "Would this change your workflow?",
        ],
        "hashtags": ["tech", "design", "innovation", "build", "product"],
        "emojis": ["⚡", "🧠", "🛠️"],
    },
    "music": {
        "label": "music",
        "core": [
            "Turn it up. Let it move you.",
            "A little louder. A little freer.",
            "The beat knows what to do.",
            "Caught in the rhythm.",
            "Sound first, everything else follows.",
        ],
        "details": [
            "A snippet that sticks with you.",
            "Volume up. World down.",
            "The kind of rhythm that makes a room move.",
        ],
        "questions": [
            "What song is on repeat for you?",
            "Ready to turn it up?",
            "Where does this track take you?",
        ],
        "hashtags": ["music", "newmusic", "musicdiscovery", "studio", "vibes"],
        "emojis": ["🎵", "⚡", "🎧"],
    },
    "gaming": {
        "label": "gaming",
        "core": [
            "One more level.",
            "Locked in.",
            "The game has a way of finding you.",
            "No lag. Just momentum.",
            "The good part starts now.",
        ],
        "details": [
            "Fast fingers, sharper instincts.",
            "A moment that belongs in the highlight reel.",
            "The kind of run you replay.",
        ],
        "questions": [
            "What’s your comfort game right now?",
            "Would you survive this?",
            "One more round?",
        ],
        "hashtags": ["gaming", "gamer", "gameplay", "gamingcommunity", "highlight"],
        "emojis": ["🎮", "⚡", "👾"],
    },
    "business": {
        "label": "creative work",
        "core": [
            "The work behind the work.",
            "Ideas become real when you build them.",
            "Good work, made visible.",
            "A closer look at the craft.",
            "Clarity is the whole strategy.",
        ],
        "details": [
            "The details behind the final frame.",
            "Process is part of the product.",
            "A small team, a clear point of view.",
        ],
        "questions": [
            "What’s the detail you’re proudest of?",
            "How do you turn an idea into a finished thing?",
            "What would you add to the process?",
        ],
        "hashtags": ["creativebusiness", "behindthescenes", "design", "storytelling", "craft"],
        "emojis": ["✦", "✳️"],
    },
    "home": {
        "label": "home",
        "core": [
            "Make the space yours.",
            "A room with a point of view.",
            "The little corners tell the story.",
            "Home is a feeling you can style.",
        ],
        "details": [
            "Warm light, good texture, nothing extra.",
            "The details that make a room feel lived in.",
            "A space that exhales.",
        ],
        "questions": [
            "Would you live here?",
            "What’s your favourite corner in your home?",
            "What detail would you copy?",
        ],
        "hashtags": ["interiors", "hometour", "homemaking", "design", "cozy"],
        "emojis": ["🕯️", "🌿", "✨"],
    },
    "pets": {
        "label": "pets",
        "core": [
            "The main character has four paws.",
            "A little chaos, a lot of love.",
            "No bad days with this face.",
            "The best kind of company.",
            "Soft heart, serious charm.",
        ],
        "details": [
            "Making a very convincing case for one more treat.",
            "The kind of face that runs the whole household.",
            "Here for the belly rubs and the camera time.",
        ],
        "questions": [
            "Would you share your snack?",
            "Who else’s pet runs the house?",
            "What’s their name?",
        ],
        "hashtags": ["pets", "dogsofinstagram", "catsofinstagram", "petlovers", "furryfriend"],
        "emojis": ["🐾", "🫶", "🐶", "🐱"],
    },
    "art": {
        "label": "art & film",
        "core": [
            "A frame worth a second look.",
            "The work speaks first.",
            "Made slowly, seen closely.",
            "The details are the story.",
        ],
        "details": [
            "A little closer to the idea.",
            "Made with attention, meant for a pause.",
            "The kind of frame that keeps giving.",
        ],
        "questions": [
            "What do you notice first?",
            "Where would you hang this?",
            "What does it make you feel?",
        ],
        "hashtags": ["art", "creativeprocess", "design", "film", "madebyhand"],
        "emojis": ["🎞️", "✨", "🖼️"],
    },
    "lifestyle": {
        "label": "everyday life",
        "core": [
            "A small moment, held for a second longer.",
            "This is the part worth remembering.",
            "Slow down; it looks good on you.",
            "The day, in a good light.",
            "A little ordinary magic.",
        ],
        "details": [
            "Nothing extra. That’s the point.",
            "The kind of day that looks good in hindsight.",
            "A moment, exactly as it felt.",
        ],
        "questions": [
            "What made you smile today?",
            "When did you last stop to notice?",
            "Who would you share this day with?",
        ],
        "hashtags": ["lifestyle", "slowliving", "moments", "everydaymagic", "aesthetic"],
        "emojis": ["☕", "✨", "🌤️"],
    },
}


def _stable_rng(*parts: Any) -> random.Random:
    payload = "::".join(str(part) for part in parts)
    digest = hashlib.sha256(payload.encode("utf-8")).digest()
    return random.Random(int.from_bytes(digest[:8], "big"))


def _clean_body(value: str) -> str:
    text = re.sub(r"[ \t]+\n", "\n", value or "")
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _join_parts(parts: list[str], platform: str) -> str:
    cleaned = [_clean_body(part) for part in parts if _clean_body(part)]
    if platform == "x":
        return " ".join(part.replace("\n", " ") for part in cleaned).strip()
    return "\n\n".join(cleaned)


def _pick(rng: random.Random, values: list[str]) -> str:
    return rng.choice(values) if values else ""


def _emoji_for(profile: dict, tone: str, platform: str, rng: random.Random) -> str:
    if tone in {"minimal", "cinematic", "professional"} or platform == "linkedin":
        return ""
    if rng.random() < 0.45:
        return ""
    emojis = profile.get("emojis") or []
    return f" {_pick(rng, emojis)}" if emojis else ""


def _cta_for(
    platform: str, tone: str, rng: random.Random, *, compact: bool = False
) -> str:
    platform_data = PLATFORM_OPTIONS[platform]
    tone_data = TONE_OPTIONS[tone]
    if platform == "x":
        return _pick(rng, ["Watch it twice.", "Your take?", "Save it.", "Follow for more."])
    if compact:
        return _pick(rng, ["Save this.", "Share this.", "Follow for more."])
    pool = platform_data["ctas"] + tone_data["ctas"]
    return _pick(rng, pool)


def _visual_lines(context: dict) -> list[str]:
    pace = context.get("pace") or {}
    key = pace.get("key", "steady")
    if key == "fast":
        options = [
            "Big colour, quick cuts, no dead air.",
            "A fast, bright little edit with somewhere to go.",
            "Quick frames, clear point of view.",
            "Colour up, pace up, no wasted seconds.",
        ]
    elif key == "snappy":
        options = [
            "Crisp cuts and a rhythm that keeps moving.",
            "A brisk edit with colour to spare.",
            "Quick enough to catch the eye. Warm enough to keep it.",
        ]
    elif key == "steady":
        options = [
            "A steady rhythm and light that carries it.",
            "Room to look, colour to hold the frame.",
            "Easy pacing, intentional detail.",
        ]
    elif key == "slow":
        options = [
            "Slow light and a frame that lingers.",
            "An unhurried cut with a long afterglow.",
            "A patient edit that lets the moment arrive.",
        ]
    else:
        options = [
            "A quiet cut with room to breathe.",
            "Nothing hurried. Just the moment, held.",
            "Stillness, with a little light in it.",
        ]
    palette = context.get("palette") or []
    names = [str(item.get("name")) for item in palette[:2] if item.get("name")]
    if len(names) == 2:
        options.append(f"{names[0].capitalize()} and {names[1]} frames, doing their thing.")
    return options


def _hashtag_pool(context: dict, tone: str, platform: str) -> list[str]:
    profile = TOPIC_WRITING.get(context.get("topic", "lifestyle"), TOPIC_WRITING["lifestyle"])
    tone_tags = {
        "cinematic": ["cinematic", "slowliving", "visualstorytelling"],
        "playful": ["goodvibes", "fun", "viral"],
        "bold": ["bold", "scrollstopper", "reels"],
        "warm": ["slowliving", "moments", "storytelling"],
        "minimal": ["minimal", "aesthetic", "simple"],
        "professional": ["behindthescenes", "craft", "creativeprocess"],
    }
    candidates: list[str] = []

    def add(value: str) -> None:
        tag = hashtag(value)
        if tag and tag not in candidates and len(tag) > 2:
            candidates.append(tag)

    keywords = [word for word in (context.get("keywords") or []) if isinstance(word, str)]
    brand = (context.get("brand") or "").lower()
    specific = [word for word in keywords if word.lower() != brand]
    profile_tags = list(profile.get("hashtags") or [])
    platform_tags = list(PLATFORM_OPTIONS[platform].get("tags") or [])[:1]
    if platform in {"linkedin", "x"}:
        platform_tags = []
    tone_pool = tone_tags.get(tone, [])

    # Alternate the most useful signals rather than dumping every keyword in
    # first. The result reads like a considered tag set, not a keyword soup.
    if brand:
        add(brand)
    for index in range(max(len(specific), len(profile_tags), len(tone_pool))):
        if index < len(platform_tags):
            add(platform_tags[index])
        if index < len(profile_tags):
            add(profile_tags[index])
        if index < len(specific):
            add(specific[index])
        if index == 0 and tone_pool:
            add(tone_pool[0])
    for word in specific:
        add(word)
    for value in platform_tags:
        add(value)
    for value in profile_tags:
        add(value)
    for value in tone_pool:
        add(value)
    return candidates


def _select_hashtags(
    context: dict, tone: str, platform: str, rng: random.Random
) -> list[str]:
    pool = _hashtag_pool(context, tone, platform)
    desired = PLATFORM_OPTIONS[platform]["hashtag_count"]
    if platform == "x":
        # Keep a little room for the actual thought.
        desired = 2
    return pool[:desired]


def _finalize(
    parts: list[str],
    hashtags: list[str],
    platform: str,
    *,
    compact: bool = False,
) -> tuple[str, str, str]:
    limit = int(PLATFORM_OPTIONS[platform]["limit"])
    tag_text = " ".join(hashtags)
    separator = " " if platform == "x" else "\n\n"

    body = _join_parts(parts, platform)

    full = f"{body}{separator}{tag_text}".strip() if tag_text else body
    if len(full) <= limit:
        return body, tag_text, full

    # For X and any unexpected overflow, give the hashtags one slot and trim the
    # body at a word boundary. No caption ever cuts a word in half.
    if len(hashtags) > 1:
        tag_text = hashtags[0]
        full = f"{body}{separator}{tag_text}".strip()
        if len(full) <= limit:
            return body, tag_text, full

    available = max(12, limit - len(tag_text) - len(separator))
    body = truncated_word(body, available)
    full = f"{body}{separator}{tag_text}".strip() if tag_text else body
    return body, tag_text, full


def _build_cards(
    context: dict, tone: str, platform: str, rng: random.Random, hashtags: list[str]
) -> list[dict]:
    profile = TOPIC_WRITING.get(context.get("topic", "lifestyle"), TOPIC_WRITING["lifestyle"])
    tone_data = TONE_OPTIONS[tone]
    quote = context.get("quote") or None
    compact = platform == "x"
    cards: list[dict] = []

    def add(
        card_id: str,
        label: str,
        note: str,
        parts: list[str],
        *,
        force_compact: bool = False,
        popular: bool = False,
    ) -> None:
        body, tags_text, text = _finalize(
            parts,
            hashtags,
            platform,
            compact=compact or force_compact,
        )
        cards.append(
            {
                "id": card_id,
                "label": label,
                "note": note,
                "body": body,
                "hashtags": tags_text.split() if tags_text else [],
                "text": text,
                "char_count": len(text),
                "recommended": popular,
            }
        )

    hook = _pick(rng, tone_data["hooks"])
    core = _pick(rng, profile["core"])
    cta = _cta_for(platform, tone, rng)
    emoji = _emoji_for(profile, tone, platform, rng)
    add(
        "scroll-stopper",
        "Scroll-stopper",
        "The all-rounder: hook, heart, and a clear next step.",
        [hook, f"{core}{emoji}", cta],
        popular=True,
    )

    visual = _pick(rng, _visual_lines(context))
    detail = _pick(rng, profile["details"])
    story_cta = _cta_for(platform, tone, rng) if rng.random() > 0.28 else ""
    add(
        "story",
        "The story",
        "A more atmospheric read of the edit.",
        [visual, detail, story_cta],
    )

    short_core = _pick(rng, [line for line in profile["core"] if line != core] or profile["core"])
    short_emoji = _emoji_for(profile, tone, platform, rng)
    add(
        "short",
        "Short & sweet",
        "One line. No filler. Ready to post.",
        [f"{short_core}{short_emoji}"],
        force_compact=compact,
        popular=False,
    )

    question = _pick(rng, profile["questions"])
    question_cta = _pick(rng, PLATFORM_OPTIONS[platform]["ctas"])
    add(
        "question",
        "Conversation starter",
        "Built to bring people into the comments.",
        [question, question_cta],
    )

    if quote:
        quote_text = str(quote.get("text") or "").strip().strip('"“”')
        reaction = _pick(rng, tone_data["reactions"])
        quote_cta = _cta_for(platform, tone, rng)
        quote_source = "the video" if quote.get("source") == "onscreen" else "the voiceover"
        add(
            "quote",
            "Quote-led",
            f"Uses the video's own words from {quote_source}.",
            [f"“{quote_text}”", reaction, quote_cta],
        )
    else:
        mood_line = _pick(rng, _visual_lines(context))
        mood_reaction = _pick(rng, tone_data["reactions"])
        add(
            "quote",
            "Mood-led",
            "A visual-first caption for when the frames do the talking.",
            [mood_line, mood_reaction],
        )

    statement = _pick(rng, tone_data["statements"])
    manifesto_detail = _pick(rng, profile["details"])
    manifesto_cta = _cta_for(platform, tone, rng, compact=compact)
    add(
        "manifesto",
        "The big idea",
        "A stronger point of view for brand or campaign posts.",
        [statement, manifesto_detail, manifesto_cta],
    )

    return cards


def resolve_tone(analysis: dict, requested: str) -> tuple[str, bool]:
    if requested in TONE_OPTIONS:
        return requested, False
    context = analysis.get("caption_context") or {}
    hint = (context.get("mood") or {}).get("tone") or "cinematic"
    if hint not in TONE_OPTIONS:
        hint = "cinematic"
    return hint, True


def build_caption_set(
    analysis: dict,
    *,
    tone: str = "auto",
    platform: str = "instagram",
    seed: int = 0,
) -> dict:
    platform = platform if platform in PLATFORM_OPTIONS else "instagram"
    resolved_tone, auto_tone = resolve_tone(analysis, tone)
    context = dict(analysis.get("caption_context") or {})
    quote = (analysis.get("reading") or {}).get("quote") or context.get("quote")
    if quote:
        context["quote"] = quote
    keywords = (analysis.get("reading") or {}).get("keywords") or context.get("keywords") or []
    context["keywords"] = keywords

    video = analysis.get("video") or {}
    fingerprint_parts = [
        video.get("filename", ""),
        context.get("summary", ""),
        resolved_tone,
        platform,
        seed,
    ]
    rng = _stable_rng(*fingerprint_parts)
    hashtags = _select_hashtags(context, resolved_tone, platform, rng)
    cards = _build_cards(context, resolved_tone, platform, rng, hashtags)

    return {
        "tone": resolved_tone,
        "tone_label": TONE_OPTIONS[resolved_tone]["label"],
        "tone_description": TONE_OPTIONS[resolved_tone]["description"],
        "tone_requested": tone,
        "tone_auto": auto_tone,
        "platform": platform,
        "platform_label": PLATFORM_OPTIONS[platform]["label"],
        "seed": seed,
        "captions": cards,
        "recommended_id": "scroll-stopper",
        "signals": {
            "topic": context.get("topic_label", "everyday life"),
            "keywords": keywords,
            "quote": quote.get("text") if quote else None,
            "has_speech": bool(context.get("has_speech")),
            "has_onscreen": bool(context.get("has_onscreen")),
            "duration_label": format_duration(context.get("duration")),
            "palette": [
                item.get("name") for item in (context.get("palette") or []) if item
            ],
        },
    }


def caption_set_as_text(caption_set: dict, *, include_labels: bool = True) -> str:
    """Plain-text export shared by the frontend and the README example."""
    lines: list[str] = []
    platform = caption_set.get("platform_label", "Instagram")
    tone = caption_set.get("tone_label", "Cinematic")
    lines.append(f"SceneScribe captions — {platform} / {tone}")
    lines.append("")
    for index, caption in enumerate(caption_set.get("captions") or [], start=1):
        if include_labels:
            lines.append(f"{index:02d} · {caption.get('label', 'Caption')}")
        lines.append(str(caption.get("text", "")).strip())
        lines.append("")
    return "\n".join(lines).strip() + "\n"
