"""Every number in the points and rank system, in one place to tune.

Points come from the Trail Journal (hike logs) and from milestones, which
also reward planning and gear (app/milestones_config.py, by tier). They're
computed on the server (app/points.py). Distance and elevation don't score
on their own: too many trails are missing them. Changing a value here
re-ranks everyone on their next request; nothing is stored.

Catalogue check (2026-11-02, the 100 active trails in 49 parks or regions,
undated hikes, so no seasonal, journal, planning or gear milestones):
every trail is 4,730 points (4,070 for trails, nights and regions, plus
660 from 24 milestones); 15 random trails come to about 945 (most land
between 705 and 1,160); Mountain Legend at 2,800 takes about 54
trails (60 average 3,090). The milestones not tied to which trails were
hiked add up to 250 more.
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
    (1100, "Backcountry Ranger"),
    (1800, "Summit Seeker"),
    (2800, "Mountain Legend"),
)
