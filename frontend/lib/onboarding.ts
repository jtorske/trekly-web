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
  | "interests"
  | "regions"
  | "hiked"
  | "pack"
  | "units"
  | "privacy"
  | "done";

export const STEPS: StepKey[] = [
  "name", "photo", "home", "style", "experience", "interests", "regions", "hiked", "pack", "units", "privacy", "done",
];

/** The numbered questions ("Step 3 of 9"); the finish screen isn't one. */
export const QUESTION_COUNT = STEPS.length - 1;

/** Only the username can't be skipped. */
export function isOptional(step: StepKey): boolean {
  return step !== "name" && step !== "done";
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
  return isStep(saved) ? saved : "name";
}

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

export const INTERESTS: { value: string; label: string }[] = [
  { value: "alpine_lakes", label: "Alpine lakes" },
  { value: "summits", label: "Summits and views" },
  { value: "larches", label: "Larches in fall" },
  { value: "waterfalls", label: "Waterfalls" },
  { value: "solitude", label: "Solitude" },
  { value: "wildlife", label: "Wildlife" },
  { value: "family", label: "Easy family outings" },
  { value: "traverses", label: "Multi-day traverses" },
  { value: "coast", label: "Coast and beaches" },
  { value: "wildflowers", label: "Wildflower meadows" },
];

export interface Region {
  slug: string;
  label: string;
  /** Matches trails.park_name exactly; Explore filters by it. */
  park: string;
  province: string;
}

export const REGIONS: Region[] = [
  { slug: "banff", label: "Banff", park: "Banff National Park", province: "AB" },
  { slug: "jasper", label: "Jasper", park: "Jasper National Park", province: "AB" },
  { slug: "kananaskis", label: "Kananaskis", park: "Kananaskis Country", province: "AB" },
  { slug: "waterton", label: "Waterton Lakes", park: "Waterton Lakes National Park", province: "AB" },
  { slug: "yoho", label: "Yoho", park: "Yoho National Park", province: "BC" },
  { slug: "kootenay", label: "Kootenay", park: "Kootenay National Park", province: "BC" },
  { slug: "assiniboine", label: "Mount Assiniboine", park: "Mount Assiniboine Provincial Park", province: "BC" },
  { slug: "robson", label: "Mount Robson", park: "Mount Robson Provincial Park", province: "BC" },
  { slug: "garibaldi", label: "Garibaldi", park: "Garibaldi Provincial Park", province: "BC" },
  { slug: "joffre", label: "Joffre Lakes", park: "Joffre Lakes Provincial Park", province: "BC" },
  { slug: "kokanee", label: "Kokanee Glacier", park: "Kokanee Glacier Provincial Park", province: "BC" },
  { slug: "cape-scott", label: "Cape Scott", park: "Cape Scott Provincial Park", province: "BC" },
  { slug: "tombstone", label: "Tombstone", park: "Tombstone Territorial Park", province: "YT" },
  { slug: "kluane", label: "Kluane", park: "Kluane National Park and Reserve", province: "YT" },
  { slug: "prince-albert", label: "Prince Albert", park: "Prince Albert National Park", province: "SK" },
  { slug: "whiteshell", label: "Whiteshell", park: "Whiteshell Provincial Park", province: "MB" },
  { slug: "algonquin", label: "Algonquin", park: "Algonquin Provincial Park", province: "ON" },
  { slug: "killarney", label: "Killarney", park: "Killarney Provincial Park", province: "ON" },
  { slug: "bruce", label: "Bruce Peninsula", park: "Bruce Peninsula National Park", province: "ON" },
  { slug: "lake-superior", label: "Lake Superior", park: "Lake Superior Provincial Park", province: "ON" },
  { slug: "pukaskwa", label: "Pukaskwa", park: "Pukaskwa National Park", province: "ON" },
  { slug: "gaspesie", label: "Gaspésie", park: "Parc national de la Gaspésie", province: "QC" },
  { slug: "forillon", label: "Forillon", park: "Forillon National Park", province: "QC" },
  { slug: "cape-breton", label: "Cape Breton Highlands", park: "Cape Breton Highlands National Park", province: "NS" },
  { slug: "gros-morne", label: "Gros Morne", park: "Gros Morne National Park", province: "NL" },
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
