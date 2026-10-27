"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import type { Session, User } from "@supabase/supabase-js";
import { getSupabaseClient } from "@/lib/supabaseClient";

export type AuthStatus = "loading" | "signedOut" | "signedIn" | "unconfigured";

interface AuthContextValue {
  status: AuthStatus;
  session: Session | null;
  user: User | null;
  /** Set when the session was ended by the provider (e.g. refresh failed). */
  sessionExpired: boolean;
  /** Clears the session; with `redirectTo`, finishes with a full-page navigation there. */
  signOut: (redirectTo?: string) => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [status, setStatus] = useState<AuthStatus>("loading");
  const [sessionExpired, setSessionExpired] = useState(false);
  // Distinguishes "the user clicked Sign out" from the provider ending the
  // session (refresh token revoked/expired), which we surface as expired.
  const signingOut = useRef(false);

  useEffect(() => {
    let supabase;
    try {
      supabase = getSupabaseClient();
    } catch {
      queueMicrotask(() => setStatus("unconfigured"));
      return;
    }

    supabase.auth.getSession().then(({ data }) => {
      setSession(data.session);
      setStatus(data.session ? "signedIn" : "signedOut");
    });

    const { data } = supabase.auth.onAuthStateChange((event, nextSession) => {
      setSession(nextSession);
      setStatus(nextSession ? "signedIn" : "signedOut");
      if (event === "SIGNED_OUT" && !signingOut.current) setSessionExpired(true);
      if (event === "SIGNED_IN") setSessionExpired(false);
    });
    return () => data.subscription.unsubscribe();
  }, []);

  const signOut = useCallback(async (redirectTo?: string) => {
    signingOut.current = true;
    try {
      const supabase = getSupabaseClient();
      // "local" clears this browser's session even if the network call fails.
      await supabase.auth.signOut({ scope: "local" });
    } finally {
      // Per-tab drafts (trip plans, pending gear picks) belong to this user.
      // Units are an account setting (profiles.units), so nothing to keep here.
      try {
        window.sessionStorage.clear();
      } catch {
        // Storage can be unavailable (private mode); nothing to clear then.
      }
      if (redirectTo) {
        // A full navigation drops every bit of in-memory signed-in state and
        // can't race with route guards reacting to the sign-out.
        window.location.replace(redirectTo);
        return;
      }
      signingOut.current = false;
      setSession(null);
      setStatus("signedOut");
      setSessionExpired(false);
    }
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({ status, session, user: session?.user ?? null, sessionExpired, signOut }),
    [status, session, sessionExpired, signOut],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside <AuthProvider>");
  return value;
}
