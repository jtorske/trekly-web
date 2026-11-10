"use client";

import { useEffect, useMemo, useState } from "react";
import { useAuth } from "@/components/AuthProvider";
import { nudgeActions, type Nudge } from "./nudges";
import { dismissNudge, getNudges } from "./nudgesApi";
import { updatePrivacy, type PrivacySettings } from "./profilesApi";
import { toast } from "./toast";

/**
 * One nudge (lib/nudges.ts) for the signed-in user. Loading it only asks the
 * API whether to show it; the setting changes only from `turnOn`, which a
 * tap calls. `enabled` false skips the request (e.g. not a trail they've hiked).
 */
export function useNudge(nudge: Nudge, enabled = true) {
  const { status } = useAuth();
  const [show, setShow] = useState(false);
  const [busy, setBusy] = useState(false);
  const actions = useMemo(() => nudgeActions(nudge, { updatePrivacy, dismissNudge }), [nudge]);
  const load = enabled && status === "signedIn";

  useEffect(() => {
    if (!load) return;
    const controller = new AbortController();
    getNudges(controller.signal)
      .then(({ active }) => setShow(active.includes(nudge)))
      // A hint only: if it doesn't load, the page simply goes without it.
      .catch(() => undefined);
    return () => controller.abort();
  }, [load, nudge]);

  /** Turns the setting on (a tap). Resolves to the saved settings, or null if it didn't save. */
  const turnOn = async (): Promise<PrivacySettings | null> => {
    setBusy(true);
    try {
      const saved = await actions.turnOn();
      setShow(false);
      return saved;
    } catch (caught) {
      toast.failure("turn that on", caught, () => void turnOn());
      return null;
    } finally {
      setBusy(false);
    }
  };

  /** Puts it away for good (✕, or a decision made). */
  const dismiss = () => {
    setShow(false);
    actions.dismiss().catch((caught: unknown) => toast.failure("hide that for good", caught));
  };

  return { show: load && show, busy, turnOn, dismiss };
}
