/**
 * App-wide toast notifications: one store, read by <Toaster /> in the root
 * layout. Call toast.success / toast.error / toast.info from anywhere (no
 * React context needed); toast.failure turns a caught error into a plain-
 * language message so raw API text never reaches a toast.
 */

export type ToastType = "success" | "error" | "info";

/** Why a toast went away. "action" means its button (Undo, Retry) was used. */
export type CloseReason = "timeout" | "dismissed" | "action" | "evicted";

export interface ToastOptions {
  /** A button, e.g. Undo or Retry. Using it closes the toast. */
  action?: { label: string; onClick: () => void };
  /** A link, e.g. "View saved". Following it closes the toast. */
  link?: { label: string; href: string };
  /** Milliseconds before it closes itself. */
  duration?: number;
  /** Called once when the toast closes, whatever the reason. */
  onClose?: (reason: CloseReason) => void;
}

export interface Toast extends Omit<ToastOptions, "duration"> {
  id: number;
  type: ToastType;
  message: string;
  duration: number;
}

export const MAX_VISIBLE = 3;
export const DURATION: Record<ToastType, number> = { success: 4000, info: 4000, error: 6000 };
/** Toasts with a button (Undo, Retry) stay long enough to reach it. */
export const ACTION_DURATION = 6000;

type Timer = { handle: ReturnType<typeof setTimeout> | null; remaining: number; startedAt: number };

let toasts: Toast[] = [];
const timers = new Map<number, Timer>();
const listeners = new Set<() => void>();
let nextId = 1;
let paused = false;

function emit() {
  for (const listener of listeners) listener();
}

function startTimer(id: number, ms: number) {
  const timer: Timer = { handle: null, remaining: ms, startedAt: Date.now() };
  if (!paused) timer.handle = setTimeout(() => close(id, "timeout"), ms);
  timers.set(id, timer);
}

function close(id: number, reason: CloseReason) {
  const found = toasts.find((t) => t.id === id);
  if (!found) return;
  const timer = timers.get(id);
  if (timer?.handle) clearTimeout(timer.handle);
  timers.delete(id);
  toasts = toasts.filter((t) => t.id !== id);
  emit();
  found.onClose?.(reason);
}

function show(type: ToastType, message: string, options: ToastOptions = {}): number {
  const duration = options.duration ?? (options.action ? Math.max(ACTION_DURATION, DURATION[type]) : DURATION[type]);
  // The same plain message twice refreshes the one already showing instead of
  // stacking. Toasts with an onClose (an Undo that commits a delete) stand
  // alone, because each one owns its own follow-up.
  if (!options.onClose) {
    const twin = toasts.find(
      (t) => t.type === type && t.message === message && !t.onClose && t.action?.label === options.action?.label,
    );
    if (twin) {
      const timer = timers.get(twin.id);
      if (timer?.handle) clearTimeout(timer.handle);
      const updated = { ...twin, ...options, duration };
      toasts = toasts.map((t) => (t.id === twin.id ? updated : t));
      startTimer(twin.id, duration);
      emit();
      return twin.id;
    }
  }
  const id = nextId++;
  toasts = [...toasts, { ...options, id, type, message, duration }];
  startTimer(id, duration);
  emit();
  // Oldest out first, so at most MAX_VISIBLE show at once.
  while (toasts.length > MAX_VISIBLE) close(toasts[0].id, "evicted");
  return id;
}

/** Plain-language follow-up for a failed request, keyed off its status. */
export function failureHint(error: unknown): string {
  const status = (error as { status?: unknown } | null)?.status;
  // fetch() rejects with a TypeError when the network is down.
  if (status === 0 || error instanceof TypeError) return "Check your connection and try again.";
  if (typeof status !== "number") return "Try again.";
  if (status === 401) return "Your session has ended. Sign in again.";
  if (status === 429) return "Wait a moment and try again.";
  if (status >= 500) return "Trekly is having trouble right now. Try again in a moment.";
  return "Try again.";
}

/** "Couldn't save the trail. Check your connection and try again." */
export function failureMessage(what: string, error: unknown): string {
  return `Couldn't ${what}. ${failureHint(error)}`;
}

/**
 * The API's own validation message (a taken username, dates out of range),
 * which belongs next to the form field rather than in a toast. Null for
 * failed requests, which toast instead.
 */
export function formProblem(error: unknown): string | null {
  const status = (error as { status?: unknown } | null)?.status;
  if ((status === 400 || status === 409 || status === 422) && error instanceof Error) return error.message;
  return null;
}

export function isAbort(error: unknown): boolean {
  return (error as { name?: string } | null)?.name === "AbortError";
}

export const toast = {
  success: (message: string, options?: ToastOptions) => show("success", message, options),
  error: (message: string, options?: ToastOptions) => show("error", message, options),
  info: (message: string, options?: ToastOptions) => show("info", message, options),
  /**
   * An error toast for a failed save or delete. `what` finishes "Couldn't …"
   * ("save the trail"); `retry` adds a Retry button. Aborted requests are
   * ignored, since the user moved on.
   */
  failure(what: string, error: unknown, retry?: () => void): number | null {
    if (isAbort(error)) return null;
    return show("error", failureMessage(what, error), retry ? { action: { label: "Retry", onClick: retry } } : {});
  },
  dismiss: (id: number) => close(id, "dismissed"),
  /** Runs a toast's button and closes it with reason "action". */
  act(id: number) {
    const found = toasts.find((t) => t.id === id);
    if (!found) return;
    close(id, "action");
    found.action?.onClick();
  },
};

/** Hovering or focusing the toasts holds every timer where it is. */
export function pauseToasts() {
  if (paused) return;
  paused = true;
  const now = Date.now();
  for (const timer of timers.values()) {
    if (timer.handle) clearTimeout(timer.handle);
    timer.handle = null;
    timer.remaining = Math.max(0, timer.remaining - (now - timer.startedAt));
  }
}

export function resumeToasts() {
  if (!paused) return;
  paused = false;
  for (const [id, timer] of timers) {
    timer.startedAt = Date.now();
    timer.handle = setTimeout(() => close(id, "timeout"), timer.remaining);
  }
}

export function subscribeToasts(listener: () => void) {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export const getToasts = () => toasts;
const EMPTY: Toast[] = [];
export const getServerToasts = () => EMPTY;

/** Tests only: drop every toast without running its onClose. */
export function resetToasts() {
  for (const timer of timers.values()) if (timer.handle) clearTimeout(timer.handle);
  timers.clear();
  toasts = [];
  paused = false;
  emit();
}
