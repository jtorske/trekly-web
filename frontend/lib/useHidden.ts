"use client";

import { useCallback, useSyncExternalStore } from "react";
import { hiddenVersion, isHidden, subscribeHidden } from "./undo";

/**
 * isHidden(key) for lists that support Undo: re-renders whenever an item is
 * removed, restored or finally deleted. The function changes identity with
 * each change, so it can sit in a memo's dependencies.
 */
export function useHidden(): (key: string) => boolean {
  const version = useSyncExternalStore(subscribeHidden, hiddenVersion, () => 0);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  return useCallback((key: string) => isHidden(key), [version]);
}
