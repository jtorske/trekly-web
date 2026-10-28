import test from "node:test";
import assert from "node:assert/strict";
import { displayName, hiddenSections, robotsFor } from "./publicProfile.ts";
import type { PrivacySettings } from "./profilesApi.ts";

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
