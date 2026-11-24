import test from "node:test";
import assert from "node:assert/strict";
import { FILTERED, isExpectedError, scrubEvent, scrubUrl } from "./sentryScrub.ts";

// Same shape as lib/api.ts's ApiError (its file imports the Supabase client).
class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

test("API and auth 4xx answers and aborts are expected, 5xx and bugs are not", () => {
  for (const status of [401, 403, 404, 422, 429]) assert.ok(isExpectedError(new ApiError("x", status)), String(status));
  assert.ok(isExpectedError(Object.assign(new Error("Invalid login credentials"), { name: "AuthApiError", status: 400 })));
  assert.ok(isExpectedError(new DOMException("aborted", "AbortError")));
  assert.ok(!isExpectedError(new ApiError("down", 502)));
  assert.ok(!isExpectedError(new TypeError("x is undefined")));
  assert.ok(!isExpectedError(undefined));
  assert.equal(scrubEvent({ message: "x" }, { originalException: new ApiError("Not found", 404) }), null);
  assert.notEqual(scrubEvent({ message: "x" }, { originalException: new TypeError("bug") }), null);
});

test("session tokens in the URL hash and query are removed", () => {
  const url = scrubUrl("https://trekly-web.vercel.app/auth/confirm?code=abc&next=/gear#access_token=eyJa.eyJb.c&type=signup");
  assert.ok(!url.includes("abc") && !url.includes("eyJ"), url);
  assert.ok(url.includes("next=/gear") && url.includes("type=signup"), url);
  assert.equal(scrubUrl("https://x.test/trail-list?province_code=AB"), "https://x.test/trail-list?province_code=AB");
});

test("emails, tokens, headers, cookies and user details never leave", () => {
  const event = {
    message: "Sign-up failed for hiker@example.com",
    request: {
      url: "https://trekly-web.vercel.app/settings?email=a@b.co",
      headers: { Authorization: "Bearer eyJh.eyJp.sig", Cookie: "sb=1", "User-Agent": "Mozilla" },
      cookies: { sb: "1" },
    },
    user: { id: "u1", email: "hiker@example.com", ip_address: "1.2.3.4", username: "jo" },
    exception: { values: [{ type: "Error", value: "token eyJa.eyJb.c for x@y.ca" }] },
    breadcrumbs: [{ category: "fetch", data: { url: "https://api.test/x?access_token=zzz" } }],
    extra: { refresh_token: "secret", trail: "Lake Agnes" },
  };
  const out = scrubEvent(event)!;
  const text = JSON.stringify(out);
  for (const leaked of ["hiker@example.com", "a@b.co", "x@y.ca", "eyJ", "zzz", "1.2.3.4", "sb=1", "secret"]) {
    assert.ok(!text.includes(leaked), leaked);
  }
  assert.equal(out.request.headers.Authorization, FILTERED);
  assert.equal(out.request.headers["User-Agent"], "Mozilla");
  assert.equal("cookies" in out.request, false);
  assert.deepEqual(out.user, { id: "u1" });
  assert.equal(out.extra.trail, "Lake Agnes");
});
