import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { DEFAULT_AFTER_LOGIN, safeNextPath } from "./authLogic.ts";
import {
  EXPERIENCE_LEVELS,
  finishSummary,
  HIKING_STYLES,
  QUESTION_COUNT,
  REGIONS,
  STEPS,
  favouriteParks,
  isOptional,
  nextStep,
  onboardingGate,
  pathIsOpen,
  previousStep,
  resumeStep,
  searchRegions,
  stepNumber,
  welcomeHref,
} from "./onboarding.ts";

const signedIn = {
  authStatus: "signedIn" as const,
  pathname: "/profile",
  profileLoading: false,
  profileError: null,
  username: null,
  onboardingPending: true,
  knownSetUp: false,
};

// ------------------------------------------------------------------ steps

test("ten questions, then the finish screen", () => {
  assert.equal(QUESTION_COUNT, 10);
  assert.equal(STEPS.at(-1), "done");
  assert.equal(stepNumber("home"), 3);
  assert.equal(stepNumber("regions"), 6);
  assert.equal(stepNumber("privacy"), 10);
});

test("past hikes and the pack come right after the places on their radar", () => {
  assert.deepEqual(STEPS.slice(STEPS.indexOf("regions"), STEPS.indexOf("regions") + 4), ["regions", "hiked", "pack", "units"]);
  assert.equal(isOptional("hiked"), true);
  assert.equal(isOptional("pack"), true);
});

test("only the username and privacy steps are required", () => {
  assert.equal(isOptional("name"), false);
  assert.equal(isOptional("privacy"), false);
  for (const step of STEPS.filter((s) => !["name", "privacy", "done"].includes(s))) assert.equal(isOptional(step), true, step);
});

test("next and back walk the steps in order and stop at the ends", () => {
  assert.equal(nextStep("name"), "photo");
  assert.equal(nextStep("privacy"), "done");
  assert.equal(nextStep("done"), "done");
  assert.equal(previousStep("photo"), "name");
  assert.equal(previousStep("name"), null);
});

// ----------------------------------------------------------------- resume

test("leaving and coming back resumes at the saved step", () => {
  assert.equal(resumeStep("trail_jo", "regions"), "regions");
  assert.equal(resumeStep("trail_jo", "done"), "done");
});

test("without a username it always starts at the username step", () => {
  assert.equal(resumeStep(null, "regions"), "name");
  assert.equal(resumeStep("", "units"), "name");
});

test("an existing user with nothing saved starts at the top, with their name filled in", () => {
  assert.equal(resumeStep("old_timer", null), "name");
  assert.equal(resumeStep("old_timer", "bogus"), "name");
});

// ------------------------------------------------------------------- gate

test("a new user without a username is sent to /welcome from any app page", () => {
  for (const pathname of ["/profile", "/trail-list", "/gear", "/settings/privacy", "/u/someone", "/"]) {
    assert.equal(onboardingGate({ ...signedIn, pathname }), "welcome", pathname);
  }
});

test("the Google path lands in /welcome: the callback passes, then its next page sends them on", () => {
  // A new Google account has a name from Google but no username yet.
  assert.equal(onboardingGate({ ...signedIn, pathname: "/auth/callback" }), "pass");
  assert.equal(onboardingGate({ ...signedIn, pathname: DEFAULT_AFTER_LOGIN }), "welcome");
  assert.equal(welcomeHref(DEFAULT_AFTER_LOGIN), "/welcome?next=%2Fprofile");
});

test("an email sign-up's confirmation link lands in /welcome the same way", () => {
  assert.equal(onboardingGate({ ...signedIn, pathname: "/trails/abc" }), "welcome");
  assert.equal(welcomeHref("/trails/abc?save=1"), "/welcome?next=%2Ftrails%2Fabc%3Fsave%3D1");
});

test("/welcome, sign-in plumbing and the legal pages stay open", () => {
  for (const pathname of ["/welcome", "/auth/callback", "/login", "/signup", "/privacy", "/terms", "/reset-password"]) {
    assert.equal(pathIsOpen(pathname), true, pathname);
    assert.equal(onboardingGate({ ...signedIn, pathname }), "pass", pathname);
  }
  assert.equal(pathIsOpen("/welcomes"), false);
});

test("mid-flow with a username: back to /welcome, except Settings (the flow links there)", () => {
  const midFlow = { ...signedIn, username: "trail_jo", onboardingPending: true };
  assert.equal(onboardingGate(midFlow), "welcome");
  assert.equal(onboardingGate({ ...midFlow, pathname: "/settings/privacy" }), "pass");
  assert.equal(onboardingGate({ ...midFlow, pathname: "/settings" }), "pass");
});

test("existing users see it once: pending until finished or skipped, then never again", () => {
  const existing = { ...signedIn, username: "old_timer" };
  assert.equal(onboardingGate({ ...existing, onboardingPending: true }), "welcome");
  assert.equal(onboardingGate({ ...existing, onboardingPending: false }), "pass");
});

