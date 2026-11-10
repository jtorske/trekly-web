/**
 * The /welcome setup flow: its screens, their options, where to resume, and
 * when the app sends someone there. Pure (no React, no network) so the rules
 * can be unit tested.
 *
 * The option lists mirror backend/app/preferences.py, which validates them;
 * onboarding.test.ts checks the two agree.
 */

export type StepKey =
  | "name"
  | "photo"
  | "home"
  | "style"
  | "experience"
  | "regions"
  | "hiked"
  | "pack"
  | "units"
  | "privacy"
  | "done";

export const STEPS: StepKey[] = [
  "name", "photo", "home", "style", "experience", "regions", "hiked", "pack", "units", "privacy", "done",
];

/** The numbered questions ("Step 3 of 9"); the finish screen isn't one. */
export const QUESTION_COUNT = STEPS.length - 1;

/** The questions that can't be skipped: the username, trail experience and the profile's Public/Private choice. */
export const REQUIRED_STEPS: readonly StepKey[] = ["name", "experience", "privacy"];

export function isOptional(step: StepKey): boolean {
  return step !== "done" && !REQUIRED_STEPS.includes(step);
}

/**
 * Whether Continue can be pressed: the experience and privacy steps start
 * with nothing chosen, and need a choice. (The name step checks its own
 * fields when Continue is pressed, so it can say what's missing.)
 */
export function canContinue(step: StepKey, answers: { experience: Experience | null; isPrivate: boolean | null }): boolean {
  if (step === "experience") return answers.experience !== null;
  if (step === "privacy") return answers.isPrivate !== null;
  return true;
}

/**
 * Where "Skip for now" goes: the first required question still unanswered
 * after the username. Experience first, unless it's saved already; then the
 * Public/Private step, which every run of the flow ends on.
 */
export function skipForNowTarget(savedExperience: Experience | null): StepKey {
  return savedExperience === null ? "experience" : "privacy";
}

/**
 * The step after this one. After "Skip for now" (`skipping`), answering
 * experience goes straight on to the privacy step rather than back through
 * the optional ones.
 */
export function stepAfter(step: StepKey, skipping: boolean): StepKey {
  return skipping && step === "experience" ? "privacy" : nextStep(step);
}

export function isStep(value: unknown): value is StepKey {
  return typeof value === "string" && (STEPS as string[]).includes(value);
}

/** 1-based position among the questions; the finish screen counts as past the last. */
export function stepNumber(step: StepKey): number {
  return STEPS.indexOf(step) + 1;
}

export function nextStep(step: StepKey): StepKey {
  return STEPS[Math.min(STEPS.indexOf(step) + 1, STEPS.length - 1)];
}

export function previousStep(step: StepKey): StepKey | null {
  const index = STEPS.indexOf(step);
  return index > 0 ? STEPS[index - 1] : null;
}

/**
 * Where to start: the username screen until there is one, otherwise the
 * screen they were on when they left (the finish screen included).
 */
export function resumeStep(username: string | null | undefined, saved: string | null | undefined): StepKey {
  if (!username) return "name";
  if (saved && saved in REMOVED_STEPS) return REMOVED_STEPS[saved];
  return isStep(saved) ? saved : "name";
}

/**
 * Steps that have been taken out, and where someone paused on one goes
 * instead: the step that followed it. (The API moves saved progress too,
 * migration c7e3a9f1d5b2; this covers a page loaded before it ran.)
 */
const REMOVED_STEPS: Record<string, StepKey> = { interests: "regions" };

export type HikingStyle = "day" | "overnight" | "both";
export type Experience = "new" | "few_seasons" | "seasoned";

export interface Choice<T extends string> {
  value: T;
  label: string;
  hint: string;
}

export const HIKING_STYLES: Choice<HikingStyle>[] = [
  { value: "day", label: "Day hikes", hint: "Out and back before dinner." },
  { value: "overnight", label: "Overnight backpacking", hint: "A tent, a stove and a night under the stars." },
  { value: "both", label: "Both", hint: "Whatever the weekend allows." },
];

export const EXPERIENCE_LEVELS: Choice<Experience>[] = [
  { value: "new", label: "New to hiking", hint: "We'll start with gentle, well-marked trails." },
  { value: "few_seasons", label: "A few seasons", hint: "Comfortable on a full day with some climbing." },
  { value: "seasoned", label: "Seasoned backpacker", hint: "Big days, scrambles and multi-day routes." },
];

