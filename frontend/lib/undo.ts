import { toast } from "./toast.ts";

/**
 * Deletes with Undo. The item disappears from every list straight away, but
 * the delete request only goes out once its toast closes without Undo, so
 * Undo just shows it again: same id, same contents, nothing re-created.
 *
 * Lists hide anything isHidden() reports. After the delete succeeds the key
 * stays hidden, so a copy of the list loaded mid-delete can't bring it back;
 * call reveal() if the same key can legitimately come back (re-saving a trail).
 */

type Entry = { state: "pending" | "removed"; commit: () => void; toastId?: number };
const hidden = new Map<string, Entry>();
const listeners = new Set<() => void>();
let version = 0;

function emit() {
  version += 1;
  for (const listener of listeners) listener();
}

export interface RemoveWithUndo {
  /** Unique per item, e.g. "gear:<id>". */
  key: string;
  /** "Removed from saved" */
  message: string;
  /** The real delete. */
  commit: () => Promise<unknown>;
  /** Finishes "Couldn't …" if the delete fails, e.g. "remove the trail". */
  what: string;
  /** After a successful delete (drop it from local state, reload counts). */
  onCommitted?: () => void;
  /** After Undo, or after a failed delete puts the item back. */
  onRestored?: () => void;
}

export function removeWithUndo({ key, message, commit, what, onCommitted, onRestored }: RemoveWithUndo): number {
  let settled = false;
  // Only this removal's own entry may commit; reveal() or a newer removal of
  // the same key replaces it.
  const entry: Entry = { state: "pending", commit: () => void run() };
  const run = async () => {
    if (settled || hidden.get(key) !== entry) return;
    settled = true;
    try {
      await commit();
      if (hidden.get(key) === entry) entry.state = "removed";
      emit();
      onCommitted?.();
    } catch (error) {
      if (hidden.get(key) === entry) hidden.delete(key);
      emit();
      onRestored?.();
      toast.failure(what, error, () => removeWithUndo({ key, message, commit, what, onCommitted, onRestored }));
    }
  };
  const previous = hidden.get(key);
  hidden.set(key, entry);
  if (previous?.toastId) toast.dismiss(previous.toastId);
  emit();
  entry.toastId = toast.success(message, {
    action: {
      label: "Undo",
      onClick: () => {
        settled = true;
        if (hidden.get(key) === entry) hidden.delete(key);
        emit();
        onRestored?.();
      },
    },
    onClose: (reason) => {
      if (reason !== "action") void run();
    },
  });
  return entry.toastId;
}

/** Cancels a pending delete (as Undo would) and forgets a finished one. */
export function reveal(key: string) {
  const entry = hidden.get(key);
  if (!entry) return;
  hidden.delete(key);
  emit();
  if (entry.state === "pending" && entry.toastId) toast.dismiss(entry.toastId);
}

export const isHidden = (key: string) => hidden.has(key);
export const isPendingRemoval = (key: string) => hidden.get(key)?.state === "pending";

/** Sends every delete still waiting on its toast (the page is going away). */
export function flushRemovals() {
  for (const entry of [...hidden.values()]) if (entry.state === "pending") entry.commit();
}

export function subscribeHidden(listener: () => void) {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export const hiddenVersion = () => version;

/** Tests only. */
export function resetHidden() {
  hidden.clear();
  emit();
}
