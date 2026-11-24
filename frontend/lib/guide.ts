/**
 * Trekly Guide's planner as data: the questions it asks, in order, and how
 * the answers become a /api/guide/recommend request. Pure, so the flow can be
 * unit tested; components/guide/GuidePlanner.tsx draws it as a conversation.
 */
import type { GuideActivity, GuideDifficulty, GuideExperience, GuideLength, RecommendRequest } from "./guideApi.ts";

/** Scenery keys, mirrored from backend app/guide/estimate.py SCENERY. */
export const SCENERY_OPTIONS: { value: string; label: string }[] = [
  { value: "lakes", label: "Lakes" },
  { value: "waterfalls", label: "Waterfalls" },
  { value: "summits", label: "Summits and views" },
  { value: "glaciers", label: "Glaciers" },
  { value: "coast", label: "Coast" },
  { value: "forest", label: "Forest" },
  { value: "larches", label: "Larches" },
  { value: "canyons", label: "Canyons" },
];

/** Months when the planner asks about winter activities (backend WINTER_MONTHS). */
const WINTER_MONTHS = new Set([12, 1, 2, 3]);
/** Snow lingers up high: the avalanche question covers alpine trails (backend SHOULDER_MONTHS). */
const SHOULDER_MONTHS = new Set([4, 5, 11]);

export type StepKey = "experience" | "when" | "activity" | "length" | "difficulty" | "where" | "dog" | "avalanche";

export interface Choice {
  value: string;
  label: string;
  hint?: string;
}

export interface Step {
  key: StepKey;
  question: string;
  choices: Choice[];
}

export interface PlannerAnswers {
  experience?: GuideExperience;
  /** "this_weekend", "next_weekend" or an ISO date. */
  when?: string;
  activity?: GuideActivity;
  length?: GuideLength | "any";
  difficulty?: GuideDifficulty;
  /** A province code or "anywhere". */
  where?: string;
  dog?: "yes" | "no";
  avalanche?: "avoid" | "allow";
}

export interface PlannerContext {
  /** Trekly knows nothing about their hiking (signed out, or no history and no level). */
  askExperience: boolean;
  homeProvince: string | null;
  /** "I usually hike with a dog" (Settings → Trekly Guide): Yes comes first. */
  dogByDefault?: boolean;
  today: Date;
}

/** Provinces with enough trails to plan around, most trails first. */
const PROVINCE_CHOICES: Choice[] = [
  { value: "AB", label: "Alberta" },
  { value: "BC", label: "BC" },
  { value: "ON", label: "Ontario" },
  { value: "QC", label: "Québec" },
  { value: "NL", label: "Newfoundland" },
  { value: "NS", label: "Nova Scotia" },
];
const PROVINCE_NAMES: Record<string, string> = {
  AB: "Alberta", BC: "BC", MB: "Manitoba", NB: "New Brunswick", NL: "Newfoundland", NS: "Nova Scotia",
  NT: "the NWT", NU: "Nunavut", ON: "Ontario", PE: "PEI", QC: "Québec", SK: "Saskatchewan", YT: "the Yukon",
};

const pad = (n: number) => String(n).padStart(2, "0");
export const isoDate = (day: Date) => `${day.getFullYear()}-${pad(day.getMonth() + 1)}-${pad(day.getDate())}`;

/** This weekend's Saturday (today on a Saturday, yesterday on a Sunday), like the backend. */
export function saturdayOf(today: Date, weeksAhead = 0): Date {
  const day = new Date(today.getFullYear(), today.getMonth(), today.getDate());
  const weekday = day.getDay(); // Sunday 0 ... Saturday 6
  const offset = weekday === 0 ? -1 : 6 - weekday;
  day.setDate(day.getDate() + offset + weeksAhead * 7);
  return day;
}

/** The date an answer means. */
export function whenDate(when: string | undefined, today: Date): Date {
  if (!when || when === "this_weekend") return saturdayOf(today);
  if (when === "next_weekend") return saturdayOf(today, 1);
  const [y, m, d] = when.split("-").map(Number);
  return new Date(y, m - 1, d);
}

export const isWinterDate = (day: Date) => WINTER_MONTHS.has(day.getMonth() + 1);
export const isShoulderDate = (day: Date) => SHOULDER_MONTHS.has(day.getMonth() + 1);

