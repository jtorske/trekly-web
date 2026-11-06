import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { joinMonth, undatedLabel } from "./hikeDate.ts";

describe("undated hikes", () => {
  it("say when the hiker joined", () => {
    const month = new Date("2026-11-03T21:00:00Z").toLocaleDateString(undefined, { month: "short", year: "numeric" });
    assert.equal(undatedLabel("2026-11-03T21:00:00Z"), `Hiked before ${month}`);
    assert.equal(undatedLabel("2026-11-03T21:00:00Z", false), `Before ${month}`);
  });

  it("fall back to Trekly when the join date isn't known", () => {
    assert.equal(undatedLabel(null), "Hiked before Trekly");
    assert.equal(undatedLabel(undefined, false), "Before Trekly");
    assert.equal(joinMonth("not a date"), null);
  });
});