export interface Region {
  slug: string;
  label: string;
  /** Matches trails.park_name exactly; Explore filters by it. */
  park: string;
  province: string;
  /**
   * The park's centre point, for sorting by distance: the middle of the box
   * around its trailheads in the trail data (2026-11-09), to 2 decimals.
   */
  centre: { lat: number; lon: number };
}

export const REGIONS: Region[] = [
  { slug: "banff", label: "Banff", park: "Banff National Park", province: "AB", centre: { lat: 51.52, lon: -116.26 } },
  { slug: "jasper", label: "Jasper", park: "Jasper National Park", province: "AB", centre: { lat: 52.84, lon: -117.68 } },
  { slug: "kananaskis", label: "Kananaskis", park: "Kananaskis Country", province: "AB", centre: { lat: 50.73, lon: -115.10 } },
  { slug: "waterton", label: "Waterton Lakes", park: "Waterton Lakes National Park", province: "AB", centre: { lat: 49.08, lon: -113.97 } },
  { slug: "yoho", label: "Yoho", park: "Yoho National Park", province: "BC", centre: { lat: 51.43, lon: -116.43 } },
  { slug: "kootenay", label: "Kootenay", park: "Kootenay National Park", province: "BC", centre: { lat: 51.13, lon: -116.11 } },
  { slug: "assiniboine", label: "Mount Assiniboine", park: "Mount Assiniboine Provincial Park", province: "BC", centre: { lat: 51.09, lon: -115.76 } },
  { slug: "robson", label: "Mount Robson", park: "Mount Robson Provincial Park", province: "BC", centre: { lat: 53.08, lon: -119.19 } },
  { slug: "garibaldi", label: "Garibaldi", park: "Garibaldi Provincial Park", province: "BC", centre: { lat: 50.00, lon: -122.92 } },
  { slug: "joffre", label: "Joffre Lakes", park: "Joffre Lakes Provincial Park", province: "BC", centre: { lat: 50.37, lon: -122.50 } },
  { slug: "kokanee", label: "Kokanee Glacier", park: "Kokanee Glacier Provincial Park", province: "BC", centre: { lat: 49.72, lon: -117.16 } },
  { slug: "cape-scott", label: "Cape Scott", park: "Cape Scott Provincial Park", province: "BC", centre: { lat: 50.79, lon: -128.36 } },
  { slug: "tombstone", label: "Tombstone", park: "Tombstone Territorial Park", province: "YT", centre: { lat: 64.48, lon: -138.34 } },
  { slug: "kluane", label: "Kluane", park: "Kluane National Park and Reserve", province: "YT", centre: { lat: 60.58, lon: -137.22 } },
  { slug: "prince-albert", label: "Prince Albert", park: "Prince Albert National Park", province: "SK", centre: { lat: 54.09, lon: -106.45 } },
  { slug: "whiteshell", label: "Whiteshell", park: "Whiteshell Provincial Park", province: "MB", centre: { lat: 50.08, lon: -95.35 } },
  { slug: "algonquin", label: "Algonquin", park: "Algonquin Provincial Park", province: "ON", centre: { lat: 45.32, lon: -78.56 } },
  { slug: "killarney", label: "Killarney", park: "Killarney Provincial Park", province: "ON", centre: { lat: 46.04, lon: -81.37 } },
  { slug: "bruce", label: "Bruce Peninsula", park: "Bruce Peninsula National Park", province: "ON", centre: { lat: 45.23, lon: -81.53 } },
  { slug: "lake-superior", label: "Lake Superior", park: "Lake Superior Provincial Park", province: "ON", centre: { lat: 47.34, lon: -84.64 } },
  { slug: "pukaskwa", label: "Pukaskwa", park: "Pukaskwa National Park", province: "ON", centre: { lat: 48.59, lon: -86.28 } },
  { slug: "gaspesie", label: "Gaspésie", park: "Parc national de la Gaspésie", province: "QC", centre: { lat: 48.97, lon: -66.04 } },
  { slug: "forillon", label: "Forillon", park: "Forillon National Park", province: "QC", centre: { lat: 48.80, lon: -64.23 } },
  { slug: "cape-breton", label: "Cape Breton Highlands", park: "Cape Breton Highlands National Park", province: "NS", centre: { lat: 46.74, lon: -60.70 } },
  { slug: "gros-morne", label: "Gros Morne", park: "Gros Morne National Park", province: "NL", centre: { lat: 49.64, lon: -57.94 } },
];

