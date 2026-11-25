"""The tools the chat model may call: thin wrappers over the Phase 1 engine.

The backend runs them, never the model. Every argument is validated with
Pydantic (extra keys refused); a bad call goes back to the model as an
error it can correct. Each tool returns:
- `data`: a compact JSON-able dict for the model (trail facts and the
  hiker's numbers only: no names, usernames, emails or ids);
- `cards`: what the chat panel shows (real Trekly trail and readiness cards);
- `trail_names`: every trail name in the result, so chat.py can check the
  reply names no trail the tools didn't return.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from app.guide.estimate import (
    AVALANCHE_CANADA_URL,
    TrailFacts,
    format_hours,
    in_avalanche_season,
    is_winter,
    this_weekend,
)
from app.guide.profile import HikerProfile
from app.guide.readiness import LABELS, readiness
from app.guide.recommend import AVALANCHE_LABELS, GuideRequest, dog_note, recommend
from app.preferences import REGION_SLUGS
from app.provinces import PROVINCE_CODES

SEASONS = {12: "winter", 1: "winter", 2: "winter", 3: "spring", 4: "spring", 5: "spring",
           6: "summer", 7: "summer", 8: "summer", 9: "fall", 10: "fall", 11: "fall"}


class ToolError(ValueError):
    """A call the model can fix: bad arguments, an unknown trail."""


@dataclass
class ToolContext:
    profile: HikerProfile
    # Live trails as the Guide sees them, and their database rows (for cards).
    facts: list[TrailFacts]
    rows: dict
    today: date
    db: Any = None
    # Trails already shown in this conversation ("show me more").
    shown_ids: set = field(default_factory=set)


@dataclass
class ToolOutput:
    data: dict
    cards: list[dict] = field(default_factory=list)
    trail_names: set[str] = field(default_factory=set)


# ---- arguments ------------------------------------------------------------

class _Args(BaseModel):
    model_config = ConfigDict(extra="forbid")


DateArg = Field(default=None, max_length=12, description="YYYY-MM-DD, or 'this_weekend'. Omit for this weekend.")


class SearchTrailsArgs(_Args):
    date: str | None = DateArg
    difficulty: Literal["easier", "similar", "push"] | None = None
    length: Literal["short", "half_day", "full_day", "overnight"] | None = None
    province: str | None = Field(default=None, description="Two-letter code, e.g. AB, BC, ON.")
    regions: list[str] = Field(default_factory=list, max_length=5, description="Park slugs, e.g. banff, jasper.")
    dog: bool = False
    activity: Literal["hike", "winter_hike", "snowshoe", "xc_ski"] = "hike"
    avoid_avalanche: bool | None = None
    include_hiked: bool = False
    more: bool = Field(default=False, description="True for 'show me more': skips trails already shown.")

    @field_validator("province")
    @classmethod
    def _province(cls, value):
        if value is not None and value.upper() not in PROVINCE_CODES:
            raise ValueError("unknown province code")
        return value.upper() if value else value

    @field_validator("regions")
    @classmethod
    def _regions(cls, values):
        unknown = [v for v in values if v not in REGION_SLUGS]
        if unknown:
            raise ValueError(f"unknown regions {unknown}; use: {', '.join(REGION_SLUGS)}")
        return values


class TrailArgs(_Args):
    trail: str = Field(min_length=2, max_length=80, description="The trail's slug or exact name from a tool result.")


class TrailDateArgs(TrailArgs):
    date: str | None = DateArg


class NoArgs(_Args):
    pass


# ---- helpers --------------------------------------------------------------

def resolve_date(value: str | None, today: date) -> date:
    if value in (None, "", "this_weekend"):
        return this_weekend(today)
    try:
        day = date.fromisoformat(value)
    except ValueError:
        raise ToolError("date must be YYYY-MM-DD or this_weekend") from None
    if day < today or (day - today).days > 366:
        raise ToolError("date must be between today and a year from now")
    return day


def resolve_trail(ctx: ToolContext, query: str) -> TrailFacts:
    q = query.strip().lower()
    for trail in ctx.facts:
        if trail.slug == q or trail.name.lower() == q:
            return trail
    matches = [t for t in ctx.facts if q in t.name.lower()]
    if len(matches) == 1:
        return matches[0]
    if matches:
        raise ToolError("several trails match: " + "; ".join(f"{t.name} ({t.slug})" for t in matches[:5]))
    raise ToolError("no Trekly trail matches; use search_trails to find one")


def _trail_summary(trail: TrailFacts) -> dict:
    return {
        "slug": trail.slug,
        "name": trail.name,
        "province": trail.province_code,
        "park": trail.park_name,
        "terrain": trail.terrain,
        "distance_km": trail.distance_km,
        "gain_m": trail.elevation_gain_m,
        "high_point_m": trail.max_elevation_m,
        "nights": trail.nights,
    }


def _trail_card(ctx: ToolContext, trail: TrailFacts, extra: dict) -> dict:
    from app.schemas.trail import TrailListItemOut

    row = ctx.rows.get(trail.id)
    return {"type": "trail", "trail": TrailListItemOut.model_validate(row).model_dump(mode="json") if row else None,
            **extra}


# ---- tools ----------------------------------------------------------------

def search_trails(ctx: ToolContext, args: SearchTrailsArgs) -> ToolOutput:
    on_date = resolve_date(args.date, ctx.today)
    request = GuideRequest(
        on_date=on_date, difficulty=args.difficulty or "similar", length=args.length, province=args.province,
        regions=tuple(args.regions), dog=args.dog, activity=args.activity, avoid_avalanche=args.avoid_avalanche,
        include_hiked=args.include_hiked, exclude_ids=frozenset(ctx.shown_ids) if args.more else frozenset(), limit=3,
    )
    result = recommend(ctx.profile, request, ctx.facts)
    trails, cards = [], []
    for r in result.results:
        est = format_hours(r.est_hours) if r.est_hours is not None else None
        trails.append({
            **_trail_summary(r.trail),
            "est_time_for_them": est,
            "reasons": list(r.reasons),
            "avalanche_terrain": AVALANCHE_LABELS[r.trail.avalanche_exposure] if request.snow_season else None,
            "dog_note": r.dog_note,
        })
        cards.append(_trail_card(ctx, r.trail, {
            "reasons": list(r.reasons), "est_label": est, "dog_note": r.dog_note, "dog_policy": r.trail.dog_policy,
        }))
        ctx.shown_ids.add(r.trail.id)
    return ToolOutput(
        data={"date": on_date.isoformat(), "winter": request.winter, "results": trails, "notes": result.notes,
              **({"avalanche_link": AVALANCHE_CANADA_URL} if request.snow_season else {})},
        cards=cards,
        trail_names={r.trail.name for r in result.results},
    )


def get_trail(ctx: ToolContext, args: TrailArgs) -> ToolOutput:
    trail = resolve_trail(ctx, args.trail)
    data = {
        **_trail_summary(trail),
        "description": (trail.description or "")[:300] or None,
        "winter_activities": list(trail.winter_activities),
        "avalanche_terrain": AVALANCHE_LABELS[trail.avalanche_exposure],
        "dogs": {"on_leash": "allowed on a leash", "not_allowed": "not allowed"}.get(trail.dog_policy, "check dog rules"),
    }
    return ToolOutput(data=data, cards=[_trail_card(ctx, trail, {"reasons": [], "est_label": None,
                                                                   "dog_note": dog_note(trail),
                                                                   "dog_policy": trail.dog_policy})],
                      trail_names={trail.name})


def check_readiness(ctx: ToolContext, args: TrailDateArgs) -> ToolOutput:
    trail = resolve_trail(ctx, args.trail)
    on_date = resolve_date(args.date, ctx.today) if args.date else ctx.today
    answer = readiness(ctx.profile, trail, on_date, ctx.facts)
    est = format_hours(answer.est_hours) if answer.est_hours is not None else None
    card = {
        "type": "readiness",
        "slug": trail.slug,
        "name": trail.name,
        "verdict": answer.verdict,
        "label": answer.label,
        "date": on_date.isoformat(),
        "est_label": est,
        "reasons": [{"level": r.level, "text": r.text} for r in answer.reasons],
        "build_up": [{"slug": t.slug, "name": t.name} for t in answer.build_up],
        "avalanche_link": answer.avalanche_link,
    }
    return ToolOutput(
        data={"trail": trail.name, "date": on_date.isoformat(), "verdict": LABELS[answer.verdict],
              "reasons": [r.text for r in answer.reasons if r.level != "info"][:4],
              "est_moving_time": est, "build_up_first": [t.name for t in answer.build_up],
              **({"avalanche_link": answer.avalanche_link} if answer.avalanche_link else {})},
        cards=[card],
        trail_names={trail.name, *(t.name for t in answer.build_up)},
    )


def get_conditions(ctx: ToolContext, args: TrailDateArgs) -> ToolOutput:
    from app.models.trail import Trail
    from app.models.trail_seasonal_condition import TrailSeasonalCondition

    trail = resolve_trail(ctx, args.trail)
    on_date = resolve_date(args.date, ctx.today) if args.date else ctx.today
    season = SEASONS[on_date.month]
    data: dict = {"trail": trail.name, "date": on_date.isoformat(), "season": season,
                  "live_forecast": "On the trail page (Open-Meteo)."}
    row = ctx.rows.get(trail.id)
    if ctx.db is not None:
        condition = ctx.db.query(TrailSeasonalCondition).filter_by(trail_id=trail.id, season=season).first()
        if condition is not None:
            data["typical_for_season"] = {
                "avg_low_c": float(condition.avg_low_c), "avg_high_c": float(condition.avg_high_c),
                "precip": condition.precip_likelihood, "high_wind": condition.high_wind,
            }
        if row is None:
            row = ctx.db.get(Trail, trail.id)
    snowy = is_winter(on_date) or in_avalanche_season(on_date)
    if snowy:
        data["winter_activities"] = list(trail.winter_activities) or "not an official winter route"
        data["avalanche_terrain"] = AVALANCHE_LABELS[trail.avalanche_exposure]
        data["avalanche_link"] = AVALANCHE_CANADA_URL
        for field in ("winter_access_note", "winter_notes", "winter_report_url"):
            value = getattr(row, field, None) if row is not None else None
            if value:
                data[field] = value
    return ToolOutput(data=data, trail_names={trail.name})


def get_my_profile_summary(ctx: ToolContext, args: NoArgs) -> ToolOutput:
    """Numbers and categories only: never names, ids or anything they wrote."""
    p = ctx.profile
    exp = p.experience
    return ToolOutput(data={
        "based_on": "their Trail Journal" if p.has_history else "their stated experience",
        "hikes_logged": exp.hike_count,
        "biggest_day_km": exp.max_distance_km,
        "biggest_day_gain_m": exp.max_gain_m,
        "highest_point_m": exp.max_high_point_m,
        "typical_km": exp.typical_distance_km,
        "typical_gain_m": exp.typical_gain_m,
        "overnights_logged": exp.overnight_count,
        "winter_hikes_logged": p.winter.winter_hikes,
        "pace_factor": p.pace.factor,
        "pace_confidence": p.pace.confidence,
        "home_province": p.home_province if p.home_province != "outside" else None,
        "experience_level": p.preferences.experience_level,
        "hiking_style": p.preferences.hiking_style,
        "hikes_with_dog": p.preferences.hikes_with_dog,
        "scenery": list(p.preferences.scenery),
    })


TOOLS = {
    "search_trails": (search_trails, SearchTrailsArgs,
                      "Find Trekly trails that fit. Returns up to 3 ranked trails with reasons built from real numbers."),
    "get_trail": (get_trail, TrailArgs, "Facts about one Trekly trail (distance, gain, high point, terrain, rules)."),
    "check_readiness": (check_readiness, TrailDateArgs,
                        "'Am I ready?': Ready / Stretch / Not yet for this hiker on a trail, with reasons."),
    "get_conditions": (get_conditions, TrailDateArgs,
                       "Typical season conditions, winter use and avalanche terrain rating for a trail and date."),
    "get_my_profile_summary": (get_my_profile_summary, NoArgs,
                               "The hiker's numbers: biggest day, typical hike, pace, preferences."),
}


def tool_specs() -> list[dict]:
    specs = []
    for name, (_, model, description) in TOOLS.items():
        schema = model.model_json_schema()
        schema.pop("title", None)
        specs.append({"type": "function", "function": {"name": name, "description": description, "parameters": schema}})
    return specs


def run_tool(ctx: ToolContext, name: str, raw_arguments: str) -> ToolOutput:
    """Validate and run one call. Raises ToolError for anything the model got wrong."""
    if name not in TOOLS:
        raise ToolError(f"unknown tool {name!r}")
    function, model, _ = TOOLS[name]
    try:
        payload = json.loads(raw_arguments or "{}")
    except ValueError:
        raise ToolError("arguments must be a JSON object") from None
    if not isinstance(payload, dict):
        raise ToolError("arguments must be a JSON object")
    try:
        args = model.model_validate(payload)
    except ValidationError as error:
        problems = "; ".join(f"{'.'.join(map(str, e['loc'])) or 'arguments'}: {e['msg']}" for e in error.errors()[:3])
        raise ToolError(f"invalid arguments: {problems}") from None
    return function(ctx, args)
