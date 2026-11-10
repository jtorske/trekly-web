"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import Avatar from "@/components/Avatar";
import Dialog from "@/components/Dialog";
import FollowButton from "@/components/FollowButton";
import ui from "@/components/ui.module.css";
import type { FollowList, Person } from "@/lib/follows";
import {
  approveFollowRequest,
  declineFollowRequest,
  getFollowList,
  getFollowRequests,
  removeFollower,
} from "@/lib/followsApi";
import { publicProfilePath } from "@/lib/profilesApi";
import { displayName } from "@/lib/publicProfile";
import { toast } from "@/lib/toast";
import styles from "./FollowListDialog.module.css";

export type FollowTab = FollowList | "requests";

const SEARCH_DELAY_MS = 250;

/**
 * Followers and following, with search. On your own profile, followers can
 * be removed, and a private profile's requests are approved or declined on
 * their own tab. The API decides who may open the lists.
 */
export default function FollowListDialog({
  username,
  name,
  initialTab,
  owner,
  signedIn,
  requestCount = 0,
  onClose,
  onCountsChange,
}: {
  username: string;
  name: string;
  initialTab: FollowTab;
  /** Your own profile: Remove and Requests. */
  owner: boolean;
  signedIn: boolean;
  requestCount?: number;
  onClose: () => void;
  /** A follower removed or a request approved: how the counts moved. */
  onCountsChange?: (change: { followers?: number; requests?: number }) => void;
}) {
  const [tab, setTab] = useState<FollowTab>(initialTab);
  const [query, setQuery] = useState("");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState<{ key: string; items: Person[]; cursor: string | null } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [requests, setRequests] = useState(requestCount);
  const key = `${tab}:${search}`;
  const current = page?.key === key ? page : null;

  useEffect(() => {
    const timer = setTimeout(() => setSearch(query.trim()), SEARCH_DELAY_MS);
    return () => clearTimeout(timer);
  }, [query]);

  const load = useCallback(
    async (cursor: string | null, signal?: AbortSignal) => {
      setLoading(true);
      setError(null);
      try {
        const result =
          tab === "requests"
            ? await getFollowRequests({ q: search, cursor, signal })
            : await getFollowList(username, tab, { q: search, cursor, signedIn, signal });
        setPage((prev) => ({
          key,
          items: cursor && prev?.key === key ? [...prev.items, ...result.items] : result.items,
          cursor: result.next_cursor,
        }));
      } catch (caught) {
        if ((caught as { name?: string }).name === "AbortError") return;
        setError(caught instanceof Error ? caught.message : "This list didn't load.");
      } finally {
        if (!signal?.aborted) setLoading(false);
      }
    },
    [tab, search, username, signedIn, key],
  );

  useEffect(() => {
    const controller = new AbortController();
    queueMicrotask(() => {
      if (!controller.signal.aborted) void load(null, controller.signal);
    });
    return () => controller.abort();
  }, [load]);

  const drop = (who: string) =>
    setPage((prev) => prev && { ...prev, items: prev.items.filter((person) => person.username !== who) });

  const remove = async (person: Person) => {
    try {
      await removeFollower(person.username);
      drop(person.username);
      onCountsChange?.({ followers: -1 });
      toast.success(`Removed ${displayName(person)} from your followers.`);
    } catch (caught) {
      toast.failure("remove this follower", caught);
    }
  };

  const answer = async (person: Person, approve: boolean) => {
    try {
      if (approve) await approveFollowRequest(person.username);
      else await declineFollowRequest(person.username);
      drop(person.username);
      setRequests((n) => Math.max(n - 1, 0));
      onCountsChange?.({ requests: -1, ...(approve ? { followers: 1 } : {}) });
      toast.success(approve ? `${displayName(person)} now follows you.` : "Request declined.");
    } catch (caught) {
      toast.failure(approve ? "approve the request" : "decline the request", caught);
    }
  };

  const tabs: { key: FollowTab; label: string }[] = [
    { key: "followers", label: "Followers" },
    { key: "following", label: "Following" },
  ];
  if (owner && (requests > 0 || tab === "requests")) tabs.push({ key: "requests", label: "Requests" });

  let emptyText: string;
  if (search) emptyText = `Nobody matches “${search}”.`;
  else if (tab === "requests") emptyText = "No requests waiting.";
  else if (tab === "followers") emptyText = owner ? "Nobody follows you yet." : `Nobody follows ${name} yet.`;
  else emptyText = owner ? "You're not following anyone yet." : `${name} isn't following anyone yet.`;

  return (
    <Dialog title={name} subtitle={`@${username}`} onClose={onClose} size="sm" sheet>
      <div className={`${ui.chips} ${styles.tabs}`} role="group" aria-label="Show">
        {tabs.map((item) => (
          <button
            key={item.key}
            type="button"
            className={ui.chip}
            aria-pressed={tab === item.key}
            onClick={() => setTab(item.key)}
          >
            {item.label}
            {item.key === "requests" && requests > 0 && <span className={styles.badge}>{requests}</span>}
          </button>
        ))}
      </div>
      <label className={ui.srOnly} htmlFor="follow-search">
        Search by name or username
      </label>
      <input
        id="follow-search"
        className={`${ui.input} ${styles.search}`}
        type="search"
        placeholder="Search by name or username"
        value={query}
        maxLength={40}
        onChange={(event) => setQuery(event.target.value)}
      />

      {!current && error ? (
        <div className={styles.empty}>
          <p className={ui.error} role="alert">
            {error}
          </p>
          <button type="button" className={ui.secondary} onClick={() => void load(null)}>
            Try again
          </button>
        </div>
      ) : !current ? (
        <div aria-busy="true" aria-label="Loading">
          {[0, 1, 2].map((n) => (
            <div key={n} className={`${ui.skeleton} ${styles.skeletonRow}`} />
          ))}
        </div>
      ) : current.items.length === 0 ? (
        <p className={styles.empty}>{emptyText}</p>
      ) : (
        <>
          <ul className={styles.list}>
            {current.items.map((person) => (
              <li key={person.username} className={styles.row}>
                <Link href={publicProfilePath(person.username)} className={styles.who} onClick={onClose}>
                  <Avatar path={person.avatar_path} name={person.display_name ?? person.username} email={null} size={40} />
                  <span className={styles.text}>
                    <span className={styles.name}>{displayName(person)}</span>
                    <span className={styles.handle}>@{person.username}</span>
                  </span>
                </Link>
                <span className={styles.actions}>
                  {tab === "requests" ? (
                    <>
                      <button type="button" className={`${ui.primary} ${styles.small}`} onClick={() => void answer(person, true)}>
                        Approve
                      </button>
                      <button type="button" className={`${ui.secondary} ${styles.small}`} onClick={() => void answer(person, false)}>
                        Decline
                      </button>
                    </>
                  ) : (
                    <>
                      {person.follow !== null && (
                        <FollowButton
                          username={person.username}
                          name={displayName(person)}
                          state={person.follow}
                          isPrivate={person.is_private}
                          size="sm"
                        />
                      )}
                      {owner && tab === "followers" && (
                        <button
                          type="button"
                          className={`${ui.ghost} ${styles.small}`}
                          onClick={() => void remove(person)}
                          aria-label={`Remove ${displayName(person)} from your followers`}
                        >
                          Remove
                        </button>
                      )}
                    </>
                  )}
                </span>
              </li>
            ))}
          </ul>
          {current.cursor && (
            <div className={styles.more}>
              <button type="button" className={ui.secondary} onClick={() => void load(current.cursor)} disabled={loading}>
                {loading ? "Loading…" : "Show more"}
              </button>
            </div>
          )}
        </>
      )}
    </Dialog>
  );
}
