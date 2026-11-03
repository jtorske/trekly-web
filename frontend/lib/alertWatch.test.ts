import test from "node:test";
import assert from "node:assert/strict";
import { ALERTS_WORK_FOR, choosePickerTrail, pickerOrder, pickerSearch, unwatchableReason } from "./alertWatch.ts";

const base = { trail_permit: false, booked_through: null, park_type: null } as const;

test("a provincial park names its booking system", () => {
  assert.equal(
    unwatchableReason({ ...base, park_type: "provincial", booked_through: { system: "bc_parks", name: "BC Parks" } }),
    `Provincial park: book through BC Parks. ${ALERTS_WORK_FOR}`,
  );
  assert.equal(
    unwatchableReason({
      ...base,
      park_type: "none",
      booked_through: { system: "traversee_de_charlevoix", name: "Traversée de Charlevoix" },
    }),
    `Book through Traversée de Charlevoix. ${ALERTS_WORK_FOR}`,
  );
});

test("unknown, unconfirmed or off-map Parks Canada booking gets the general reason", () => {
  const general = `No online Parks Canada booking. ${ALERTS_WORK_FOR}`;
  assert.equal(unwatchableReason(base), general);
  assert.equal(
    unwatchableReason({ ...base, park_type: "national", booked_through: { system: "parks_canada", name: "Parks Canada" } }),
    general,
  );
});

test("permits and first-come campsites say so", () => {
  assert.match(unwatchableReason({ ...base, trail_permit: true, park_type: "national" }), /permit/);
  assert.match(
    unwatchableReason({ ...base, booked_through: { system: "none", name: "No reservations" } }),
    /first come, first served/,
  );
});

test("the browse list hides unwatchable trails until asked; a search always finds them", () => {
  assert.deepEqual(pickerSearch("", false), { watchable: true, sort: "watchable" });
  assert.deepEqual(pickerSearch("  ", false), { watchable: true, sort: "watchable" });
  assert.deepEqual(pickerSearch("", true), { sort: "watchable" });
  assert.deepEqual(pickerSearch("garibaldi", false), { sort: "watchable" });
});

test("watchable trails come first, keeping the server's order within each group", () => {
  const trails = [
    { name: "A", has_watchable_campgrounds: false },
    { name: "B", has_watchable_campgrounds: true },
    { name: "C", has_watchable_campgrounds: false },
    { name: "D", has_watchable_campgrounds: true },
  ];
  assert.deepEqual(pickerOrder(trails).map((t) => t.name), ["B", "D", "A", "C"]);
});

test("an unwatchable trail can't be selected: choosing it only explains why", () => {
  const garibaldi = {
    ...base,
    park_type: "provincial" as const,
    booked_through: { system: "bc_parks", name: "BC Parks" },
    has_watchable_campgrounds: false,
  };
  assert.deepEqual(choosePickerTrail(garibaldi), { kind: "explain", reason: unwatchableReason(garibaldi) });
  const skyline = { ...base, has_watchable_campgrounds: true };
  assert.deepEqual(choosePickerTrail(skyline), { kind: "pick", trail: skyline });
});
