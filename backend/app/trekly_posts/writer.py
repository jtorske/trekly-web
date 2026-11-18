"""Turning a post's facts into text: the template always, the Claude API optionally.

Every generator writes a template text from real data. When the type allows
it, ANTHROPIC_API_KEY is set and [ai].enabled is on, the Claude API is asked to
rewrite that text as a friendly 1-3 sentence post using only the facts given.
Its answer is then checked (`check_ai_text`): any number, capitalised name,
month or weekday that isn't in the input, a link, mention or hashtag, more than
three sentences, or a text over the length limit sends the post back to the
template. So the worst the AI can do is change the wording.

Conditions and warnings never reach the AI: `write` refuses them outright,
on top of the config never allowing it (app/trekly_posts/config.py).
"""

import json
import logging
import os
import re
from dataclasses import dataclass
from typing import Any, Protocol

log = logging.getLogger(__name__)

NEVER_AI_TYPES = frozenset({"conditions"})

SYSTEM_PROMPT = """You write short posts for the official Trekly account, shown in the Activity feed of a \
Canadian hiking app.

Rewrite the DRAFT as a friendly post of 1 to 3 sentences, at most {max_chars} characters, in Canadian English.

Use only the facts in DATA and DRAFT. Do not add any fact that isn't there: no new numbers, names, places, \
dates, months, seasons, distances, times, rankings, superlatives, history, or claims about conditions, \
safety, weather, wildlife, crowds or access. Keep every number exactly as given. If you're unsure, stay \
close to the draft's wording.

No hashtags, emoji, links, @mentions, quotation marks or exclamation-mark chains. Reply with the post \
text only."""

NUMBER_WORDS = {
    "zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve",
    "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen", "twenty", "thirty",
    "forty", "fifty", "sixty", "seventy", "eighty", "ninety", "hundred", "hundreds", "thousand", "thousands",
    "million", "dozen", "dozens", "half", "once", "twice", "first", "second", "third", "fourth", "fifth",
    "tenth", "hundredth", "single", "double", "triple", "couple", "pair",
}
DATE_WORDS = {
    "january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
    "november", "december", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
    "today", "tomorrow", "yesterday", "tonight", "weekend", "spring", "summer", "fall", "autumn", "winter",
}
# Claims the AI likes to add: allowed only when the data says so too.
CLAIM_WORDS = {
    "best", "most", "least", "highest", "tallest", "longest", "largest", "biggest", "oldest", "newest",
    "busiest", "quietest", "steepest", "easiest", "hardest", "favourite", "favorite", "famous", "iconic",
    "popular", "beloved", "hidden", "gem", "only", "record", "closed", "closure", "open", "reopened", "safe",
    "safety", "dangerous", "danger", "bear", "bears", "wildlife", "snow", "ice", "icy", "avalanche",
    "wildfire", "fire", "smoke", "flood", "crowded", "crowds", "busy", "easy", "hard", "difficult",
    "moderate", "beginner", "beginners", "family", "families", "kids", "children", "dog", "dogs", "steep",
    "flat", "free", "permit", "permits", "reservation", "reservations", "views", "waterfall", "glacier",
    "lake", "lakes", "larch", "larches", "wildflowers", "sunrise", "sunset",
}
# Words that may start a sentence with a capital without being a name.
COMMON_STARTERS = {
    "a", "an", "the", "this", "that", "these", "those", "it", "its", "it's", "there", "here", "hikers",
    "hiker", "trail", "trails", "new", "fun", "fact", "did", "do", "you", "your", "we", "our", "if", "with",
    "for", "from", "on", "in", "at", "after", "before", "over", "plenty", "lots", "looking", "ready",
    "add", "take", "try", "plan", "save", "head", "check", "lace", "grab", "explore", "find", "see", "meet",
    "why", "what", "when", "where", "how", "who", "one", "some", "most", "more", "and", "but", "so", "just",
    "big", "great", "nice", "thanks", "congrats", "welcome", "trending", "spotlight", "community", "roundup",
    "photos", "photo", "fresh", "another", "every", "each", "all", "both", "whether", "time", "worth",
    "up", "out", "pack", "bring", "remember", "keep", "enjoy", "happy", "good", "busy", "quiet", "it’s",
}
ALWAYS_ALLOWED_NAMES = {"trekly", "i"}

