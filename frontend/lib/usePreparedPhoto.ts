"use client";

import { useRef, useState } from "react";
import { photoProblemMessage } from "./photoPrep";
import { preparePhoto, PICK_EDGE } from "./preparePhoto";

/**
 * A photo field's state: the picked photo, already upright and scaled down
 * (see lib/photoPrep.ts), whether that's still running, and why it failed.
 */
export function usePreparedPhoto(maxEdge = PICK_EDGE) {
  const [photo, setPhoto] = useState<File | null>(null);
  const [preparing, setPreparing] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  // Only the latest pick wins if someone picks again while one is preparing.
  const latest = useRef(0);

  /** Resolves false when the photo can't be used, so the caller can clear its input. */
  const pick = async (file: File | null | undefined): Promise<boolean> => {
    const pickId = ++latest.current;
    setProblem(null);
    if (!file) {
      setPhoto(null);
      setPreparing(false);
      return true;
    }
    setPreparing(true);
    try {
      const prepared = await preparePhoto(file, { maxEdge });
      if (pickId === latest.current) setPhoto(prepared);
      return true;
    } catch (caught) {
      if (pickId === latest.current) {
        setPhoto(null);
        setProblem(photoProblemMessage(caught));
      }
      return false;
    } finally {
      if (pickId === latest.current) setPreparing(false);
    }
  };

  return { photo, preparing, problem, pick };
}
