""""Trekly picks": suggestions mixed into a quiet Activity feed.

While real hikers have shared fewer than SPARSE_BELOW posts in the last
week, the feed shows a few picks between posts, styled as picks, never as
anyone's post: a trending trail, a trail that just got a photo, and a
seasonal suggestion. Once real activity passes the threshold, `sparse` is
False and the page stops showing them. Demo and official accounts' posts
don't count towards it (app/account_labels.py).

Every pick is made from catalogue data alone; none says anything about
who did what.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.account_labels import real_user
from app.activity import visible_where, _joined
from app.models.activity import ActivityPost
from app.models.trail import Trail
from app.models.trail_photo import TrailPhoto
from app.models.trail_seasonal_condition import TrailSeasonalCondition

SPARSE_BELOW = 10
SPARSE_DAYS = 7
NEW_PHOTO_DAYS = 30

PickKind = Literal["trending", "new_photos", "seasonal"]

SEASONS = {12: "winter", 1: "winter", 2: "winter", 3: "spring", 4: "spring", 5: "spring",
           6: "summer", 7: "summer", 8: "summer", 9: "fall", 10: "fall", 11: "fall"}
SEASON_TEXT = {
    "winter": ("A winter pick", "Short days and cold nights: this one stays among the milder trails in winter."),
    "spring": ("A spring pick", "Snow lingers up high in spring. This trail is one of the first to warm up."),
    "summer": ("A summer pick", "Long days and open passes: a good one for the height of summer."),
    "fall": ("A fall pick", "Cool air and changing colours. This trail holds its warmth into the fall."),
}


@dataclass(frozen=True)
class Pick:
    kind: PickKind
    title: str
    text: str
    trail: Trail


def real_posts_this_week(db: Session, today: date) -> int:
    since = datetime.now(timezone.utc) - timedelta(days=SPARSE_DAYS)
    query = _joined().where(visible_where(today), ActivityPost.created_at >= since, real_user(ActivityPost.user_id))
    return db.scalar(select(func.count()).select_from(query.with_only_columns(ActivityPost.id).subquery())) or 0


def season_of(day: date) -> str:
    return SEASONS[day.month]


def _seasonal(db: Session, today: date, live, skip: set) -> Trail | None:
    """The warmest trails this season, taking a different one each week."""
    season = season_of(today)
    trails = db.scalars(
        select(Trail)
        .join(TrailSeasonalCondition, TrailSeasonalCondition.trail_id == Trail.id)
        .where(*live, TrailSeasonalCondition.season == season)
        .order_by(TrailSeasonalCondition.avg_high_c.desc(), Trail.popularity_rank, Trail.name)
        .limit(6)
    ).all()
    trails = [t for t in trails if t.id not in skip]
    if not trails:
        return None
    return trails[today.isocalendar().week % len(trails)]


def picks(db: Session, today: date, trending: list, live) -> list[Pick]:
    """Up to three picks, each a different trail. `trending` is the list from
    GET /api/activity/trending (real hikers only), `live` the catalogue filter."""
    out: list[Pick] = []
    used: set = set()
    if trending:
        top = trending[0]
        trail = db.get(Trail, top.trail.id)
        if trail is not None:
            out.append(Pick(
                kind="trending",
                title="Trending this week" if top.this_week else "Popular on Trekly",
                text="Hikers have been logging and saving this one." if top.this_week
                else "One of the most-hiked trails in the catalogue.",
                trail=trail,
            ))
            used.add(trail.id)

    since = datetime.now(timezone.utc) - timedelta(days=NEW_PHOTO_DAYS)
    photo_trail = db.scalars(
        select(Trail).join(TrailPhoto, TrailPhoto.trail_id == Trail.id)
        .where(*live, TrailPhoto.created_at >= since, Trail.id.not_in(used) if used else True)
        .order_by(TrailPhoto.created_at.desc())
        .limit(1)
    ).first()
    if photo_trail is not None:
        out.append(Pick(kind="new_photos", title="New photos",
                        text="A fresh photo just went up for this trail.", trail=photo_trail))
        used.add(photo_trail.id)

    seasonal = _seasonal(db, today, live, used)
    if seasonal is not None:
        title, text = SEASON_TEXT[season_of(today)]
        out.append(Pick(kind="seasonal", title=title, text=text, trail=seasonal))
    return out