NUMBER_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")
WORD_RE = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿ][A-Za-zÀ-ÖØ-öø-ÿ'’\-]*")
SENTENCE_END_RE = re.compile(r"[.!?]+(?=\s|$)")
FORBIDDEN_RE = re.compile(r"https?://|www\.|@\w|#\w|\.(?:com|ca|org|net)\b", re.IGNORECASE)


class TextClient(Protocol):
    def complete(self, system: str, user: str) -> str | None: ...


@dataclass(frozen=True)
class Written:
    body: str
    writer: str  # "template" or "ai"
    note: str | None = None


def _strings(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, bool):
        return []
    if isinstance(value, (int, float)):
        return [str(value)]
    if isinstance(value, dict):
        return [s for v in value.values() for s in _strings(v)]
    if isinstance(value, (list, tuple, set)):
        return [s for v in value for s in _strings(v)]
    return [str(value)]


def _norm_number(token: str) -> str:
    token = token.replace(",", "")
    if "." in token:
        token = token.rstrip("0").rstrip(".")
    return token


def _numbers(text: str) -> set[str]:
    return {_norm_number(n) for n in NUMBER_RE.findall(text)}


def _words(text: str) -> set[str]:
    return {w.lower().strip("'’-") for w in WORD_RE.findall(text)}


def check_ai_text(text: str, data: dict, template_body: str, max_chars: int) -> list[str]:
    """Problems with an AI-written post; empty when it may be used."""
    problems: list[str] = []
    text = text.strip()
    source = " ".join([template_body, *_strings(data)])
    if not text:
        return ["empty"]
    if len(text) > max_chars:
        problems.append(f"longer than {max_chars} characters")
    if "\n" in text:
        problems.append("more than one paragraph")
    sentences = [s for s in SENTENCE_END_RE.split(text) if s.strip()]
    if len(sentences) > 3:
        problems.append("more than 3 sentences")
    if FORBIDDEN_RE.search(text):
        problems.append("contains a link, mention or hashtag")
    if '"' in text or "“" in text or "”" in text:
        problems.append("contains quotation marks")

    extra_numbers = _numbers(text) - _numbers(source)
    if extra_numbers:
        problems.append(f"numbers not in the data: {sorted(extra_numbers)}")

    source_words = _words(source)
    for word in sorted(_words(text) & (NUMBER_WORDS | DATE_WORDS | CLAIM_WORDS)):
        if word not in source_words:
            problems.append(f"'{word}' isn't in the data")

    for match in WORD_RE.finditer(text):
        word = match.group(0)
        if not word[0].isupper():
            continue
        key = word.lower().strip("'’-")
        if key in source_words or key in ALWAYS_ALLOWED_NAMES:
            continue
        leading = text[:match.start()].rstrip(" \t'‘(")
        at_start = leading == "" or leading[-1] in ".!?:"
        if at_start and key in COMMON_STARTERS:
            continue
        problems.append(f"name '{word}' isn't in the data")

    for required in data.get("must_mention", []) or []:
        if required.lower() not in text.lower():
            problems.append(f"leaves out '{required}'")
    return problems


class AnthropicTextClient:
    """The Claude API through the official SDK. One short request per post."""

    def __init__(self, api_key: str, model: str, max_chars: int):
        import anthropic  # only needed when the AI is on

        self._anthropic = anthropic
        self._client = anthropic.Anthropic(api_key=api_key, timeout=60.0, max_retries=2)
        self._model = model
        self._max_chars = max_chars

    def complete(self, system: str, user: str) -> str | None:
        anthropic = self._anthropic
        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=4000,
                system=system,
                output_config={"effort": "low"},
                messages=[{"role": "user", "content": user}],
            )
        except (anthropic.RateLimitError, anthropic.APIStatusError, anthropic.APIConnectionError) as error:
            log.warning("Claude API request failed: %s", type(error).__name__)
            return None
        if response.stop_reason != "end_turn":
            log.info("Claude API stopped with %s", response.stop_reason)
            return None
        return "".join(block.text for block in response.content if block.type == "text").strip() or None


def client_from_env(model: str, max_chars: int) -> TextClient | None:
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not key:
        return None
    return AnthropicTextClient(key, model, max_chars)


def write(post_type: str, template_body: str, data: dict, *, use_ai: bool, client: TextClient | None,
          max_chars: int) -> Written:
    """The post's text: the AI's when allowed and it passes the check, else the template's."""
    if post_type in NEVER_AI_TYPES:
        # Never even offered to the AI, whatever the caller asked for.
        return Written(template_body, "template")
    if not use_ai or client is None:
        return Written(template_body, "template")
    user = (
        "DATA:\n" + json.dumps(data, ensure_ascii=False, sort_keys=True, default=str)
        + "\n\nDRAFT:\n" + template_body
    )
    try:
        text = client.complete(SYSTEM_PROMPT.format(max_chars=max_chars), user)
    except Exception as error:  # a broken client must never stop a run
        log.warning("AI writer failed: %s", type(error).__name__)
        return Written(template_body, "template", "The AI request failed; using the template.")
    if not text:
        return Written(template_body, "template", "The AI gave no usable answer; using the template.")
    text = " ".join(text.split())
    problems = check_ai_text(text, data, template_body, max_chars)
    if problems:
        return Written(template_body, "template", "AI text rejected: " + "; ".join(problems[:4]))
    return Written(text, "ai")
