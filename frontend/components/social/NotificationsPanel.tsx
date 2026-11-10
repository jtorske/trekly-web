"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Bell } from "lucide-react";
import Avatar from "@/components/Avatar";
import FollowButton from "@/components/FollowButton";
import ui from "@/components/ui.module.css";
import { shortAgo } from "@/lib/activity";
import { approveFollowRequest, declineFollowRequest } from "@/lib/followsApi";
import {
  actionText,
  announceUnread,
  notificationHref,
  whoText,
  type TreklyNotification,
} from "@/lib/notifications";
import { getNotifications, markNotificationsRead } from "@/lib/notificationsApi";
import { displayName } from "@/lib/publicProfile";
import { sectionHref } from "@/app/settings/settingsSections";
import { toast } from "@/lib/toast";
import styles from "./NotificationsPanel.module.css";

/**
 * The notification list, used by the bell's dropdown and /notifications.
 * Opening an item marks it read; requests are answered right here.
 */
export default function NotificationsPanel({
  onNavigate,
  variant = "page",
}: {
  /** Called after following a link (the dropdown closes). */
  onNavigate?: () => void;
  variant?: "dropdown" | "page";
}) {
  const router = useRouter();
  const [items, setItems] = useState<TreklyNotification[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (signal?: AbortSignal) => {
    setError(null);
    try {
      const body = await getNotifications(signal);
      setItems(body.items);
      announceUnread(body.unread);
    } catch (caught) {
      if ((caught as { name?: string }).name === "AbortError") return;
      setError(caught instanceof Error ? caught.message : "Your notifications didn't load.");
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    queueMicrotask(() => {
      if (!controller.signal.aborted) void load(controller.signal);
    });
    return () => controller.abort();
  }, [load]);

  const unreadCount = items?.filter((item) => item.unread).length ?? 0;

  const markRead = async (ids?: string[]) => {
    const before = items;
    setItems((prev) => prev && prev.map((item) => (!ids || ids.includes(item.id) ? { ...item, unread: false } : item)));
    try {
      announceUnread((await markNotificationsRead(ids)).unread);
    } catch (caught) {
      setItems(before);
      toast.failure("mark your notifications read", caught);
    }
  };

  const open = (item: TreklyNotification) => {
    if (item.unread) void markNotificationsRead(item.ids).then((body) => announceUnread(body.unread)).catch(() => undefined);
    onNavigate?.();
    router.push(notificationHref(item));
  };

  const answer = async (item: TreklyNotification, approve: boolean) => {
    const who = item.actors[0];
    if (!who) return;
    try {
      if (approve) await approveFollowRequest(who.username);
      else await declineFollowRequest(who.username);
      setItems((prev) => prev && prev.filter((other) => other.id !== item.id));
      toast.success(approve ? `${displayName(who)} now follows you.` : "Request declined.");
      void load();
    } catch (caught) {
      toast.failure(approve ? "approve the request" : "decline the request", caught);
    }
  };

  let body;
  if (items === null && error) {
    body = (
      <div className={styles.empty}>
        <p className={ui.error} role="alert">
          {error}
        </p>
        <button type="button" className={ui.secondary} onClick={() => void load()}>
          Try again
        </button>
      </div>
    );
  } else if (items === null) {
    body = (
      <div aria-busy="true" aria-label="Loading notifications">
        {[0, 1, 2].map((n) => (
          <div key={n} className={`${ui.skeleton} ${styles.skeletonRow}`} />
        ))}
      </div>
    );
  } else if (items.length === 0) {
    body = (
      <div className={styles.empty}>
        <Bell size={28} aria-hidden="true" className={styles.emptyIcon} />
        <p className={styles.emptyTitle}>Nothing yet</p>
        <p>New followers, follow requests, high fives and comments on your posts show up here.</p>
      </div>
    );
  } else {
    body = (
      <ul className={styles.list}>
        {items.map((item) => {
          const who = whoText(item.actors, item.actor_count);
          const single = item.actor_count === 1 ? item.actors[0] : null;
          return (
            <li key={item.id} className={`${styles.item} ${item.unread ? styles.unread : ""}`}>
              <span className={styles.avatars} aria-hidden="true">
                {item.actors.slice(0, 2).map((actor) => (
                  <Avatar key={actor.username} path={actor.avatar_path} name={actor.display_name ?? actor.username} email={null} size={item.actor_count > 1 ? 30 : 40} />
                ))}
              </span>
              <div className={styles.main}>
                <Link
                  href={notificationHref(item)}
                  className={styles.text}
                  onClick={(event) => {
                    event.preventDefault();
                    open(item);
                  }}
                >
                  <strong>{who}</strong> {actionText(item)}
                  <span className={styles.when}>
                    {" · "}
                    <time dateTime={item.created_at}>{shortAgo(item.created_at)}</time>
                  </span>
                  {item.unread && <span className={ui.srOnly}> (unread)</span>}
                </Link>
                {item.kind === "follow_request" && single && (
                  <div className={styles.actions}>
                    <button type="button" className={`${ui.primary} ${styles.small}`} onClick={() => void answer(item, true)}>
                      Approve
                    </button>
                    <button type="button" className={`${ui.secondary} ${styles.small}`} onClick={() => void answer(item, false)}>
                      Decline
                    </button>
                  </div>
                )}
              </div>
              {item.kind === "new_follower" && single && item.follow === "none" && (
                <FollowButton username={single.username} name={displayName(single)} state="none" isPrivate={false} size="sm" />
              )}
              {item.unread && <span className={styles.dot} aria-hidden="true" />}
            </li>
          );
        })}
      </ul>
    );
  }

  return (
    <div className={`${styles.panel} ${variant === "dropdown" ? styles.dropdown : ""}`}>
      <div className={styles.header}>
        {variant === "dropdown" ? <h2 className={styles.title}>Notifications</h2> : null}
        <button
          type="button"
          className={`${ui.ghost} ${styles.markAll}`}
          onClick={() => void markRead()}
          disabled={unreadCount === 0}
        >
          Mark all read
        </button>
      </div>
      <div className={styles.scroll}>{body}</div>
      <div className={styles.footer}>
        {variant === "dropdown" && (
          <Link href="/notifications" className={ui.ghost} onClick={onNavigate}>
            See all
          </Link>
        )}
        <Link href={sectionHref("notifications")} className={ui.ghost} onClick={onNavigate}>
          Notification settings
        </Link>
      </div>
    </div>
  );
}
