import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import availability, gear, me_account, me_alerts, me_gear, me_setups, trails

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    # Comma-separated list, e.g. "https://trekly.app,http://localhost:3000".
    allow_origins=[
        origin.strip()
        for origin in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
        if origin.strip()
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(trails.router)
app.include_router(availability.router)
app.include_router(gear.router)
app.include_router(me_gear.router)
app.include_router(me_account.router)
app.include_router(me_setups.router)
app.include_router(me_alerts.router)


@app.get("/")
def root():
    return {
        "message": "Trail Q API running"
    }