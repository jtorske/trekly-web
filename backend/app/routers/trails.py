from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.trail import Trail
from app.schemas.trail import TrailOut

router = APIRouter(prefix="/api/trails", tags=["trails"])


@router.get("", response_model=list[TrailOut])
def search_trails(q: str = "", db: Session = Depends(get_db)):
    query = db.query(Trail)
    if q:
        like = f"%{q}%"
        query = query.filter(or_(Trail.name.ilike(like), Trail.region.ilike(like)))
    return query.order_by(Trail.name).limit(10).all()


@router.get("/{trail_id}", response_model=TrailOut)
def get_trail(trail_id: UUID, db: Session = Depends(get_db)):
    trail = db.get(Trail, trail_id)
    if trail is None:
        raise HTTPException(status_code=404, detail="Trail not found")
    return trail