/** The next question, or null once everything needed is answered. */
export function nextStep(answers: PlannerAnswers, context: PlannerContext): Step | null {
  if (context.askExperience && !answers.experience) {
    return {
      key: "experience",
      question: "First, how much hiking have you done?",
      choices: [
        { value: "new", label: "I'm just starting" },
        { value: "few_seasons", label: "A few seasons" },
        { value: "seasoned", label: "Lots, I'm seasoned" },
      ],
    };
  }
  if (!answers.when) {
    return {
      key: "when",
      question: "When are you heading out?",
      choices: [
        { value: "this_weekend", label: "This weekend" },
        { value: "next_weekend", label: "Next weekend" },
        { value: "pick", label: "Pick a date" },
      ],
    };
  }
  const day = whenDate(answers.when, context.today);
  const winter = isWinterDate(day);
  const shoulder = isShoulderDate(day);
  if (winter && !answers.activity) {
    return {
      key: "activity",
      question: "It's winter then. What are you up for?",
      choices: [
        { value: "winter_hike", label: "Winter hike" },
        { value: "snowshoe", label: "Snowshoe" },
        { value: "xc_ski", label: "Cross-country ski" },
      ],
    };
  }
  if (!answers.length) {
    const choices: Choice[] = [
      { value: "short", label: "A few hours", hint: "Under 3 h" },
      { value: "half_day", label: "Half day", hint: "3 to 5 h" },
      { value: "full_day", label: "Full day", hint: "5 h or more" },
    ];
    if (!winter) choices.push({ value: "overnight", label: "Overnight" });
    choices.push({ value: "any", label: "Surprise me" });
    return { key: "length", question: "How long do you want to be out?", choices };
  }
  if (!answers.difficulty) {
    return {
      key: "difficulty",
      question: "How hard should it feel?",
      choices: [
        { value: "easier", label: "Take it easy" },
        { value: "similar", label: "Like usual" },
        { value: "push", label: "Push me" },
      ],
    };
  }
  if (!answers.where) {
    const home = context.homeProvince && PROVINCE_NAMES[context.homeProvince] ? context.homeProvince : null;
    const choices: Choice[] = [];
    if (home) choices.push({ value: home, label: `Near home (${PROVINCE_NAMES[home]})` });
    for (const choice of PROVINCE_CHOICES) if (choice.value !== home) choices.push(choice);
    choices.push({ value: "anywhere", label: "Anywhere" });
    return { key: "where", question: "Where would you like to go?", choices };
  }
  if (!answers.dog) {
    const no: Choice = { value: "no", label: "No" };
    const yes: Choice = { value: "yes", label: "Yes", hint: "Leash-rule trails first" };
    return { key: "dog", question: "Bringing a dog?", choices: context.dogByDefault ? [yes, no] : [no, yes] };
  }
  if ((winter || shoulder) && !answers.avalanche) {
    return {
      key: "avalanche",
      question: winter
        ? "Keep to trails with an official Simple or no-avalanche-terrain rating?"
        : "Snow lingers up high this time of year. Keep alpine picks to trails rated Simple or no avalanche terrain?",
      choices: [
        { value: "avoid", label: "Yes, please" },
        { value: "allow", label: "No, I can assess it", hint: "Adds unrated trails; check avalanche.ca" },
      ],
    };
  }
  return null;
}

/** What the user "said" for a choice, shown as their chat bubble. */
export function answerLabel(step: Step, value: string): string {
  if (step.key === "when" && /^\d{4}-\d{2}-\d{2}$/.test(value)) {
    const [y, m, d] = value.split("-").map(Number);
    return new Date(y, m - 1, d).toLocaleDateString("en-CA", { weekday: "long", month: "long", day: "numeric" });
  }
  return step.choices.find((choice) => choice.value === value)?.label ?? value;
}

export function toRequest(answers: PlannerAnswers, today: Date, excludeIds: string[] = []): RecommendRequest {
  const day = whenDate(answers.when, today);
  const winter = isWinterDate(day);
  const snowSeason = winter || isShoulderDate(day);
  return {
    date: answers.when === "this_weekend" || !answers.when ? "this_weekend" : isoDate(day),
    difficulty: answers.difficulty ?? "similar",
    length: !answers.length || answers.length === "any" ? null : answers.length,
    province: !answers.where || answers.where === "anywhere" ? null : answers.where,
    dog: answers.dog === "yes",
    activity: winter ? (answers.activity ?? "winter_hike") : "hike",
    avoid_avalanche: snowSeason ? answers.avalanche !== "allow" : null,
    exclude_ids: excludeIds,
    limit: 3,
    experience: answers.experience ?? null,
  };
}

/** A one-line summary of what was asked, for the results header. */
export function summary(answers: PlannerAnswers, today: Date): string {
  const day = whenDate(answers.when, today).toLocaleDateString("en-CA", { weekday: "short", month: "short", day: "numeric" });
  const where = !answers.where || answers.where === "anywhere" ? "anywhere" : (PROVINCE_NAMES[answers.where] ?? answers.where);
  return `${day} · ${where}`;
}

export const VERDICT_TONE: Record<string, "good" | "warn" | "stop"> = {
  ready: "good",
  stretch: "warn",
  not_yet: "stop",
};
