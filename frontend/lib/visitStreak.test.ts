import test from "node:test";
import assert from "node:assert/strict";
import {
  bestLabel,
  cachedToday,
  localDate,
  readCache,
  showsStreak,
  streakLabel,
  toCache,
  type VisitReply,
} from "./visitStreak.ts";

const reply: VisitReply = { current_streak: 12, longest_streak: 30, today: "2026-11-02", grew: true };
const ALICE = "6f1c1a52-0000-4000-8000-000000000001";

test("the local date follows the browser's time zone around midnight", () => {
  // Regina has been UTC-6 all year for decades, so this doesn't depend on the runtime's zone data:
  // 05:59 UTC on 3 Nov is 23:59 on 2 Nov there; a minute later it's 3 Nov.
  assert.equal(localDate(new Date("2026-11-03T05:59:00Z"), "America/Regina"), "2026-11-02");
  assert.equal(localDate(new Date("2026-11-03T06:00:00Z"), "America/Regina"), "2026-11-03");
  assert.equal(localDate(new Date("2026-11-03T06:59:00Z"), "UTC"), "2026-11-03");
  assert.equal(localDate(new Date("2026-11-03T11:30:00Z"), "Pacific/Kiritimati"), "2026-11-04");
});

test("an unknown time zone falls back to the browser's own", () => {
  const now = new Date("2026-11-03T12:00:00Z");
  assert.equal(localDate(now, "Not/AZone"), localDate(now, null));
});

test("the once-a-day guard skips the call only for the same user on the same date", () => {
  const cache = readCache(JSON.stringify(toCache(ALICE, reply)));
  assert.deepEqual(cachedToday(cache, ALICE, "2026-11-02"), { current: 12, longest: 30 });
  // The next local day, another account in this tab, or nothing cached: call the API.
  assert.equal(cachedToday(cache, ALICE, "2026-11-03"), null);
  assert.equal(cachedToday(cache, "someone-else", "2026-11-02"), null);
  assert.equal(cachedToday(null, ALICE, "2026-11-02"), null);
});

test("the cache never keeps the grew flag, so a reload doesn't animate again", () => {
  assert.equal("grew" in toCache(ALICE, reply), false);
});

test("an unreadable or tampered cache counts as not recorded", () => {
  for (const raw of [null, "", "not json", "{}", '{"userId":"a","today":"2026-11-02","current":"12","longest":30}']) {
    assert.equal(readCache(raw), null, String(raw));
  }
});

test("a streak of 1 is hidden; from 2 days it shows", () => {
  assert.equal(showsStreak(null), false);
  assert.equal(showsStreak({ current: 0, longest: 9 }), false);
  assert.equal(showsStreak({ current: 1, longest: 9 }), false);
  assert.equal(showsStreak({ current: 2, longest: 2 }), true);
});

test("labels: the streak, and the best only when it's longer", () => {
  assert.equal(streakLabel(12), "12-day streak");
  assert.equal(bestLabel({ current: 12, longest: 30 }), "Best: 30 days");
  assert.equal(bestLabel({ current: 12, longest: 12 }), null);
});
