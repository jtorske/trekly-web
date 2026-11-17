import assert from "node:assert/strict";
import test from "node:test";
import {
  commonTrailsLabel,
  hikerName,
  initialTab,
  isLimited,
  isSearchable,
  parseTab,
  hikerSearchHint,
  searchHref,
  searchTerm,
  suggestionReason,
  type HikerResult,
} from "./hikerSearch.ts";

const hiker = (overrides: Partial<HikerResult> = {}): HikerResult => ({
  username: "jordan",
  display_name: "Jordan Torske",
  avatar_path: null,
  is_private: false,
  follow: "none",
  rank: null,
  home_province: null,
  common_trails: null,
  same_province: false,
  ...overrides,
});

test("the search term drops spaces and a leading @", () => {
  assert.equal(searchTerm("  @jordan "), "jordan");
  assert.equal(searchTerm("@@jo"), "jo");
  assert.equal(searchTerm("Joëlle"), "Joëlle");
});

test("two characters at least", () => {
  assert.equal(isSearchable(""), false);
  assert.equal(isSearchable("j"), false);
  assert.equal(isSearchable("@j"), false);
  assert.equal(isSearchable(" j "), false);
  assert.equal(isSearchable("jo"), true);
  assert.equal(isSearchable("@jo"), true);
});

test("tabs: the URL's, else the remembered one, else Trails", () => {
  assert.equal(parseTab("hikers"), "hikers");
  assert.equal(parseTab("people"), null);
  assert.equal(initialTab("hikers", "trails"), "hikers");
  assert.equal(initialTab(null, "hikers"), "hikers");
  assert.equal(initialTab("nonsense", "hikers"), "hikers");
  assert.equal(initialTab(null, null), "trails");
  assert.equal(initialTab(undefined, "junk"), "trails");
});

test("search links", () => {
  assert.equal(searchHref("hikers"), "/search?tab=hikers");
  assert.equal(searchHref("hikers", " Joëlle "), "/search?tab=hikers&q=Jo%C3%ABlle");
  assert.equal(searchHref("trails", "lake agnes"), "/search?tab=trails&q=lake+agnes");
});

test("trails in common", () => {
  assert.equal(commonTrailsLabel(null), null);
  assert.equal(commonTrailsLabel(0), null);
  assert.equal(commonTrailsLabel(1), "You've both hiked 1 trail");
  assert.equal(commonTrailsLabel(3), "You've both hiked 3 trails");
  assert.equal(commonTrailsLabel(1200), "You've both hiked 1,200 trails");
});

test("suggestion reasons: trails first, then the province", () => {
  assert.equal(suggestionReason(hiker({ common_trails: 2, same_province: true }), "Alberta"), "You've both hiked 2 trails");
  assert.equal(suggestionReason(hiker({ common_trails: 0, same_province: true }), "Alberta"), "Also from Alberta");
  assert.equal(suggestionReason(hiker({ same_province: true }), null), "From your home province");
  assert.equal(suggestionReason(hiker(), "Alberta"), null);
});

test("names fall back to the username", () => {
  assert.equal(hikerName(hiker()), "Jordan Torske");
  assert.equal(hikerName(hiker({ display_name: "  " })), "@jordan");
  assert.equal(hikerName(hiker({ display_name: null })), "@jordan");
});

test("a private profile is limited until you follow it", () => {
  assert.equal(isLimited(hiker()), false);
  assert.equal(isLimited(hiker({ is_private: true })), true);
  assert.equal(isLimited(hiker({ is_private: true, follow: "requested" })), true);
  assert.equal(isLimited(hiker({ is_private: true, follow: "following" })), false);
});

test("an @ in Explore's box points to people search", () => {
  assert.equal(hikerSearchHint("@jordan"), "/search?tab=hikers&q=jordan");
  assert.equal(hikerSearchHint("  @Joëlle B"), "/search?tab=hikers&q=Jo%C3%ABlle+B");
  assert.equal(hikerSearchHint("@@jo"), "/search?tab=hikers&q=jo");
  assert.equal(hikerSearchHint("@"), null);
  assert.equal(hikerSearchHint("@  "), null);
  assert.equal(hikerSearchHint("lake @ banff"), null);
  assert.equal(hikerSearchHint("lake"), null);
});
