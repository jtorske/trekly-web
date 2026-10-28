"""Every number in the points and rank system, in one place to tune.

Points come only from the Trail Journal (hike logs) and are computed on the
server (app/points.py). Distance and elevation don't count yet: too many
trails are missing them. Changing a value here re-ranks everyone on their
next request; nothing is stored.

Catalogue check (2026-10-28, 116 trails in 60 parks or regions): every
trail is 5,410 points; 15 random trails come to about 820 (most land
between 665 and 995); Mountain Legend at 2,800 is roughly 45-50 trails.
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

# Each milestone badge earned (app/journal.py).
MILESTONE_POINTS = 25

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