test("finished or skipped users, signed-out visitors and loading sessions pass", () => {
  assert.equal(onboardingGate({ ...signedIn, username: "trail_jo", onboardingPending: false }), "pass");
  assert.equal(onboardingGate({ ...signedIn, authStatus: "signedOut" }), "pass");
  assert.equal(onboardingGate({ ...signedIn, authStatus: "loading" }), "pass");
});

test("while the profile loads, wait unless this browser has seen them set up", () => {
  assert.equal(onboardingGate({ ...signedIn, profileLoading: true }), "wait");
  assert.equal(onboardingGate({ ...signedIn, profileLoading: true, knownSetUp: true }), "pass");
  // Loaded: the server's answer wins over the browser's memory.
  assert.equal(onboardingGate({ ...signedIn, knownSetUp: true }), "welcome");
});

test("a profile that can't load doesn't lock the user out", () => {
  assert.equal(onboardingGate({ ...signedIn, profileError: "We couldn't reach Trekly." }), "pass");
});

test("next can't point back into /welcome or the sign-in pages", () => {
  assert.equal(safeNextPath("/welcome"), DEFAULT_AFTER_LOGIN);
  assert.equal(safeNextPath("/welcome?next=/gear"), DEFAULT_AFTER_LOGIN);
  assert.equal(safeNextPath("/trail-list"), "/trail-list");
  assert.equal(welcomeHref("/"), "/welcome");
});

// ---------------------------------------------------------------- options

test("region search matches names, parks, accents and provinces", () => {
  assert.deepEqual(searchRegions("gaspesie").map((r) => r.slug), ["gaspesie"]);
  assert.deepEqual(searchRegions("MOUNT").map((r) => r.slug), ["assiniboine", "robson"]);
  assert.ok(searchRegions("yukon", { YT: "Yukon" }).every((r) => r.province === "YT"));
  assert.equal(searchRegions("  ").length, REGIONS.length);
});

test("favourite regions become Explore parks, in pick order, ignoring unknown ones", () => {
  assert.deepEqual(favouriteParks(["yoho", "nowhere", "banff"]), [
    { park: "Yoho National Park", label: "Yoho" },
    { park: "Banff National Park", label: "Banff" },
  ]);
});

/** A Python tuple of string literals (or Region(...) slugs) from preferences.py. */
function pythonTuple(source: string, name: string): string[] {
  const match = source.match(new RegExp(`^${name} = \\(([\\s\\S]*?)\\n\\)`, "m"));
  assert.ok(match, `${name} not found in preferences.py`);
  return [...match[1].matchAll(/(?:^|\n)\s*(?:Region\()?"([^"]+)"/g)].map((m) => m[1]);
}

test("the options match the API's (backend/app/preferences.py)", () => {
  const source = readFileSync(fileURLToPath(new URL("../../backend/app/preferences.py", import.meta.url)), "utf8");
  assert.deepEqual(pythonTuple(source, "ONBOARDING_STEPS"), STEPS);
  assert.doesNotMatch(source, /^INTERESTS = /m);
  assert.deepEqual(pythonTuple(source, "REGIONS"), REGIONS.map((r) => r.slug));
  for (const region of REGIONS) {
    assert.ok(source.includes(`Region("${region.slug}", "${region.label}", "${region.park}", "${region.province}")`), region.slug);
  }
  assert.match(source, /HIKING_STYLES = \("day", "overnight", "both"\)/);
  assert.deepEqual(HIKING_STYLES.map((s) => s.value), ["day", "overnight", "both"]);
  assert.match(source, /EXPERIENCE_LEVELS = \("new", "few_seasons", "seasoned"\)/);
  assert.deepEqual(EXPERIENCE_LEVELS.map((s) => s.value), ["new", "few_seasons", "seasoned"]);
});

test("the finish summary says what their past hikes earned", () => {
  assert.equal(
    finishSummary({ stamps: 12, milestones: 4, rank: "Day Tripper" }),
    "You've stamped 12 trails, earned 4 milestones and reached Day Tripper.",
  );
  assert.equal(finishSummary({ stamps: 1, milestones: 1, rank: "Day Tripper" }), "You've stamped 1 trail, earned 1 milestone and reached Day Tripper.");
  assert.equal(finishSummary({ stamps: 2, milestones: 0, rank: "Trailhead Rookie" }), "You've stamped 2 trails and reached Trailhead Rookie.");
  assert.equal(finishSummary({ stamps: 3, milestones: 0, rank: null }), "You've stamped 3 trails.");
  assert.equal(finishSummary({ stamps: 0, milestones: 0, rank: "Trailhead Rookie" }), null);
});

test("anyone paused on the removed interests step resumes at the next one", () => {
  assert.equal(resumeStep("trail_jo", "interests"), "regions");
  assert.ok(!(STEPS as string[]).includes("interests"));
  assert.equal(nextStep("experience"), "regions");
  assert.equal(previousStep("regions"), "experience");
});
