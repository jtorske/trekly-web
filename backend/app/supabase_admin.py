"""Account actions through the Supabase Auth admin API (service-role key).

Used by the admin area (app/routers/admin.py) to ban, unban and send a
password reset. Like PhotoStorage (app/trail_photos.py), the key is read
only by supabase_admin_from_env() and lives only inside a closure that
builds request headers: it is never an attribute, never logged, and never in
an error. A failed request raises SupabaseAdminError with just the HTTP
status, and the original exception is dropped (`from None`), because a
server could echo the request's headers back in its error body.

Environment:
    SUPABASE_URL               https://<project-ref>.supabase.co
    SUPABASE_SERVICE_ROLE_KEY  server only; never sent to the browser
    APP_URL                    where the reset email's link lands
"""

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from uuid import UUID

# Supabase has no "ban forever"; a hundred years is its documented idiom.
BAN_DURATION = "876000h"
USER_AGENT = "Trekly admin (server)"


class SupabaseAdminError(RuntimeError):
    pass


class SupabaseAdmin:
    def __init__(self, supabase_url: str, service_key: str):
        self.base = f"{supabase_url.rstrip('/')}/auth/v1"
        # A closure, not an attribute: dumping the object shows a function.
        self._auth_headers = lambda: {"Authorization": f"Bearer {service_key}", "apikey": service_key}

    def __repr__(self) -> str:
        return f"SupabaseAdmin({self.base!r})"

    def _send(self, method: str, url: str, body: dict) -> None:
        request = urllib.request.Request(
            url,
            data=json.dumps(body).encode(),
            method=method,
            headers={**self._auth_headers(), "Content-Type": "application/json", "User-Agent": USER_AGENT},
        )
        status = None
        try:
            with urllib.request.urlopen(request, timeout=20):
                return
        except urllib.error.HTTPError as error:
            status = error.code
        except (urllib.error.URLError, TimeoutError, OSError):
            pass
        raise SupabaseAdminError(
            f"Supabase didn't accept that ({f'HTTP {status}' if status else 'no response'})."
        ) from None

    def ban(self, user_id: UUID) -> None:
        self._send("PUT", f"{self.base}/admin/users/{user_id}", {"ban_duration": BAN_DURATION})

    def unban(self, user_id: UUID) -> None:
        self._send("PUT", f"{self.base}/admin/users/{user_id}", {"ban_duration": "none"})

    def send_password_reset(self, email: str, redirect_to: str) -> None:
        query = urllib.parse.urlencode({"redirect_to": redirect_to})
        self._send("POST", f"{self.base}/recover?{query}", {"email": email})


def supabase_admin_from_env() -> SupabaseAdmin | None:
    url, key = os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    return SupabaseAdmin(url, key) if url and key else None


def reset_redirect() -> str:
    """The same landing as "Forgot password": the auth callback, then /reset-password."""
    app_url = os.getenv("APP_URL", "http://localhost:3000").rstrip("/")
    return f"{app_url}/auth/callback?next={urllib.parse.quote('/reset-password', safe='')}"
