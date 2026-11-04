import test from "node:test";
import assert from "node:assert/strict";
import { partyLimitProblem } from "./alertRules.ts";

test("the party can't be bigger than the site's maximum group size", () => {
  const site = { name: "Lake O'Hara Backcountry Sites", max_group_size: 4 };
  assert.equal(partyLimitProblem(site, 4), null);
  assert.equal(partyLimitProblem(site, 5), "Lake O'Hara Backcountry Sites takes at most 4 people per booking.");
  assert.equal(partyLimitProblem({ name: "Corral", max_group_size: 1 }, 2), "Corral takes at most 1 person per booking.");
  // No limit published: anything the form allows.
  assert.equal(partyLimitProblem({ name: "Snowbowl", max_group_size: null }, 12), null);
});
