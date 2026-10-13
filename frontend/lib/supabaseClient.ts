import { createClient, type SupabaseClient } from "@supabase/supabase-js";

let client: SupabaseClient | null = null;

/**
 * Lazily creates the Supabase client on first use, rather than throwing at
 * module import time — callers should invoke this inside the function that
 * needs it (and inside a try/catch) so a missing configuration degrades
 * gracefully instead of crashing every page that imports this module.
 *
 * Sessions persist in localStorage and refresh automatically, so a signed-in
 * user stays signed in across refreshes, direct navigation and browser
 * restarts until the refresh token expires or they sign out. Email links
 * (confirmation, password reset, email change) use the PKCE flow and land on
 * /auth/callback, which exchanges the code for a session.
 */
export function getSupabaseClient(): SupabaseClient {
  if (client) return client;

  const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

  if (!supabaseUrl || !supabaseAnonKey) {
    throw new Error(
      "Missing NEXT_PUBLIC_SUPABASE_URL or NEXT_PUBLIC_SUPABASE_ANON_KEY environment variables",
    );
  }

  client = createClient(supabaseUrl, supabaseAnonKey, {
    auth: {
      flowType: "pkce",
      persistSession: true,
      autoRefreshToken: true,
      detectSessionInUrl: true,
    },
  });
  return client;
}
