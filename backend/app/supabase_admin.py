"""Account actions through the Supabase Auth admin API (service-role key).

Used by the admin area (app/routers/admin.py) to ban, unban and send a
password reset, and by the sign-up email helper (app/routers/signup_email.py)
to resend a sign-up confirmation. Like PhotoStorage (app/trail_photos.py), the key is read
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


def _json_object(response) -> dict:
    """The body of a successful call, or {} when it has none worth reading."""
    try:
        payload = json.loads(response.read() or b"{}")
    except (ValueError, AttributeError, TypeError):
        return {}
    return payload if isinstance(payload, dict) else {}


class SupabaseAdmin:
    def __init__(self, supabase_url: str, service_key: str):
        self.base = f"{supabase_url.rstrip('/')}/auth/v1"
        # A closure, not an attribute: dumping the object shows a function.
        self._auth_headers = lambda: {"Authorization": f"Bearer {service_key}", "apikey": service_key}

    def __repr__(self) -> str:
        return f"SupabaseAdmin({self.base!r})"

    def _send(self, method: str, url: str, body: dict) -> dict:
        request = urllib.request.Request(
            url,
            data=json.dumps(body).encode(),
            method=method,
            headers={**self._auth_headers(), "Content-Type": "application/json", "User-Agent": USER_AGENT},
        )
        status = None
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                return _json_object(response)
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

    def recovery_token_hash(self, email: str) -> str:
        """A password-reset token for this address, without sending anything.
        Works for an account that only signs in with Google, too: verifying it
        signs them in, and the password they then choose works alongside Google."""
        payload = self._send("POST", f"{self.base}/admin/generate_link", {"type": "recovery", "email": email})
        token_hash = payload.get("hashed_token") or (payload.get("properties") or {}).get("hashed_token")
        if not isinstance(token_hash, str) or not token_hash:
            raise SupabaseAdminError("Supabase didn't return a reset token.")
        return token_hash

    def create_user(self, email: str, password: str, display_name: str) -> UUID:
        """A confirmed account with no email sent (the labeled-account scripts)."""
        payload = self._send("POST", f"{self.base}/admin/users", {
            "email": email, "password": password, "email_confirm": True,
            "user_metadata": {"display_name": display_name},
        })
        try:
            return UUID(str(payload.get("id") or (payload.get("user") or {}).get("id")))
        except ValueError:
            raise SupabaseAdminError("Supabase didn't return the new account's id.") from None

    def delete_user(self, user_id: UUID) -> None:
        """Deletes the account; its rows go with it (ON DELETE CASCADE)."""
        self._send("DELETE", f"{self.base}/admin/users/{user_id}", {})

    def resend_signup_confirmation(self, email: str, redirect_to: str) -> None:
        """Supabase's own "Confirm your email" email, sent again."""
        query = urllib.parse.urlencode({"redirect_to": redirect_to})
        self._send("POST", f"{self.base}/resend?{query}", {"type": "signup", "email": email})


def supabase_admin_from_env() -> SupabaseAdmin | None:
    url, key = os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    return SupabaseAdmin(url, key) if url and key else None


def reset_redirect() -> str:
    """The same landing as "Forgot password": the auth callback, then /reset-password."""
    app_url = os.getenv("APP_URL", "http://localhost:3000").rstrip("/")
    return f"{app_url}/auth/callback?next={urllib.parse.quote('/reset-password', safe='')}"
