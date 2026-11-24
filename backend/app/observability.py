"""Error reporting to Sentry (free tier), off unless SENTRY_DSN is set.

What leaves the server:
- Unexpected errors only. JsonServerErrors (app/main.py) turns them into a
  JSON 500 and logs them with logger.exception; Sentry's logging integration
  sends that log record with the traceback and the request. HTTPExceptions
  (401/403/404, moderation rejections as 422, rate limits as 429) are never
  logged as errors, and the FastAPI integration only reports 5xx responses;
  scrub_event drops any 4xx that slips through anyway.
- No personal data: send_default_pii is off (no IPs, cookies or bodies), and
  scrub_event removes auth headers, cookies, tokens in URLs and anything
  shaped like an email address, wherever it appears.
- 10% of requests as performance traces in production; none locally.

Environment:
    SENTRY_DSN          the project's DSN; unset = Sentry stays off
    SENTRY_ENVIRONMENT  optional; defaults to "production" on Render, else "local"
    RENDER_GIT_COMMIT   set by Render; becomes the release (the git SHA)
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any
from urllib.parse import parse_qsl, urlencode

log = logging.getLogger(__name__)

EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
# Bearer/JWT-looking strings: three base64url segments.
JWT = re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b")
SENSITIVE_HEADERS = {"authorization", "cookie", "set-cookie", "apikey", "x-api-key", "proxy-authorization"}
# Keys whose values are secrets or personal: tokens, secrets, emails, and an
# auth "code"/"key" on its own (not province_code or the like).
SENSITIVE_PARAMS = re.compile(r"token|secret|password|signature|email|api_?key|^code$|^key$", re.IGNORECASE)
FILTERED = "[Filtered]"


def _scrub_text(value: str) -> str:
    return JWT.sub(FILTERED, EMAIL.sub(FILTERED, value))


def _scrub(value: Any) -> Any:
    """Every string inside value, emails and tokens replaced."""
    if isinstance(value, str):
        return _scrub_text(value)
    if isinstance(value, dict):
        return {key: (FILTERED if isinstance(key, str) and SENSITIVE_PARAMS.search(key) and isinstance(item, str) else _scrub(item))
                for key, item in value.items()}
    if isinstance(value, list):
        return [_scrub(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_scrub(item) for item in value)
    return value


def _scrub_query(query: Any) -> Any:
    if not isinstance(query, str):
        return _scrub(query)
    pairs = [(key, FILTERED if SENSITIVE_PARAMS.search(key) else _scrub_text(value))
             for key, value in parse_qsl(query, keep_blank_values=True)]
    return urlencode(pairs, safe="[]")


def is_expected(event: dict, hint: dict | None) -> bool:
    """A 4xx (auth, not found, validation, moderation, rate limit): not a bug."""
    error = (hint or {}).get("exc_info", (None, None, None))[1]
    status = getattr(error, "status_code", None)
    if isinstance(status, int) and 400 <= status < 500:
        return True
    response_status = ((event.get("contexts") or {}).get("response") or {}).get("status_code")
    return isinstance(response_status, int) and 400 <= response_status < 500


def scrub_event(event: dict, hint: dict | None = None) -> dict | None:
    """Sentry's before_send: drop expected errors, strip personal data."""
    if is_expected(event, hint):
        return None
    request = event.get("request")
    if isinstance(request, dict):
        request.pop("cookies", None)
        request.pop("data", None)
        headers = request.get("headers")
        if isinstance(headers, dict):
            request["headers"] = {
                key: FILTERED if key.lower() in SENSITIVE_HEADERS or "token" in key.lower() else _scrub(value)
                for key, value in headers.items()
            }
        if "query_string" in request:
            request["query_string"] = _scrub_query(request["query_string"])
        if isinstance(request.get("url"), str):
            request["url"] = _scrub_text(request["url"])
    user = event.get("user")
    if isinstance(user, dict):
        # The user id alone is enough to find a report; no email, name or IP.
        event["user"] = {"id": user["id"]} if user.get("id") else {}
    for key in ("message", "logentry", "exception", "breadcrumbs", "extra", "contexts", "tags"):
        if key in event:
            event[key] = _scrub(event[key])
    return event


def sentry_options(env=os.environ) -> dict | None:
    """sentry_sdk.init options, or None when SENTRY_DSN isn't set."""
    dsn = (env.get("SENTRY_DSN") or "").strip()
    if not dsn:
        return None
    environment = (env.get("SENTRY_ENVIRONMENT") or "").strip() or ("production" if env.get("RENDER") else "local")
    return {
        "dsn": dsn,
        "environment": environment,
        "release": env.get("RENDER_GIT_COMMIT") or env.get("SENTRY_RELEASE") or None,
        "send_default_pii": False,
        # Stack frames' local variables can hold anything (raw request
        # headers with the bearer token, a user's row with their email), so
        # tracebacks carry code and line numbers only.
        "include_local_variables": False,
        "traces_sample_rate": 0.1 if environment == "production" else 0.0,
        "before_send": scrub_event,
        "before_send_transaction": scrub_event,
        "max_request_body_size": "never",
    }


def init_sentry(env=os.environ) -> bool:
    """Starts Sentry when configured; True if it did."""
    options = sentry_options(env)
    if options is None:
        return False
    import sentry_sdk

    sentry_sdk.init(**options)
    log.info("Sentry on (%s, release %s)", options["environment"], options["release"] or "unknown")
    return True
