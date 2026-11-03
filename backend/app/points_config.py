"""Every number in the points and rank system, in one place to tune.

Points come from the Trail Journal (hike logs) and from milestones, which
also reward planning and gear (app/milestones_config.py, by tier). They're
computed on the server (app/points.py). Distance and elevation don't score
on their own: too many trails are missing them. Changing a value here
re-ranks everyone on their next request; nothing is stored.

Catalogue check (2026-11-02, the final 50 milestones; the 100 active trails
in 49 parks or regions, undated hikes, so no calendar, journal, planning or
gear milestones): every trail is 4,965 points (4,070 for trails, nights and
regions, plus 895 from 30 milestones); 15 random trails come to about 985
(most land between 740 and 1,205), so Ridge Walker; Mountain Legend at
3,200 takes about 59 trails (thresholds retuned 2026-11-03). The calendar,
journal, planning and gear milestones add up to 380 more. Long hauler,
Thousand-kilometre club and Loop de loop can't be earned until the
catalogue has more lengths and route types.
"""

# Each hiked trail, by its terrain difficulty.
TRAIL_POINTS = {
    "easy": 10,
    "moderate": 20,
    "difficult": 35,
    "extreme": 50,
}

# Overnight trips: per night of the trail's typical duration.
POINTS_PER_NIGHT = 10

# The first trail in each park or region (so per distinct region).
NEW_REGION_POINTS = 15

# Each milestone earned scores by its tier: TIER_POINTS in
# app/milestones_config.py (bronze 10, silver 25, gold 50).

# (points needed, rank name), lowest first. The first must be 0.
RANKS = (
    (0, "Trailhead Rookie"),
    (50, "Day Tripper"),
    (250, "Switchback Regular"),
    (600, "Ridge Walker"),
    (1200, "Backcountry Ranger"),
    (2000, "Summit Seeker"),
    (3200, "Mountain Legend"),
)
