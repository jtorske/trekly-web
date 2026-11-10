/**
 * The landing hero's slideshow timing, kept free of React so it can be tested
 * with fake timers. The hero starts on the photo the server picked, then
 * crossfades through the rest of the pool in a shuffled order.
 *
 * Only one photo is ever fetched ahead: the next one, `preloadLeadMs` before
 * its turn. If it hasn't finished loading by then, the hero waits for it
 * rather than fading to a half-loaded image.
 */

/**
 * The pool's indexes in a random order, with `avoidFirst` (the photo on screen
 * now) never first, so a new cycle can't open with an immediate repeat.
 */
export function shuffledCycle(
  count: number,
  avoidFirst: number | undefined,
  random: () => number = Math.random,
): number[] {
  const order = Array.from({ length: count }, (_, i) => i);
  for (let i = order.length - 1; i > 0; i--) {
    const j = Math.min(Math.floor(random() * (i + 1)), i);
    [order[i], order[j]] = [order[j], order[i]];
  }
  if (count > 1 && order[0] === avoidFirst) {
    const swap = 1 + Math.min(Math.floor(random() * (count - 1)), count - 2);
    [order[0], order[swap]] = [order[swap], order[0]];
  }
  return order;
}

export interface RotationTimers {
  setTimeout(callback: () => void, ms: number): unknown;
  clearTimeout(handle: unknown): void;
}

export interface HeroRotationOptions {
  /** How many photos are in the pool. Fewer than two never rotates. */
  count: number;
  /** The photo already on screen (the server's pick). */
  start: number;
  /** Time each photo stays up. */
  intervalMs?: number;
  /** How long before its turn the next photo starts loading. */
  preloadLeadMs?: number;
  random?: () => number;
  timers?: RotationTimers;
  /** Start loading this photo; call `loaded(index)` once it has. */
  onPreload(index: number): void;
  /** Crossfade to this photo. */
  onShow(index: number): void;
}

export interface HeroRotation {
  /** Begins (or, after `pause`, resumes) the countdown on the current photo. */
  play(): void;
  /** Stops the countdown, e.g. while the tab is hidden. */
  pause(): void;
  /** The photo passed to `onPreload` has finished loading. */
  loaded(index: number): void;
  current(): number;
}

export const HERO_INTERVAL_MS = 7000;
export const HERO_PRELOAD_LEAD_MS = 2000;

export function createHeroRotation(options: HeroRotationOptions): HeroRotation {
  const {
    count,
    intervalMs = HERO_INTERVAL_MS,
    preloadLeadMs = Math.min(HERO_PRELOAD_LEAD_MS, intervalMs),
    random = Math.random,
    timers = globalThis,
    onPreload,
    onShow,
  } = options;

  let current = options.start;
  // The rest of this cycle: everything but the starting photo, shuffled.
  let queue = shuffledCycle(count, undefined, random).filter((i) => i !== current);
  let next: number | undefined;
  let nextLoaded = false;
  let due = false;
  let playing = false;
  let timer: unknown;

  const clear = () => {
    if (timer !== undefined) timers.clearTimeout(timer);
    timer = undefined;
  };

  const takeNext = (): number => {
    if (queue.length === 0) queue = shuffledCycle(count, current, random);
    return queue.shift()!;
  };

  const advance = () => {
    if (next === undefined) return;
    current = next;
    next = undefined;
    nextLoaded = false;
    due = false;
    onShow(current);
    schedule(intervalMs);
  };

  const preload = () => {
    if (next === undefined) {
      next = takeNext();
      onPreload(next);
    }
  };

  const becomeDue = () => {
    timer = undefined;
    preload();
    due = true;
    if (nextLoaded) advance();
  };

  // Counts down `remaining` ms to the next photo's turn, preloading it
  // `preloadLeadMs` before that.
  const schedule = (remaining: number) => {
    clear();
    const untilPreload = remaining - preloadLeadMs;
    if (untilPreload > 0) {
      timer = timers.setTimeout(() => {
        preload();
        timer = timers.setTimeout(becomeDue, preloadLeadMs);
      }, untilPreload);
    } else {
      preload();
      timer = timers.setTimeout(becomeDue, remaining);
    }
  };

  return {
    play() {
      if (playing || count < 2) return;
      playing = true;
      // Back from a hidden tab: give the current photo a full turn.
      schedule(intervalMs);
    },
    pause() {
      playing = false;
      due = false;
      clear();
    },
    loaded(index) {
      if (index !== next) return;
      nextLoaded = true;
      if (due && playing) advance();
    },
    current: () => current,
  };
}
