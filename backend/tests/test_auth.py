import time
import uuid

import jwt
from cryptography.hazmat.primitives.asymmetric import ec


def test_missing_token_is_401(client):
    response = client.get("/api/me/gear")
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_valid_token_is_accepted(client, auth_headers):
    response = client.get("/api/me/gear", headers=auth_headers(uuid.uuid4()))
    assert response.status_code == 200
    assert response.json()["items"] == []


def test_rejects_expired_wrong_audience_issuer_role_and_subject(client, make_token):
    bad_tokens = [
        make_token(exp=int(time.time()) - 10),
        make_token(aud="something-else"),
        make_token(iss="https://evil.example.com/auth/v1"),
        make_token(role="anon"),
        make_token(sub="not-a-uuid"),
        make_token(exp=None),
        "not.a.jwt",
    ]
    for token in bad_tokens:
        response = client.get("/api/me/gear", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 401, token


def test_rejects_token_signed_by_another_key(client):
    other_key = ec.generate_private_key(ec.SECP256R1())
    now = int(time.time())
    forged = jwt.encode(
        {
            "sub": str(uuid.uuid4()),
            "aud": "authenticated",
            "iss": "https://test-project.supabase.co/auth/v1",
            "role": "authenticated",
            "exp": now + 3600,
        },
        other_key,
        algorithm="ES256",
    )
    response = client.get("/api/me/gear", headers={"Authorization": f"Bearer {forged}"})
    assert response.status_code == 401


def test_rejects_hs256_without_configured_secret(client):
    token = jwt.encode(
        {
            "sub": str(uuid.uuid4()),
            "aud": "authenticated",
            "iss": "https://test-project.supabase.co/auth/v1",
            "role": "authenticated",
            "exp": int(time.time()) + 3600,
        },
        "guessable-secret-of-at-least-32-bytes!!",
        algorithm="HS256",
    )
    response = client.get("/api/me/gear", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401
