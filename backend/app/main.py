import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import (
    admin_profiles,
    admin_trail_photos,
    availability,
    gear,
    me_account,
    me_alerts,
    me_featured_badges,
    me_gear,
    me_hike_logs,
    me_plans,
    me_privacy,
    me_rank,
    me_setups,
    public_profiles,
    trails,
    usernames,
)


def cors_options(env=os.environ) -> dict:
    return {
        # Comma-separated list, e.g. "https://trekly.app,http://localhost:3000".
        "allow_origins": [
            origin.strip()
            for origin in env.get("CORS_ORIGINS", "http://localhost:3000").split(",")
            if origin.strip()
        ],
        # Full-match regex for origins that can't be listed, such as Vercel
        # preview URLs: "https://trekly-web-[a-z0-9-]+-myteam\.vercel\.app".
        "allow_origin_regex": env.get("CORS_ORIGIN_REGEX") or None,
        "allow_credentials": True,
        "allow_methods": ["*"],
        "allow_headers": ["*"],
    }


def docs_enabled(env=os.environ) -> bool:
    """Swagger UI and the OpenAPI schema: on locally, off on Render.

    API_DOCS=true/false overrides; Render sets RENDER on every service.
    """
    setting = env.get("API_DOCS")
    if setting is not None:
        return setting.strip().lower() in ("1", "true", "yes")
    return not env.get("RENDER")


app = FastAPI(
    **({} if docs_enabled() else {"docs_url": None, "redoc_url": None, "openapi_url": None})
)

app.add_middleware(CORSMiddleware, **cors_options())

app.include_router(trails.router)
app.include_router(availability.router)
app.include_router(gear.router)
app.include_router(me_gear.router)
app.include_router(me_account.router)
app.include_router(me_setups.router)
app.include_router(me_alerts.router)
app.include_router(me_plans.router)
app.include_router(me_hike_logs.router)
app.include_router(me_featured_badges.router)
app.include_router(me_rank.router)
app.include_router(admin_trail_photos.router)
app.include_router(me_privacy.router)
app.include_router(public_profiles.router)
app.include_router(admin_profiles.router)
app.include_router(usernames.router)


@app.get("/")
def root():
    return {
        "message": "Trail Q API running"
    }