"""Supabase access-token verification for FastAPI routes.

The frontend signs users in with Supabase Auth and sends the session's access
token as `Authorization: Bearer <token>`. We verify it locally against the
project's published signing keys (JWKS, ES256/RS256), so verifying sign-ins
needs only the public project URL, never a service-role key. (The one
service-role key the backend holds is for trail photo uploads and stays in
app/trail_photos.py.) Projects still on the
legacy shared secret can set SUPABASE_JWT_SECRET for HS256 tokens.

Environment:
    SUPABASE_URL          https://<project-ref>.supabase.co   (required)
    SUPABASE_JWT_SECRET   legacy HS256 secret                 (optional)
"""

import os
from dataclasses import dataclass
from functools import lru_cache
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

ASYMMETRIC_ALGORITHMS = ("ES256", "RS256")
AUDIENCE = "authenticated"

bearer_scheme = HTTPBearer(auto_error=False)


class AuthConfigurationError(RuntimeError):
    pass


class TokenVerifier:
    def __init__(self, supabase_url: str, jwt_secret: str | None = None, jwks_client=None):
        base = supabase_url.rstrip("/")
        self.issuer = f"{base}/auth/v1"
        self.jwt_secret = jwt_secret
        self.jwks_client = jwks_client or jwt.PyJWKClient(
            f"{self.issuer}/.well-known/jwks.json", cache_keys=True, lifespan=3600
        )

    def verify(self, token: str) -> UUID:
        """Return the user id for a valid user access token; raise jwt.PyJWTError otherwise."""
        return self.verify_user(token).id

    def verify_user(self, token: str) -> "CurrentUser":
        algorithm = jwt.get_unverified_header(token).get("alg")
        if algorithm in ASYMMETRIC_ALGORITHMS:
            key = self.jwks_client.get_signing_key_from_jwt(token).key
        elif algorithm == "HS256" and self.jwt_secret:
            key = self.jwt_secret
        else:
            raise jwt.InvalidAlgorithmError(f"Unsupported token algorithm: {algorithm}")

        claims = jwt.decode(
            token,
            key,
            algorithms=[algorithm],
            audience=AUDIENCE,
            issuer=self.issuer,
            options={"require": ["exp", "sub", "aud", "iss"]},
        )
        # The anon/publishable key is also a JWT; only real user sessions count.
        if claims.get("role") != "authenticated":
            raise jwt.InvalidTokenError("Token is not a signed-in user session")
        try:
            user_id = UUID(claims["sub"])
        except (ValueError, TypeError) as error:
            raise jwt.InvalidTokenError("Token subject is not a user id") from error
        email = claims.get("email") if isinstance(claims.get("email"), str) else None
        return CurrentUser(id=user_id, email=email or None)


@dataclass(frozen=True)
class CurrentUser:
    id: UUID
    email: str | None


@lru_cache
def get_token_verifier() -> TokenVerifier:
    supabase_url = os.getenv("SUPABASE_URL")
    if not supabase_url:
        raise AuthConfigurationError("SUPABASE_URL is not set")
    return TokenVerifier(supabase_url, os.getenv("SUPABASE_JWT_SECRET") or None)


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_verifier_dependency() -> TokenVerifier:
    try:
        return get_token_verifier()
    except AuthConfigurationError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Sign-in isn't configured on the server.",
        ) from error


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    verifier: TokenVerifier = Depends(get_verifier_dependency),
) -> CurrentUser:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _unauthorized("Sign in to continue.")
    try:
        return verifier.verify_user(credentials.credentials)
    except jwt.PyJWKClientConnectionError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Couldn't reach the sign-in service. Try again shortly.",
        ) from error
    except jwt.PyJWTError as error:
        raise _unauthorized("Your session has expired or is invalid. Sign in again.") from error


def get_current_user_id(user: CurrentUser = Depends(get_current_user)) -> UUID:
    return user.id
