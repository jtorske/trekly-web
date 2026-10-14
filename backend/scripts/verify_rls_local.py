"""Verify row-level security against a LOCAL Supabase CLI stack.

Talks to Supabase's REST API directly (bypassing the Trekly API) as two real
users and as the anonymous role, and checks that nobody can read or change
another user's private rows. Refuses to run against anything but localhost.

    python scripts/verify_rls_local.py
"""

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

BASE = os.getenv("LOCAL_SUPABASE_URL", "http://127.0.0.1:44321")
ANON = os.getenv(
    "LOCAL_SUPABASE_ANON_KEY",
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZS1kZW1vIiwicm9sZSI6ImFub24iLCJleHAiOjE5ODM4MTI5OTZ9.CRXP1A7WOeoJeXxjNni43kdQwgnWNReilDMblYTn_I0",
)
SERVICE = os.getenv(
    "LOCAL_SUPABASE_SERVICE_KEY",
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZS1kZW1vIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImV4cCI6MTk4MzgxMjk5Nn0.EGIM96RAZx35lJzdJsyH-qQwv8Hdp7fsn3W0YpN81IU",
)

if not BASE.startswith(("http://127.0.0.1", "http://localhost")):
    sys.exit("Refusing to run: this script only targets a local Supabase stack.")

env_file = Path(__file__).resolve().parents[2] / "supabase" / "e2e-test-users.env"
users = dict(line.split("=", 1) for line in env_file.read_text().splitlines() if "=" in line and not line.startswith("#"))
PASSWORD = users["E2E_PASSWORD"].strip()


def call(method, path, token=None, body=None, apikey=ANON, extra=None):
    headers = {"apikey": apikey, "Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    headers.update(extra or {})
    request = urllib.request.Request(
        f"{BASE}{path}", method=method, headers=headers, data=json.dumps(body).encode() if body is not None else None
    )
    try:
        with urllib.request.urlopen(request) as response:
            text = response.read().decode()
            return response.status, json.loads(text) if text else None
    except urllib.error.HTTPError as error:
        text = error.read().decode()
        return error.code, json.loads(text) if text else None


def token_for(email):
    status, body = call("POST", "/auth/v1/token?grant_type=password", body={"email": email, "password": PASSWORD})
    assert status == 200, (email, status, body)
    return body["access_token"], body["user"]["id"]


def ensure_user(email):
    # Local admin API (service key is the public local-dev default) creates a confirmed user.
    call("POST", "/auth/v1/admin/users", token=SERVICE, apikey=SERVICE,
         body={"email": email, "password": PASSWORD, "email_confirm": True})


failures = []


def check(label, condition):
    print(("PASS " if condition else "FAIL ") + label)
    if not condition:
        failures.append(label)


ensure_user(users["E2E_USER_B_EMAIL"].strip())
alice, alice_id = token_for(users["E2E_USER_A_EMAIL"].strip())
bob, bob_id = token_for(users["E2E_USER_B_EMAIL"].strip())

_, alice_gear = call("GET", "/rest/v1/user_gear_items?select=id,user_id", alice)
check("Alice can read her own gear", bool(alice_gear) and all(r["user_id"] == alice_id for r in alice_gear))
target = alice_gear[0]["id"] if alice_gear else "00000000-0000-0000-0000-000000000000"

_, bob_view = call("GET", "/rest/v1/user_gear_items?select=id", bob)
check("Bob sees none of Alice's gear", bob_view == [])
_, by_id = call("GET", f"/rest/v1/user_gear_items?id=eq.{target}&select=id", bob)
check("Bob can't fetch Alice's gear by id", by_id == [])
_, anon_view = call("GET", "/rest/v1/user_gear_items?select=id")
check("Anonymous sees no gear", anon_view == [] or isinstance(anon_view, dict))

status, updated = call("PATCH", f"/rest/v1/user_gear_items?id=eq.{target}", bob, {"quantity": 42}, extra={"Prefer": "return=representation"})
check("Bob's update of Alice's gear changes nothing", updated == [])
status, deleted = call("DELETE", f"/rest/v1/user_gear_items?id=eq.{target}", bob, extra={"Prefer": "return=representation"})
check("Bob's delete of Alice's gear removes nothing", deleted == [])
_, still = call("GET", f"/rest/v1/user_gear_items?id=eq.{target}&select=quantity", alice)
check("Alice's item is intact", bool(still) and still[0]["quantity"] != 42)

status, _ = call("POST", "/rest/v1/user_gear_items", bob,
                 {"user_id": alice_id, "custom_name": "Planted", "category_id": "00000000-0000-0000-0000-000000000000"})
check("Bob can't insert a row owned by Alice", status in (401, 403))

_, profiles = call("GET", "/rest/v1/profiles?select=id,display_name", bob)
check("Bob only sees his own profile", all(p["id"] == bob_id for p in profiles or []))
_, alice_profile = call("PATCH", f"/rest/v1/profiles?id=eq.{alice_id}", bob, {"bio": "hacked"}, extra={"Prefer": "return=representation"})
check("Bob can't edit Alice's profile", alice_profile == [])

_, saved = call("GET", "/rest/v1/saved_trails?select=trail_id", bob)
check("Bob sees no saved trails of others", saved == [])

status, products = call("GET", "/rest/v1/catalog_products?select=id&limit=1")
check("Catalogue is publicly readable", status == 200 and len(products) == 1)
status, written = call("PATCH", f"/rest/v1/catalog_products?id=eq.{products[0]['id']}", alice, {"name": "Hacked"}, extra={"Prefer": "return=representation"})
check("Signed-in users can't modify the shared catalogue", status in (401, 403) or written == [])

status, objects = call("POST", f"/storage/v1/object/list/gear-photos", bob, {"prefix": alice_id})
check("Bob can't list Alice's photo folder", objects == [] or status >= 400)

print(f"\n{len(failures)} failure(s)")
sys.exit(1 if failures else 0)
