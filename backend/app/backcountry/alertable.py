"""Which campgrounds can take an availability alert, and for how many people.

One place for the rules, used by the alert endpoints (app/routers/me_alerts.py)
and by the trail campground list (app/routers/trails.py), which passes the
answer on so the alert buttons and forms match what the API accepts.

An alert means "email me when this opens up", so it only makes sense where
a site can fill up and a hiker can then book it online:

- Horse grazing camps aren't part of hiking trips.
- Trail permits (West Coast Trail, Gros Morne) are a daily start quota, not
  nightly campsites; permit alerts are a separate, later feature.
- Random-camping zones with Parks Canada's 1000 quota never fill up.
- Cabins and shelters: availability requests for them work (recorded in
  tests/fixtures/parks_canada_availability_types.json), but no response has
  shown one as available yet, so an opening can't be confirmed. Off until a
  recorded response shows status 0 for one.
- Sites Parks Canada books only in person or by phone (NOT_ONLINE).

Hut and lodge beds aren't in Parks Canada's system at all; the "<Hut>
Random" zones there are camping quotas of 1000, covered above.
"""

from app.models.backcountry import BackcountrySite

UNLIMITED_QUOTA = 1000
UNCONFIRMED_KINDS = frozenset({"cabin", "shelter"})

# provider_resource_id -> why. From Parks Canada's own site descriptions.
NOT_ONLINE = {
    "-2147482971": "Parks Canada books Paradise Valley only within 24 hours of your trip, in person or by phone.",
    "-2147483107": "Parks Canada issues Hector Lake permits only in person in Lake Louise or by phone.",
}


def alert_block(site: BackcountrySite) -> str | None:
    """Why this campground can't take an alert, or None if it can."""
    if site.kind == "horse_camp":
        return "Alerts aren't offered for horse camps."
    if site.kind == "trail_permit":
        return "Alerts aren't offered for trail permits yet."
    if site.kind == "random_zone" and (site.reservable_capacity or 0) >= UNLIMITED_QUOTA:
        return "Random camping here has no quota to fill up, so there's nothing to alert you about."
    if site.kind in UNCONFIRMED_KINDS:
        return "Alerts aren't offered for cabins and shelters yet."
    if site.provider_resource_id in NOT_ONLINE:
        return NOT_ONLINE[site.provider_resource_id]
    return None


def party_problem(site: BackcountrySite, party_size: int) -> str | None:
    """Parks Canada's "Maximum Group Size" for the site, if the party is over it."""
    limit = site.max_group_size
    if limit and party_size > limit:
        return f"{site.name} takes at most {limit} {'person' if limit == 1 else 'people'} per booking."
    return None
