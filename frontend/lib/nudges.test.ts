import test from "node:test";
import assert from "node:assert/strict";
import { NUDGE_SETTING, itemVisible, nudgeActions, summaryLine, visitorSummary, type Nudge, type NudgeApi } from "./nudges.ts";
import type { PrivacySettings, PrivacyUpdate } from "./profilesApi.ts";

const defaults: PrivacySettings = {
  is_private: false,
  show_journal: true,
  show_rank: true,
  show_gear: true,
  show_saved_trails: true,
  show_trip_plans: false,
  hide_hike_dates: false,
  allow_search_indexing: false,
  show_in_community: false,
  show_home_province: false,
  show_visit_streak: false,
  share_activity: false,
  public_notice_pending: false,
  username: "alice",
  hidden_by_moderators: false,
};

/** A fake API that records every call. */
function recorder() {
  const calls: { updates: PrivacyUpdate[]; dismissed: Nudge[] } = { updates: [], dismissed: [] };
  const api: NudgeApi = {
    updatePrivacy: async (update) => {
      calls.updates.push(update);
      return { ...defaults, ...update } as PrivacySettings;
    },
    dismissNudge: async (nudge) => {
      calls.dismissed.push(nudge);
    },
  };
  return { api, calls };
}

const NUDGES = Object.keys(NUDGE_SETTING) as Nudge[];

test("making a nudge changes nothing until it's tapped", () => {
  const { api, calls } = recorder();
  for (const nudge of NUDGES) nudgeActions(nudge, api);
  assert.deepEqual(calls, { updates: [], dismissed: [] });
});

test("turning on sends exactly its one setting, switched on, and nothing else", async () => {
  for (const nudge of NUDGES) {
    const { api, calls } = recorder();
    await nudgeActions(nudge, api).turnOn();
    assert.deepEqual(calls.updates, [{ [NUDGE_SETTING[nudge]]: true }]);
    assert.deepEqual(calls.dismissed, []);
  }
  assert.equal(NUDGE_SETTING.hike_share, "share_activity");
  assert.equal(NUDGE_SETTING.activity_card, "share_activity");
  assert.equal(NUDGE_SETTING.hiked_by, "show_in_community");
});

test("dismissing only puts the nudge away and never touches a setting", async () => {
  for (const nudge of NUDGES) {
    const { api, calls } = recorder();
    await nudgeActions(nudge, api).dismiss();
    assert.deepEqual(calls, { updates: [], dismissed: [nudge] });
  }
});

test("the summary line names what visitors see and what isn't shared", () => {
  assert.equal(summaryLine(defaults), "Visitors see: journal, rank, gear, saved trails. Not sharing: Activity feed, Hiked by.");
  assert.equal(
    summaryLine({ ...defaults, share_activity: true, show_in_community: true, show_saved_trails: false }),
    "Visitors see: journal, rank, gear. Sharing: Activity feed, Hiked by.",
  );
  assert.equal(
    summaryLine({ ...defaults, share_activity: true }),
    "Visitors see: journal, rank, gear, saved trails. Not sharing: Hiked by.",
  );
});

test("private profiles, no username and a hidden journal share nothing in the community", () => {
  assert.match(summaryLine({ ...defaults, is_private: true, share_activity: true }), /private/);
  assert.match(summaryLine({ ...defaults, username: null }), /username/);
  const noJournal = { ...defaults, show_journal: false, share_activity: true, show_in_community: true };
  assert.equal(itemVisible(noJournal, "share_activity"), false);
  assert.equal(itemVisible(noJournal, "show_in_community"), false);
  assert.match(summaryLine(noJournal), /Not sharing: Activity feed, Hiked by/);
});

test("the visitors card lists every item as visible or hidden", () => {
  const { visible, hidden } = visitorSummary(defaults);
  assert.deepEqual(visible, ["Journal", "Rank", "Gear", "Saved trails"]);
  assert.deepEqual(hidden, ["Trip plans", "Home province", "Visit streak", "Activity feed", "Hiked by"]);
  assert.deepEqual(visitorSummary({ ...defaults, is_private: true }).visible, []);
});
