"use client";

import { useEffect, useState } from "react";
import type { Session } from "@supabase/supabase-js";
import { getSupabaseClient } from "./supabaseClient";

export interface SessionState {
  session: Session | null;
  isLoading: boolean;
}

/** Tracks the Supabase auth session, updating on sign-in and sign-out. */
export function useSession(): SessionState {
  const [state, setState] = useState<SessionState>({
    session: null,
    isLoading: true,
  });

  useEffect(() => {
    let supabase;
    try {
      supabase = getSupabaseClient();
    } catch {
      // Without Supabase config the app still works signed-out.
      queueMicrotask(() => setState({ session: null, isLoading: false }));
      return;
    }

    supabase.auth.getSession().then(({ data }) => {
      setState({ session: data.session, isLoading: false });
    });

    const { data } = supabase.auth.onAuthStateChange((_event, session) => {
      setState({ session, isLoading: false });
    });
    return () => data.subscription.unsubscribe();
  }, []);

  return state;
}

/**
 * Only allows same-site relative paths as post-login redirects, so a crafted
 * ?next= link can't bounce users to another origin.
 */
export function safeNextPath(next: string | null, fallback = "/gear"): string {
  if (!next || !next.startsWith("/") || next.startsWith("//") || next.startsWith("/\\")) {
    return fallback;
  }
  return next;
}

export async function signOut(): Promise<void> {
  await getSupabaseClient().auth.signOut();
}
