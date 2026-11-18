"""config/trekly_posts.toml, read into plain dataclasses and checked on load."""

import tomllib
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from app.models.trekly_post import POST_TYPES

CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "trekly_posts.toml"
WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class TypeConfig:
    name: str
    enabled: bool
    days: tuple[str, ...]
    ai: bool
    expires_after_days: int
    options: dict[str, Any] = field(default_factory=dict)

    def runs_on(self, day: date) -> bool:
        return self.enabled and WEEKDAYS[day.weekday()] in self.days

    def get(self, key: str, default=None):
        return self.options.get(key, default)


@dataclass(frozen=True)
class Pacing:
    max_posts_per_day: int = 1
    busy_post_count: int = 6
    busy_window_hours: int = 24
    trail_cooldown_days: int = 30


@dataclass(frozen=True)
class AiConfig:
    enabled: bool = False
    model: str = "claude-opus-5-5"
    max_chars: int = 280


@dataclass(frozen=True)
class Feature:
    id: str
    text: str
    url: str | None = None


@dataclass(frozen=True)
class PostsConfig:
    timezone: str
    pacing: Pacing
    ai: AiConfig
    digest_enabled: bool
    types: dict[str, TypeConfig]
    features: tuple[Feature, ...] = ()

    def type(self, name: str) -> TypeConfig:
        return self.types[name]


def _type(name: str, raw: dict) -> TypeConfig:
    days = tuple(raw.get("days", WEEKDAYS))
    bad = [d for d in days if d not in WEEKDAYS]
    if bad:
        raise ConfigError(f"types.{name}.days: unknown day(s) {bad}")
    expires = int(raw.get("expires_after_days", 3))
    if expires < 1:
        raise ConfigError(f"types.{name}.expires_after_days must be at least 1")
    options = {k: v for k, v in raw.items() if k not in ("enabled", "days", "ai", "expires_after_days")}
    # Warnings and closures are quoted from the official source, never rewritten.
    ai = bool(raw.get("ai", False)) and name != "conditions"
    return TypeConfig(name=name, enabled=bool(raw.get("enabled", False)), days=days, ai=ai,
                      expires_after_days=expires, options=options)


def parse_config(raw: dict) -> PostsConfig:
    types_raw = raw.get("types", {})
    unknown = set(types_raw) - set(POST_TYPES)
    if unknown:
        raise ConfigError(f"Unknown post type(s): {sorted(unknown)}")
    types = {name: _type(name, types_raw.get(name, {})) for name in POST_TYPES}
    pacing = Pacing(**raw.get("pacing", {}))
    if pacing.max_posts_per_day < 1 or pacing.trail_cooldown_days < 0:
        raise ConfigError("pacing values out of range")
    ai = AiConfig(**raw.get("ai", {}))
    features = []
    seen = set()
    for item in raw.get("features", []):
        feature = Feature(id=str(item["id"]), text=str(item["text"]).strip(), url=item.get("url"))
        if not feature.text or feature.id in seen:
            raise ConfigError(f"features: empty text or repeated id {feature.id!r}")
        if feature.url is not None and not feature.url.startswith("/"):
            raise ConfigError(f"features.{feature.id}.url must be a site path like /journal")
        seen.add(feature.id)
        features.append(feature)
    return PostsConfig(
        timezone=raw.get("timezone", "America/Edmonton"),
        pacing=pacing,
        ai=ai,
        digest_enabled=bool(raw.get("digest", {}).get("enabled", True)),
        types=types,
        features=tuple(features),
    )


def load_config(path: Path = CONFIG_PATH) -> PostsConfig:
    with open(path, "rb") as handle:
        return parse_config(tomllib.load(handle))
