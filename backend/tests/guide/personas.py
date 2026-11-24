"""Persona evals for Trekly Guide: who they are, what they ask, what must hold.

Each persona has a Trail Journal (real catalogue slugs, optional dates and
times on trail), stated preferences, one planner request, and expected
properties. test_personas.py runs every persona against the real catalogue
and also applies the checks every answer must pass (trails exist, the 130%
ceiling, winter avalanche rules, dog rules, hiked trails excluded,
readiness verdicts that follow the rules).

`readiness` lists (slug, date, expected verdict) for "Am I ready?" checks.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

SUMMER = date(2027, 7, 10)  # a Saturday
FALL = date(2027, 9, 18)
WINTER = date(2027, 1, 16)
MAY = date(2027, 5, 15)


@dataclass(frozen=True)
class Persona:
    name: str
    description: str
    # (slug, hiked_on, minutes on trail)
    hikes: tuple = ()
    prefs: dict = field(default_factory=dict)
    home_province: str | None = None
    saved: tuple[str, ...] = ()
    request: dict = field(default_factory=dict)
    # Properties of the answer (see test_personas.check_expectations):
    #   min_results / max_results, province, regions_park, terrain_in,
    #   activity, empty_note (substring), scenery, notes_contain,
    #   pace_between, basis, verdict_at_least
    expect: dict = field(default_factory=dict)
    readiness: tuple = ()


D = date

BEGINNER_HIKES = (
    ("grassi-lakes", D(2026, 6, 6), 75),
    ("tunnel-mountain", D(2026, 6, 20), 100),
    ("lake-agnes-tea-house", D(2026, 7, 4), 160),
    ("maligne-canyon", D(2026, 8, 1), 70),
)
INTERMEDIATE_HIKES = (
    ("ha-ling-peak", D(2026, 6, 13), 210),
    ("johnston-canyon-to-the-ink-pots", D(2026, 6, 27), 230),
    ("prairie-mountain", D(2026, 7, 11), 190),
    ("sulphur-skyline", D(2026, 7, 25), 200),
    ("rawson-lake", D(2026, 8, 8), 150),
    ("chester-lake", D(2026, 8, 22), 170),
)
EXPERT_HIKES = (
    ("panorama-ridge", D(2026, 7, 3), 560),
    ("mount-yamnuska", D(2026, 7, 17), 300),
    ("tent-ridge-horseshoe", D(2026, 7, 31), 330),
    ("crypt-lake", D(2026, 8, 14), 380),
    ("iceline-trail", D(2026, 8, 28), 300),
    ("skyline-trail", D(2026, 9, 5), None),
    ("berg-lake-trail", D(2025, 8, 10), None),
)
ONTARIO_HIKES = (
    ("lions-head", D(2026, 6, 6), 150),
    ("cyprus-lake-to-the-grotto", D(2026, 6, 20), 80),
    ("centennial-ridges", D(2026, 7, 4), 200),
    ("top-of-the-giant", D(2026, 8, 1), 420),
)

PERSONAS: list[Persona] = [
    # --- beginners ---------------------------------------------------------
    Persona("beginner_similar", "Four short Rockies hikes, wants more of the same",
            hikes=BEGINNER_HIKES, prefs={"experience_level": "new"}, home_province="AB",
            request={"on_date": SUMMER, "difficulty": "similar"},
            expect={"min_results": 3, "basis": "history"},
            readiness=(("skyline-trail", SUMMER, "not_yet"), ("grassi-lakes", SUMMER, "ready"))),
    Persona("beginner_easier", "Wants an easy day", hikes=BEGINNER_HIKES,
            prefs={"experience_level": "new"}, request={"on_date": SUMMER, "difficulty": "easier"},
            expect={"min_results": 3, "terrain_in": ("easy", "moderate", "difficult")}),
    Persona("beginner_push", "Ready to push a bit", hikes=BEGINNER_HIKES, prefs={"experience_level": "new"},
            request={"on_date": SUMMER, "difficulty": "push"}, expect={"min_results": 2},
            readiness=(("sentinel-pass-via-larch-valley", SUMMER, "not_yet"),)),
    # --- intermediates -----------------------------------------------------
    Persona("intermediate_similar", "Six Kananaskis/Banff day hikes", hikes=INTERMEDIATE_HIKES,
            prefs={"experience_level": "few_seasons"}, home_province="AB",
            request={"on_date": SUMMER, "difficulty": "similar"}, expect={"min_results": 3},
            readiness=(("ha-ling-peak", SUMMER, "ready"), ("gros-morne-mountain", SUMMER, "not_yet"),
                       ("panorama-ridge", SUMMER, "stretch"),
                       ("iceline-trail", SUMMER, None))),
    Persona("intermediate_push", "Wants a step up", hikes=INTERMEDIATE_HIKES,
            prefs={"experience_level": "few_seasons"}, request={"on_date": SUMMER, "difficulty": "push"},
            expect={"min_results": 3}),
    Persona("intermediate_easier", "Recovery day", hikes=INTERMEDIATE_HIKES,
            prefs={"experience_level": "few_seasons"}, request={"on_date": SUMMER, "difficulty": "easier"},
            expect={"min_results": 3}),
    Persona("intermediate_half_day", "Half day only", hikes=INTERMEDIATE_HIKES,
            request={"on_date": SUMMER, "length": "half_day"}, expect={"min_results": 3}),
    # --- experts -----------------------------------------------------------
    Persona("expert_push", "Big days and multi-day trips", hikes=EXPERT_HIKES,
            prefs={"experience_level": "seasoned"}, request={"on_date": SUMMER, "difficulty": "push"},
            expect={"min_results": 1}),
    Persona("expert_overnight", "Next backpacking trip", hikes=EXPERT_HIKES,
            prefs={"experience_level": "seasoned", "hiking_style": "overnight"},
            request={"on_date": SUMMER, "length": "overnight"}, expect={"min_results": 3},
            readiness=(("west-coast-trail", SUMMER, None),)),
    Persona("expert_full_day", "Full day out", hikes=EXPERT_HIKES,
            request={"on_date": SUMMER, "length": "full_day"}, expect={"min_results": 2}),
    # --- no history --------------------------------------------------------
    Persona("new_no_history", "Signed up, said 'new', logged nothing", prefs={"experience_level": "new"},
            request={"on_date": SUMMER}, expect={"min_results": 3, "basis": "stated"},
            readiness=(("grassi-lakes", SUMMER, "ready"), ("panorama-ridge", SUMMER, "not_yet"),
                       ("joffre-lakes", SUMMER, "stretch"))),
    Persona("seasoned_no_history", "Experienced but hasn't logged anything",
            prefs={"experience_level": "seasoned"}, request={"on_date": SUMMER, "difficulty": "push"},
            expect={"min_results": 3, "basis": "stated"},
            readiness=(("panorama-ridge", SUMMER, "ready"), ("west-coast-trail", SUMMER, "stretch"))),
    Persona("guest", "Signed out, no answers", request={"on_date": SUMMER},
            expect={"min_results": 3, "basis": "stated"}),
    Persona("one_hike_only", "One logged hike: still gentle", hikes=(("ha-ling-peak", D(2026, 7, 1), 200),),
            prefs={"experience_level": "few_seasons"}, request={"on_date": SUMMER},
            expect={"min_results": 3, "basis": "stated"},
            readiness=(("crypt-lake", SUMMER, "stretch"),)),
    Persona("history_off", "Big history but 'Use my history' is off", hikes=EXPERT_HIKES,
            prefs={"experience_level": "new", "use_history": False},
            request={"on_date": SUMMER, "difficulty": "push"}, expect={"min_results": 2, "basis": "stated"},
            readiness=(("panorama-ridge", SUMMER, "not_yet"),)),
    # --- winter ------------------------------------------------------------
    Persona("winter_beginner_snowshoe", "First snowshoe, default avalanche avoidance",
            hikes=BEGINNER_HIKES, prefs={"experience_level": "new"},
            request={"on_date": WINTER, "activity": "snowshoe"},
            expect={"min_results": 1, "activity": "snowshoe", "ates_in": ("none", "simple")},
            readiness=(("wilcox-pass", WINTER, "not_yet"), ("lake-agnes-tea-house", WINTER, "not_yet"),
                       ("tunnel-mountain", WINTER, "stretch"))),
    Persona("winter_snowshoe_avoid_off", "Knows avalanche basics, avoid turned off",
            hikes=INTERMEDIATE_HIKES, request={"on_date": WINTER, "activity": "snowshoe", "avoid_avalanche": False},
            expect={"min_results": 1, "activity": "snowshoe"},
            readiness=(("chester-lake", WINTER, None),)),
    Persona("winter_hike", "Winter hike, avoid off", hikes=INTERMEDIATE_HIKES,
            request={"on_date": WINTER, "activity": "hike", "avoid_avalanche": False},
            expect={"min_results": 1, "activity": "winter_hike"}),
    Persona("winter_xc_ski", "Cross-country ski", hikes=INTERMEDIATE_HIKES,
            request={"on_date": WINTER, "activity": "xc_ski", "avoid_avalanche": False},
            expect={"min_results": 1, "activity": "xc_ski"}),
    Persona("winter_hiker_with_winter_history", "Has winter hikes logged", prefs={"experience_level": "few_seasons"},
            hikes=(*INTERMEDIATE_HIKES, ("johnston-canyon-to-the-ink-pots", D(2026, 1, 10), 240)),
            request={"on_date": WINTER, "activity": "hike", "avoid_avalanche": False}, expect={"min_results": 1},
            readiness=(("valley-of-the-five-lakes", WINTER, None),)),
    Persona("snowshoe_in_summer", "Asks for snowshoeing in July", hikes=INTERMEDIATE_HIKES,
            request={"on_date": SUMMER, "activity": "snowshoe"}, expect={"max_results": 0, "notes_contain": "Dec-Mar"}),
    # --- dogs --------------------------------------------------------------
    Persona("dog_owner", "Always brings the dog", hikes=INTERMEDIATE_HIKES, prefs={"hikes_with_dog": True},
            request={"on_date": SUMMER, "dog": True}, expect={"min_results": 3}),
    Persona("dog_owner_bc", "Dog, BC only", hikes=INTERMEDIATE_HIKES,
            request={"on_date": SUMMER, "dog": True, "province": "BC"}, expect={"province": "BC"}),
    # --- places ------------------------------------------------------------
    Persona("out_of_province", "Ontario hiker visiting Alberta", hikes=ONTARIO_HIKES, home_province="ON",
            request={"on_date": SUMMER, "province": "AB"}, expect={"min_results": 3, "province": "AB"}),
    Persona("ontario_local", "Close to home", hikes=ONTARIO_HIKES, home_province="ON",
            request={"on_date": SUMMER, "province": "ON"}, expect={"min_results": 2, "province": "ON"}),
    Persona("quebec", "Québec, no history", prefs={"experience_level": "few_seasons"}, home_province="QC",
            request={"on_date": FALL, "province": "QC"}, expect={"min_results": 3, "province": "QC"}),
    Persona("newfoundland", "Gros Morne trip", hikes=INTERMEDIATE_HIKES,
            request={"on_date": SUMMER, "province": "NL"}, expect={"min_results": 1, "province": "NL"}),
    Persona("banff_fan", "Only Banff", hikes=INTERMEDIATE_HIKES, prefs={"favourite_regions": ("banff",)},
            request={"on_date": SUMMER, "regions": ("banff",)},
            expect={"min_results": 2, "regions_park": "Banff National Park"}),
    # --- other -------------------------------------------------------------
    Persona("repeat_ok", "Happy to repeat favourites", hikes=INTERMEDIATE_HIKES,
            request={"on_date": SUMMER, "include_hiked": True}, expect={"min_results": 3}),
    Persona("first_overnight", "Day hiker trying an overnight", hikes=INTERMEDIATE_HIKES,
            request={"on_date": SUMMER, "length": "overnight"}, expect={"min_results": 1},
            readiness=(("garibaldi-lake", SUMMER, "stretch"),)),
    Persona("shoulder_season", "Mid-May, alpine still snowy", hikes=INTERMEDIATE_HIKES,
            request={"on_date": MAY}, expect={"min_results": 3}),
    Persona("fast_short", "Fast hiker, short outing", prefs={"experience_level": "few_seasons"},
            hikes=tuple((slug, day, int(minutes * 0.7)) for slug, day, minutes in INTERMEDIATE_HIKES),
            request={"on_date": SUMMER, "length": "short"},
            expect={"min_results": 2, "pace_between": (0.6, 0.95)}),
    Persona("slow_full_day", "Slow and steady, full day", prefs={"experience_level": "few_seasons"},
            hikes=tuple((slug, day, int(minutes * 1.5)) for slug, day, minutes in INTERMEDIATE_HIKES),
            request={"on_date": SUMMER, "length": "full_day"},
            expect={"min_results": 1, "pace_between": (1.3, 1.6)}),
    Persona("lake_lover", "Lakes, please", hikes=INTERMEDIATE_HIKES, prefs={"scenery": ("lakes",)},
            request={"on_date": SUMMER}, expect={"min_results": 3, "scenery": "lakes"}),
    Persona("saved_list", "Has saved trails", hikes=INTERMEDIATE_HIKES, saved=("galatea-lakes",),
            request={"on_date": SUMMER}, expect={"min_results": 3}),
]