/** Accents and case folded, for searching "gaspesie" or "MOUNT". */
export function fold(value: string): string {
  return value.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().trim();
}

/** Regions whose name, park or province code match the search. */
export function searchRegions(query: string, provinceNames: Record<string, string> = {}): Region[] {
  const needle = fold(query);
  if (!needle) return REGIONS;
  return REGIONS.filter((region) =>
    [region.label, region.park, region.province, provinceNames[region.province] ?? ""].some((text) => fold(text).includes(needle)),
  );
}

/** The parks behind favourite region slugs, in the order they were picked. */
export function favouriteParks(slugs: readonly string[]): { park: string; label: string }[] {
  return slugs.flatMap((slug) => {
    const region = REGIONS.find((r) => r.slug === slug);
    return region ? [{ park: region.park, label: region.label }] : [];
  });
}

/** Pages anyone signed in can open before finishing setup: sign-in plumbing, the legal pages and /welcome itself. */
const OPEN_PATHS = ["/auth", "/login", "/signup", "/forgot-password", "/reset-password", "/privacy", "/terms", "/welcome"];

export function pathIsOpen(pathname: string): boolean {
  return OPEN_PATHS.some((path) => pathname === path || pathname.startsWith(`${path}/`));
}

export type GateState = "pass" | "wait" | "welcome";

/**
 * Whether the app can be shown, or the person goes to /welcome first.
 *
 * - No username yet (new by email or Google, or from before usernames were
 *   required): always /welcome. It's the one required step.
 * - A username but the flow never finished or skipped (new users mid-flow,
 *   and existing users once): /welcome too, except Settings, which the
 *   flow links to.
 * - While a signed-in user's profile loads, wait, unless this browser has
 *   already seen them set up, so no app page flashes up first. If the
 *   profile can't load at all, don't lock them out of a broken API.
 */
export function onboardingGate(input: {
  authStatus: "loading" | "signedOut" | "signedIn" | "unconfigured";
  pathname: string;
  profileLoading: boolean;
  profileError: string | null;
  username: string | null | undefined;
  onboardingPending: boolean | undefined;
  knownSetUp: boolean;
}): GateState {
  if (input.authStatus !== "signedIn" || pathIsOpen(input.pathname)) return "pass";
  if (input.profileLoading) return input.knownSetUp ? "pass" : "wait";
  if (input.profileError) return "pass";
  if (!input.username) return "welcome";
  if (!input.onboardingPending) return "pass";
  const inSettings = input.pathname === "/settings" || input.pathname.startsWith("/settings/");
  return inSettings ? "pass" : "welcome";
}

/** /welcome, coming back to `next` afterwards. */
export function welcomeHref(next: string): string {
  return next && next !== "/" ? `/welcome?next=${encodeURIComponent(next)}` : "/welcome";
}

/** Full-viewport screens that draw their own logo bar instead of the site navbar and footer. */
export function isFullPage(pathname: string): boolean {
  return /^\/(signup|welcome)(\/|$)/.test(pathname);
}

/** Where "Explore all trails" goes. */
export const EXPLORE_HREF = "/trail-list";

/**
 * The finish screen's one-line summary of what their history earned, e.g.
 * "You've stamped 12 trails, earned 4 milestones and reached Day Tripper."
 * Null when they didn't add any hikes.
 */
export function finishSummary({ stamps, milestones, rank }: { stamps: number; milestones: number; rank: string | null }): string | null {
  if (stamps <= 0) return null;
  const parts = [`stamped ${stamps} ${stamps === 1 ? "trail" : "trails"}`];
  if (milestones > 0) parts.push(`earned ${milestones} ${milestones === 1 ? "milestone" : "milestones"}`);
  if (rank) parts.push(`reached ${rank}`);
  const list = parts.length > 1 ? `${parts.slice(0, -1).join(", ")} and ${parts[parts.length - 1]}` : parts[0];
  return `You've ${list}.`;
}
