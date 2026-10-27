"""Username availability and suggestions for the sign-up and "choose your
username" forms. Open to guests, since sign-up happens before there's a
session. Says only whether a name is free, never whose it is.
"""

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.usernames import TAKEN_MESSAGE, is_taken, normalize, rule_problem, suggest

router = APIRouter(prefix="/api/usernames", tags=["usernames"])

NO_STORE = {"Cache-Control": "no-store"}


class UsernameCheckOut(BaseModel):
    username: str
    available: bool
    message: str


class UsernameSuggestionOut(BaseModel):
    username: str


@router.get("/check", response_model=UsernameCheckOut)
def check_username(response: Response, username: str = Query(max_length=60), db: Session = Depends(get_db)):
    response.headers.update(NO_STORE)
    name = normalize(username)
    problem = rule_problem(name)
    if problem is None and is_taken(db, name):
        problem = TAKEN_MESSAGE
    return UsernameCheckOut(username=name, available=problem is None, message=problem or f"@{name} is available.")


@router.get("/suggest", response_model=UsernameSuggestionOut)
def suggest_username(response: Response, hint: str = Query(default="", max_length=320), db: Session = Depends(get_db)):
    response.headers.update(NO_STORE)
    return UsernameSuggestionOut(username=suggest(db, hint))
