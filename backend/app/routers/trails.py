from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.trail import Trail
from app.models.trail_seasonal_condition import TrailSeasonalCondition
from app.schemas.trail import (
    SeasonalConditionOut,
    Terrain,
    TrailDetailOut,
    TrailListItemOut,
)

router = APIRouter(prefix="/api/trails", tags=["trails"])

SEASON_ORDER = {"spring": 0, "summer": 1, "fall": 2, "winter": 3}


@router.get("", response_model=list[TrailListItemOut])
def search_trails(
    q: str = "",
    terrain: Terrain | None = None,
    limit: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
):
    query = db.query(Trail)
    if q:
        like = f"%{q}%"
        query = query.filter(or_(Trail.name.ilike(like), Trail.region.ilike(like)))
    if terrain:
        query = query.filter(Trail.terrain_difficulty == terrain)
    return query.order_by(Trail.name).limit(limit).all()


@router.get("/{trail_id}", response_model=TrailDetailOut)
def get_trail(trail_id: UUID, db: Session = Depends(get_db)):
    trail = db.get(Trail, trail_id)
    if trail is None:
        raise HTTPException(status_code=404, detail="Trail not found")

    conditions = (
        db.query(TrailSeasonalCondition)
        .filter(TrailSeasonalCondition.trail_id == trail_id)
        .all()
    )
    detail = TrailDetailOut.model_validate(trail)
    detail.seasonal_conditions = [
        SeasonalConditionOut.model_validate(condition)
        for condition in sorted(conditions, key=lambda c: SEASON_ORDER.get(c.season, 99))
    ]
    return detail
