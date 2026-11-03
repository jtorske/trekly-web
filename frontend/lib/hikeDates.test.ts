import test from "node:test";
import assert from "node:assert/strict";
import { localToday } from "./stay.ts";
import { formatHikeDate } from "./publicProfile.ts";

/**
 * Date-based milestones (Canada Day, First day hike, seasons) read the plain
 * YYYY-MM-DD the hiker saved. In the browser that date must be the local
 * calendar day, never a UTC one: 11:30 pm on July 1 in Vancouver is already
 * July 2 in UTC, and new Date("2026-07-01") is June 30 there.
 */
const ZONES = ["America/Vancouver", "America/St_Johns", "America/Whitehorse", "Pacific/Kiritimati", "UTC"];

for (const zone of ZONES) {
  test(`hike dates stay on the hiker's calendar day in ${zone}`, () => {
    const before = process.env.TZ;
    process.env.TZ = zone;
    try {
      // The dialog's default date: late in the evening and just after midnight.
      assert.equal(localToday(new Date(2026, 6, 1, 23, 30)), "2026-07-01");
      assert.equal(localToday(new Date(2027, 0, 1, 0, 5)), "2027-01-01");
      // Showing a saved date never moves it a day.
      assert.match(formatHikeDate("2026-07-01"), /July/);
      assert.doesNotMatch(formatHikeDate("2026-07-01"), /June|30/);
      assert.match(formatHikeDate("2027-01-01"), /January/);
      assert.doesNotMatch(formatHikeDate("2027-01-01"), /December|2026/);
    } finally {
      process.env.TZ = before;
    }
  });
}
