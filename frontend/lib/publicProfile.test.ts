import test from "node:test";
import assert from "node:assert/strict";
import { displayName, featuredEntries, hiddenSections, robotsFor } from "./publicProfile.ts";
import type { PrivacySettings, PublicJournalEntry } from "./profilesApi.ts";
import type { TrailListItem } from "./trailsApi.ts";

let next = 0;
function entry(overrides: Partial<TrailListItem> = {}): PublicJournalEntry {
  next += 1;
  const trail = {
    id: `t${next}`,
    name: `Trail ${next}`,
    region: "Banff National Park, AB",
    country_code: "CA",
    province_code: "AB",
    terrain: "moderate",
    typical_duration_nights: 0,
    distance_km: null,
    ...overrides,
  } as TrailListItem;
  return { trail, hiked_on: null, note: null, photo_path: null };
}

const SETTINGS: PrivacySettings = {
  is_private: false,
  show_journal: true,
  show_rank: true,
  show_gear: true,
  show_saved_trails: true,
  show_trip_plans: false,
  hide_hike_dates: false,
  allow_search_indexing: false,
  public_notice_pending: false,
  username: "alice",
  hidden_by_moderators: false,
};

test("featured badges keep the API's order and stop at six", () => {
  const entries = Array.from({ length: 9 }, () => entry());
  assert.deepEqual(featuredEntries(entries).map((e) => e.trail.id), entries.slice(0, 6).map((e) => e.trail.id));
  assert.deepEqual(featuredEntries(entries.slice(0, 2)), entries.slice(0, 2));
});

test("the owner's banner lists the hidden sections", () => {
  assert.deepEqual(hiddenSections(SETTINGS), ["Trip plans"]);
  assert.deepEqual(hiddenSections({ ...SETTINGS, show_gear: false, show_trip_plans: true }), ["Gear and loadouts"]);
});

test("profiles are noindex unless the owner opted in", () => {
  assert.deepEqual(robotsFor(null), { index: false, follow: false });
  assert.deepEqual(robotsFor({ allow_indexing: false }), { index: false, follow: false });
  assert.deepEqual(robotsFor({ allow_indexing: true }), { index: true, follow: true });
});

test("display name falls back to the handle", () => {
  assert.equal(displayName({ display_name: "  ", username: "alice" }), "@alice");
  assert.equal(displayName({ display_name: "Alice A", username: "alice" }), "Alice A");
});
