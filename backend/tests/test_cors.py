from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient

from app.main import cors_options

PREVIEW_REGEX = r"https://trekly-web-[a-z0-9-]+-myteam\.vercel\.app"


def client_for(env):
    app = FastAPI()
    app.add_middleware(CORSMiddleware, **cors_options(env))

    @app.get("/ping")
    def ping():
        return {"ok": True}

    return TestClient(app)


def allowed_origin(client, origin):
    response = client.get("/ping", headers={"Origin": origin})
    return response.headers.get("access-control-allow-origin")


def test_defaults_to_local_dev_only():
    client = client_for({})
    assert allowed_origin(client, "http://localhost:3000") == "http://localhost:3000"
    assert allowed_origin(client, "https://trekly-web.vercel.app") is None


def test_lists_exact_origins():
    client = client_for({"CORS_ORIGINS": " https://trekly-web.vercel.app , http://localhost:3000 "})
    assert allowed_origin(client, "https://trekly-web.vercel.app") == "https://trekly-web.vercel.app"
    assert allowed_origin(client, "http://localhost:3000") == "http://localhost:3000"


def test_regex_allows_vercel_previews_only_for_the_team():
    client = client_for({"CORS_ORIGINS": "https://trekly-web.vercel.app", "CORS_ORIGIN_REGEX": PREVIEW_REGEX})
    for origin in (
        "https://trekly-web-abc123xyz-myteam.vercel.app",
        "https://trekly-web-git-feature-x-myteam.vercel.app",
    ):
        assert allowed_origin(client, origin) == origin
    for origin in (
        "https://trekly-web-abc123-otherteam.vercel.app",
        "https://trekly-web-abc123-myteam.vercel.app.evil.com",
        "http://trekly-web-abc123-myteam.vercel.app",
    ):
        assert allowed_origin(client, origin) is None


def test_preflight_for_authorised_request():
    client = client_for({"CORS_ORIGIN_REGEX": PREVIEW_REGEX})
    origin = "https://trekly-web-abc123-myteam.vercel.app"
    response = client.options(
        "/ping",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "PUT",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin
