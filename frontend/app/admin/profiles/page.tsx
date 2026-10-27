"use client";

import { Suspense, useCallback, useEffect, useState, type FormEvent } from "react";
import Link from "next/link";
import RequireAuth from "@/components/RequireAuth";
import ui from "@/components/ui.module.css";
import { ApiError } from "@/lib/api";
import { hideProfile, listHiddenProfiles, publicProfilePath, unhideProfile, type HiddenProfile } from "@/lib/profilesApi";
import profile from "@/app/profile/page.module.css";

/**
 * Profile moderation: hide a reported profile (it becomes a 404 for everyone
 * else, through the API and row-level security) or unhide it. The backend
 * checks ADMIN_USER_IDS / PHOTO_ADMIN_USER_IDS on every request; this page
 * only shows what the API allows.
 */
function ProfileModeration() {
  const [state, setState] = useState<
    { status: "loading" } | { status: "forbidden" } | { status: "error"; error: string } | { status: "ready"; hidden: HiddenProfile[] }
  >({ status: "loading" });
  const [username, setUsername] = useState("");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<{ ok: boolean; message: string } | null>(null);

  const load = useCallback((signal?: AbortSignal) => {
    listHiddenProfiles(signal)
      .then((hidden) => setState({ status: "ready", hidden }))
      .catch((error: unknown) => {
        if ((error as { name?: string }).name === "AbortError") return;
        if (error instanceof ApiError && error.status === 403) setState({ status: "forbidden" });
        else setState({ status: "error", error: error instanceof Error ? error.message : "That didn't load." });
      });
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    load(controller.signal);
    return () => controller.abort();
  }, [load]);

  const run = async (work: () => Promise<unknown>, done: string) => {
    setBusy(true);
    setResult(null);
    try {
      await work();
      setResult({ ok: true, message: done });
      load();
    } catch (caught) {
      setResult({ ok: false, message: caught instanceof Error ? caught.message : "That didn't work." });
    } finally {
      setBusy(false);
    }
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const handle = username.trim().replace(/^@/, "").toLowerCase();
    if (!handle) return;
    void run(async () => {
      await hideProfile(handle, reason);
      setUsername("");
      setReason("");
    }, `@${handle} is hidden.`);
  };

  return (
    <main className={profile.page}>
      <div className={profile.wrap}>
        <h1 className={profile.name}>Profile moderation</h1>
        {state.status === "loading" && <div className={`${ui.skeleton} ${profile.skeletonRow}`} aria-label="Loading" />}
        {state.status === "forbidden" && <p className={ui.notice}>This page is only for Trekly admins.</p>}
        {state.status === "error" && (
          <p className={ui.error} role="alert">
            {state.error}
          </p>
        )}
        {state.status === "ready" && (
          <>
            <section className={profile.card} aria-labelledby="hide-title">
              <h2 id="hide-title" className={profile.cardTitle}>
                Hide a profile
              </h2>
              <p className={profile.cardDescription}>
                Reports arrive at treklyusersupport@gmail.com. A hidden profile is &ldquo;not found&rdquo; for everyone
                but its owner, who is told it was hidden.
              </p>
              <form className={profile.form} onSubmit={submit} noValidate>
                <div className={ui.row}>
                  <label className={ui.field}>
                    <span className={ui.label}>Username</span>
                    <input className={ui.input} value={username} onChange={(e) => setUsername(e.target.value)} autoCapitalize="none" spellCheck={false} />
                  </label>
                  <label className={ui.field}>
                    <span className={ui.label}>Reason (only admins see it)</span>
                    <input className={ui.input} value={reason} onChange={(e) => setReason(e.target.value)} maxLength={500} />
                  </label>
                </div>
                <div className={profile.formActions}>
                  <button type="submit" className={ui.danger} disabled={busy || !username.trim()}>
                    Hide profile
                  </button>
                </div>
              </form>
              {result && (
                <p className={result.ok ? ui.success : ui.error} role={result.ok ? "status" : "alert"}>
                  {result.message}
                </p>
              )}
            </section>

            <section className={profile.card} aria-labelledby="hidden-title">
              <h2 id="hidden-title" className={profile.cardTitle}>
                Hidden profiles ({state.hidden.length})
              </h2>
              {state.hidden.length === 0 ? (
                <p className={ui.hint}>None.</p>
              ) : (
                <ul className={profile.trails}>
                  {state.hidden.map((row) => (
                    <li key={row.user_id} className={profile.trailRow}>
                      <span className={profile.trailLink}>
                        <span className={profile.trailName}>
                          {row.username ? (
                            <Link href={publicProfilePath(row.username)}>@{row.username}</Link>
                          ) : (
                            "(no username)"
                          )}
                          {row.display_name && ` · ${row.display_name}`}
                        </span>
                        <span className={profile.trailMeta}>
                          Hidden {new Date(row.hidden_at).toLocaleString()}
                          {row.reason && ` · ${row.reason}`}
                        </span>
                      </span>
                      {row.username && (
                        <button
                          type="button"
                          className={ui.secondary}
                          disabled={busy}
                          onClick={() => run(() => unhideProfile(row.username!), `@${row.username} is visible again.`)}
                        >
                          Unhide
                        </button>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </section>
          </>
        )}
      </div>
    </main>
  );
}

export default function ProfileModerationPage() {
  return (
    <Suspense fallback={<main className={profile.page} />}>
      <RequireAuth fallback={<main className={profile.page} aria-busy="true" />}>
        <ProfileModeration />
      </RequireAuth>
    </Suspense>
  );
}
