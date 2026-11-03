import assert from "node:assert/strict";
import test from "node:test";
import type { CampgroundAlert } from "../../lib/availabilityApi.ts";
import { alertPlace, groupAlerts, groupOf, timeAgo } from "./alertGroups.ts";

const TODAY = "2026-11-02";

function alert(id: string, status: CampgroundAlert["status"], start_date: string): CampgroundAlert {
  return {
    id, status, start_date, site_id: "s", campground: "Evelyn Creek", site_code: "27", park: "Jasper",
    trail: null, end_date: start_date, nights: 2, party_size: 2, last_summary: null,
    last_checked_at: null, notified_at: null, created_at: "2026-10-01T00:00:00Z", booking_url: null,
  };
}

test("alerts sort into Active, Found and Past", () => {
  assert.equal(groupOf(alert("a", "active", "2026-11-10"), TODAY), "active");
  assert.equal(groupOf(alert("a", "notified", "2026-11-10"), TODAY), "found");
  assert.equal(groupOf(alert("a", "cancelled", "2026-11-10"), TODAY), "past");
  assert.equal(groupOf(alert("a", "expired", "2026-10-10"), TODAY), "past");
  // Not expired yet by the poller, or found but no longer bookable.
  assert.equal(groupOf(alert("a", "active", "2026-11-01"), TODAY), "past");
  assert.equal(groupOf(alert("a", "notified", "2026-11-01"), TODAY), "past");
  assert.equal(groupOf(alert("a", "active", TODAY), TODAY), "active");
});

test("groups keep a useful order and skip empty sections", () => {
  const groups = groupAlerts(
    [
      alert("late", "active", "2026-12-01"),
      alert("old", "expired", "2026-09-01"),
      alert("soon", "active", "2026-11-05"),
      alert("recent", "cancelled", "2026-11-20"),
    ],
    TODAY,
  );
  assert.deepEqual(groups.map((g) => [g.title, g.alerts.map((a) => a.id)]), [
    ["Active", ["soon", "late"]],
    ["Past and cancelled", ["recent", "old"]],
  ]);
  assert.deepEqual(groupAlerts([], TODAY), []);
});

test("last checked reads as a short time ago", () => {
  const now = new Date("2026-11-02T18:00:00Z");
  assert.equal(timeAgo("2026-11-02T17:59:40Z", now), "just now");
  assert.equal(timeAgo("2026-11-02T17:48:00Z", now), "12 min ago");
  assert.equal(timeAgo("2026-11-02T15:00:00Z", now), "3 h ago");
  assert.match(timeAgo("2026-10-20T12:00:00Z", now), /^on Oct 2\d$/);
});

test("the site code shows only when it adds something", () => {
  assert.equal(alertPlace({ campground: "Evelyn Creek", site_code: "27" }), "Evelyn Creek 27");
  assert.equal(alertPlace({ campground: "PH1", site_code: "PH1" }), "PH1");
  assert.equal(alertPlace({ campground: "Signal", site_code: null }), "Signal");
});
