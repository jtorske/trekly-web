"""Trail Journal rules the server needs: which milestone badges are earned.

Mirrors computeMilestones in frontend/lib/journal.ts, which draws the
journal; the server decides what can be featured (and, later, scored), so
a browser can never claim a badge it hasn't earned.
"""

from collections.abc import Iterable

from app.models.trail import Trail

MILESTONES = ("first-hike", "first-overnight", "five-parks", "hundred-km")
PARKS_GOAL = 5
CENTURY_KM = 100


def earned_milestones(trails: Iterable[Trail]) -> set[str]:
    """The milestones earned by hiking these trails (one per hike log)."""
    trails = list(trails)
    earned = set()
    if trails:
        earned.add("first-hike")
    if any((trail.typical_duration_nights or 0) >= 1 for trail in trails):
        earned.add("first-overnight")
    if len({trail.region for trail in trails}) >= PARKS_GOAL:
        earned.add("five-parks")
    # Only trails with a known distance count towards the total.
    if sum(float(trail.distance_km or 0) for trail in trails) >= CENTURY_KM:
        earned.add("hundred-km")
    return earned
