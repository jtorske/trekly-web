"use client";

import { useEffect, useId, useState } from "react";
import Link from "next/link";
import { ChevronDown } from "lucide-react";
import { useAuth } from "@/components/AuthProvider";
import { sectionHref } from "@/app/settings/settingsSections";
import { VISITOR_ITEMS, itemBlocker, itemVisible, summaryLine, type VisitorItemKey } from "@/lib/nudges";
import { getPrivacy, onPrivacyUpdated, updatePrivacy, type PrivacySettings } from "@/lib/profilesApi";
import { toast } from "@/lib/toast";
import shell from "./shell.module.css";
import styles from "./VisitorsCard.module.css";

const collapsedKey = (userId: string) => `trekly:visitors-card-collapsed:${userId}`;

function readCollapsed(userId: string): boolean {
  try {
    return window.localStorage.getItem(collapsedKey(userId)) === "1";
  } catch {
    return false;
  }
}

function writeCollapsed(userId: string, collapsed: boolean) {
  try {
    if (collapsed) window.localStorage.setItem(collapsedKey(userId), "1");
    else window.localStorage.removeItem(collapsedKey(userId));
  } catch {
    // Unavailable (private mode): it simply opens next time.
  }
}

/**
 * "What visitors see" on the owner's profile: each section and community
 * feature, visible or hidden, with a quick switch that saves through the
 * privacy API (the same rules as Settings → Privacy). Collapsed, it's one
 * line; this browser remembers which.
 */
export default function VisitorsCard() {
  const { user } = useAuth();
  const [settings, setSettings] = useState<PrivacySettings | null>(null);
  // This session's choice; until then, what this browser remembers.
  const [choice, setChoice] = useState<{ userId: string; collapsed: boolean } | null>(null);
  const [saving, setSaving] = useState<VisitorItemKey | null>(null);
  const bodyId = useId();
  const userId = user?.id ?? null;

  useEffect(() => {
    const controller = new AbortController();
    getPrivacy(controller.signal)
      .then(setSettings)
      // A summary only: if it doesn't load, the profile goes without it.
      .catch(() => undefined);
    const stop = onPrivacyUpdated(setSettings);
    return () => {
      controller.abort();
      stop();
    };
  }, []);

  // Only renders after the settings load in the browser, so storage is there to read.
  if (!settings || !userId) return null;
  const collapsed = choice?.userId === userId ? choice.collapsed : readCollapsed(userId);

  const toggle = () => {
    const next = !collapsed;
    setChoice({ userId, collapsed: next });
    writeCollapsed(userId, next);
  };

  const change = async (key: VisitorItemKey, value: boolean) => {
    setSaving(key);
    try {
      setSettings(await updatePrivacy({ [key]: value }));
    } catch (caught) {
      toast.failure("save that", caught, () => void change(key, value));
    } finally {
      setSaving(null);
    }
  };

  const blocked = settings.is_private || !settings.username;

  return (
    <section className={`${shell.section} ${styles.card}`} aria-labelledby={`${bodyId}-title`}>
      <div className={styles.head}>
        <h2 id={`${bodyId}-title`} className={styles.title}>
          <button type="button" className={styles.toggle} aria-expanded={!collapsed} aria-controls={bodyId} onClick={toggle}>
            What visitors see
            <ChevronDown size={18} aria-hidden="true" className={collapsed ? styles.chevron : `${styles.chevron} ${styles.open}`} />
          </button>
        </h2>
        <Link href={sectionHref("privacy")} className={shell.sectionLink}>
          Privacy settings →
        </Link>
      </div>
      {collapsed ? (
        <p className={styles.summary}>{summaryLine(settings)}</p>
      ) : (
        <div id={bodyId} className={styles.body}>
          {blocked ? (
            <p className={styles.summary}>{summaryLine(settings)}</p>
          ) : (
            <ul className={styles.items}>
              {VISITOR_ITEMS.map((item) => {
                const reason = itemBlocker(settings, item.key);
                const visible = itemVisible(settings, item.key);
                // Like Settings: a community switch can always go off, but only on when it can take effect.
                const unavailable = reason !== null && !settings[item.key];
                return (
                  <li key={item.key}>
                    <label className={`${styles.item} ${unavailable ? styles.itemBlocked : ""}`}>
                      <span className={styles.itemText}>
                        <span className={styles.itemLabel}>{item.label}</span>
                        <span className={visible ? styles.visible : styles.hidden}>
                          {visible ? "Visible" : unavailable ? "Needs your journal shown" : "Hidden"}
                        </span>
                      </span>
                      <input
                        type="checkbox"
                        role="switch"
                        className={styles.switch}
                        checked={settings[item.key]}
                        disabled={saving !== null || unavailable}
                        aria-label={`Show ${item.label} to visitors`}
                        onChange={(event) => void change(item.key, event.target.checked)}
                      />
                    </label>
                  </li>
                );
              })}
            </ul>
          )}
          {settings.show_trip_plans && !blocked && (
            <p className={styles.warning}>Public trip plans show where and when you&apos;ll be on the trail.</p>
          )}
        </div>
      )}
    </section>
  );
}
