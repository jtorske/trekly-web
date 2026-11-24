"""Trekly Guide's "Am I ready?": readiness(profile, trail, on_date).

The verdict is the worst level any check gives:
- Not yet: per-day distance or gain above CEILING (130%) of their biggest day;
  ATES Challenging or Complex in avalanche season (Nov-May); a trail that
  isn't an official winter route, Dec-Mar.
- Stretch: distance or gain 100-130% of their biggest day; a high point more
  than HIGH_POINT_MARGIN above the highest they've been; a first overnight,
  or one much longer than they've done; a day longer than LONG_DAY_HOURS at
  their pace; no winter hikes logged before a winter outing; avalanche
  exposure not rated (Dec-Mar, or an alpine trail in Nov-May), with
  "check avalanche.ca".
- Ready: none of the above.

With fewer than MIN_HISTORY_HIKES hikes (or "Use my history" off) the
distance and gain checks give way to a gentle answer from the trail alone
(rules.GENTLE: its terrain grade against their stated experience) and a nudge to
log past hikes. The season and avalanche checks apply to everyone.

Every reason quotes real numbers from the trail and profile. Wording never
calls a trail or its conditions safe.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date
from typing import Iterable

from app.guide.estimate import (
    AVALANCHE_CANADA_URL,
    TrailFacts,
    format_hours,
    in_avalanche_season,
    is_shoulder,
    is_winter,
    naismith_hours,
)
from app.guide.profile import HikerProfile
from app.guide.recommend import GuideRequest, recommend
from app.guide.rules import (
    CEILING, NOT_YET, OVERNIGHT_JUMP, READY, SERIOUS_AVALANCHE, STRETCH, gentle_verdict, is_gentle,
)

ORDER = {READY: 0, STRETCH: 1, NOT_YET: 2}
LABELS = {READY: "Ready", STRETCH: "Stretch", NOT_YET: "Not yet"}

HIGH_POINT_MARGIN = 500  # m above the highest they've been
LONG_DAY_HOURS = 10.0


@dataclass(frozen=True)
class Reason:
    kind: str  # distance | gain | high_point | overnight | duration | season | avalanche | history
    level: str  # ready | stretch | not_yet | info
    text: str


@dataclass(frozen=True)
class Readiness:
    verdict: str
    reasons: tuple[Reason, ...]
    est_hours: float | None
    # True when the answer is from the trail alone (too little history).
    gentle: bool
    build_up: tuple[TrailFacts, ...] = ()
    avalanche_link: str | None = None

    @property
    def label(self) -> str:
        return LABELS[self.verdict]


def _km(value: float) -> str:
    return f"{value:.1f}".rstrip("0").rstrip(".") + " km"


def _worst(reasons: list[Reason]) -> str:
    levels = [r.level for r in reasons if r.level in ORDER]
    return max(levels, key=ORDER.get, default=READY)


def _measure(kind, value, best, best_trail, unit) -> Reason:
    label = {"distance": "distance", "gain": "climb"}[kind]
    shown = _km(value) if unit == "km" else f"{round(value)} m"
    best_shown = _km(best) if unit == "km" else f"{round(best)} m"
    where = f" ({best_trail})" if best_trail else ""
    ratio = value / best if best else 0
    if ratio > CEILING:
        return Reason(kind, NOT_YET, f"The {label} ({shown}) is {round((ratio - 1) * 100)}% more than your "
                                      f"biggest day so far, {best_shown}{where}. Build up first.")
    if ratio > 1.0:
        return Reason(kind, STRETCH, f"The {label} ({shown}) is {round((ratio - 1) * 100)}% more than your "
                                      f"biggest day, {best_shown}{where}.")
    return Reason(kind, READY, f"Within your range: {shown} here, and your biggest day is {best_shown}{where}.")


def _history_checks(profile: HikerProfile, trail: TrailFacts, winter: bool) -> list[Reason]:
    exp = profile.experience
    out: list[Reason] = []
    if winter and not trail.winter_measures_known():
        out.append(Reason("distance", "info", f"In winter the route ends at {trail.winter_route_ends.rstrip('.')}, "
                                              "so it's shorter than the summer trail."))
    else:
        if trail.per_day_km is not None:
            out.append(_measure("distance", trail.per_day_km, exp.max_distance_km, exp.max_distance_trail, "km"))
        if trail.per_day_gain is not None:
            out.append(_measure("gain", trail.per_day_gain, exp.max_gain_m, exp.max_gain_trail, "m"))
        else:
            out.append(Reason("gain", "info", "Trekly doesn't have this trail's elevation gain yet."))
    if trail.max_elevation_m and exp.max_high_point_m:
        above = trail.max_elevation_m - exp.max_high_point_m
        if above > HIGH_POINT_MARGIN:
            where = f" on {exp.max_high_point_trail}" if exp.max_high_point_trail else ""
            out.append(Reason("high_point", STRETCH, f"It tops out at {trail.max_elevation_m} m, {above} m higher "
                                                     f"than you've been ({exp.max_high_point_m} m{where})."))
    if trail.nights:
        if exp.overnight_count == 0:
            out.append(Reason("overnight", STRETCH, f"It's a {trail.nights}-night trip and you haven't logged an "
                                                    "overnight yet: a full pack makes every day harder."))
        elif trail.nights > exp.max_nights + OVERNIGHT_JUMP:
            out.append(Reason("overnight", STRETCH, f"{trail.nights} nights is well past your longest trip "
                                                    f"({exp.max_nights} nights)."))
    return out


def _gentle_checks(profile: HikerProfile, trail: TrailFacts) -> list[Reason]:
    level = profile.preferences.experience_level
    verdict = gentle_verdict(profile, trail)
    parts = []
    if trail.distance_km is not None:
        parts.append(_km(trail.distance_km))
    if trail.elevation_gain_m is not None:
        parts.append(f"{trail.elevation_gain_m} m of climbing")
    if trail.nights:
        parts.append(f"{trail.nights} {'night' if trail.nights == 1 else 'nights'}")
    stats = f" ({', '.join(parts)})" if parts else ""
    who = {
        "new": "someone newer to hiking",
        "few_seasons": "someone with a few seasons behind them",
        "seasoned": "a seasoned hiker",
    }.get(level, "most hikers")
    text = {
        READY: f"On its own, this {trail.terrain} trail{stats} is a good fit for {who}.",
        STRETCH: f"On its own, this {trail.terrain} trail{stats} is a stretch for {who}.",
        NOT_YET: f"On its own, this {trail.terrain} trail{stats} is a lot for {who}. Build up to it.",
    }[verdict]
    nudge = ("Log a few past hikes and Trekly can check it against your own history."
             if profile.preferences.use_history else
             "\"Use my history\" is off in Settings, so this is from the trail alone.")
    return [Reason("terrain", verdict, text), Reason("history", "info", nudge)]


def _season_checks(profile: HikerProfile, trail: TrailFacts, on_date: date) -> list[Reason]:
    out: list[Reason] = []
    if is_winter(on_date):
        if not trail.winter_activities:
            out.append(Reason("season", NOT_YET, "It isn't an official winter route: snow and avalanche terrain "
                                                 "make it a summer trail. Look again from late spring."))
        elif profile.has_history and profile.winter.winter_hikes == 0:
            out.append(Reason("season", STRETCH, "You haven't logged a winter hike yet: short days, cold and snow "
                                                 "make it slower going. Start with a short one."))
    elif is_shoulder(on_date) and trail.climate_zone == "alpine":
        out.append(Reason("season", "info", f"It's alpine: snow can linger up high in {on_date:%B}. "
                                            "Check the park's trail report before you go."))

    if in_avalanche_season(on_date):
        exposure = trail.avalanche_exposure
        if exposure in SERIOUS_AVALANCHE:
            out.append(Reason("avalanche", NOT_YET, f"Its avalanche terrain is rated {exposure.title()} (ATES): that "
                                                    "needs avalanche training and rescue gear. "
                                                    f"See {AVALANCHE_CANADA_URL}."))
        elif exposure == "simple":
            out.append(Reason("avalanche", "info", "Its avalanche terrain is rated Simple (ATES), which still "
                                                   f"means some exposure. Check {AVALANCHE_CANADA_URL} before you go."))
        elif exposure == "unknown" and (is_winter(on_date) or trail.climate_zone == "alpine"):
            out.append(Reason("avalanche", STRETCH, "Its avalanche exposure isn't rated. Check "
                                                    f"{AVALANCHE_CANADA_URL} and the park before you go."))
        elif exposure == "none" and is_winter(on_date):
            out.append(Reason("avalanche", "info", "It's officially rated as having no avalanche terrain. "
                                                   f"Conditions still change: {AVALANCHE_CANADA_URL}."))
    return out


def _duration(profile: HikerProfile, trail: TrailFacts, on_date: date) -> tuple[float | None, Reason | None]:
    if is_winter(on_date) and not trail.winter_measures_known():
        return None, None
    base = naismith_hours(trail.per_day_km, trail.per_day_gain)
    if base is None:
        return None, None
    hours = round(base * profile.pace.factor, 2)
    per = " a day" if trail.nights else ""
    if profile.pace.confidence == "low":
        how = "at a standard pace; add your times on trail to your hikes to tune it"
    else:
        how = f"at your pace, {profile.pace.factor:g}x the standard estimate"
    level = STRETCH if hours > LONG_DAY_HOURS else "info"
    text = f"About {format_hours(hours)}{per} of moving time for you ({how})."
    if level == STRETCH:
        text = f"That's a long day: about {format_hours(hours)}{per} of moving time for you."
    return hours, Reason("duration", level, text)


def build_up_trails(profile: HikerProfile, trail: TrailFacts, on_date: date,
                    catalogue: Iterable[TrailFacts], limit: int = 2) -> tuple[TrailFacts, ...]:
    """1-2 trails between what they've done and this one, nearby first."""
    km, gain = trail.per_day_km, trail.per_day_gain
    exp = profile.experience
    # Between their typical day and this trail: a real step, never past it.
    smaller = [
        t for t in catalogue
        if t.id != trail.id and t.per_day_km is not None and km is not None and t.per_day_km <= km
        and (gain is None or t.per_day_gain is None or t.per_day_gain <= gain)
        and (t.per_day_km >= exp.typical_distance_km or (t.per_day_gain or 0) >= exp.typical_gain_m)
        and t.nights <= trail.nights
    ]
    activity = "hike"
    if is_winter(on_date):
        wanted = [a for a in ("winter_hike", "snowshoe", "xc_ski") if a in trail.winter_activities]
        activity = wanted[0] if wanted else "winter_hike"
    # A build-up never adds avalanche exposure: recommend()'s snow-season rules apply.
    for province in (trail.province_code, None):
        for difficulty in ("push", "similar"):
            request = GuideRequest(on_date=on_date, difficulty=difficulty, province=province,
                                   activity=activity, limit=limit)
            found = recommend(profile, request, smaller).results
            if found:
                return tuple(r.trail for r in found)
    return ()


def readiness(profile: HikerProfile, trail: TrailFacts, on_date: date,
              catalogue: Iterable[TrailFacts] = ()) -> Readiness:
    winter = is_winter(on_date)
    gentle = is_gentle(profile)
    reasons = _gentle_checks(profile, trail) if gentle else _history_checks(profile, trail, winter)
    if trail.id in profile.hiked_trail_ids:
        reasons.insert(0, Reason("history", "info", "You've hiked this one before."))
    reasons += _season_checks(profile, trail, on_date)
    hours, duration = _duration(profile, trail, on_date)
    if duration is not None:
        reasons.append(duration)
    verdict = _worst(reasons)
    avalanche_link = AVALANCHE_CANADA_URL if any(r.kind == "avalanche" for r in reasons) else None
    result = Readiness(verdict=verdict, reasons=tuple(reasons), est_hours=hours, gentle=gentle,
                       avalanche_link=avalanche_link)
    if verdict != READY:
        result = replace(result, build_up=build_up_trails(profile, trail, on_date, catalogue))
    return result
