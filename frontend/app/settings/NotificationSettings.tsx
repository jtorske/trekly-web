"use client";

import { useEffect, useState } from "react";
import ui from "@/components/ui.module.css";
import { NOTIFICATION_TYPES, type NotificationKind, type NotificationPreferences } from "@/lib/notifications";
import { getNotificationPreferences, updateNotificationPreferences } from "@/lib/notificationsApi";
import { Switch } from "./PrivacySettings";
import styles from "./settings.module.css";

/**
 * Settings → Notifications: one switch per type. Each saves when flipped.
 * Off stops new ones and hides those you have. In-app only for now.
 */
export default function NotificationSettings() {
  const [prefs, setPrefs] = useState<NotificationPreferences | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [status, setStatus] = useState<{ ok: boolean; message: string } | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    getNotificationPreferences(controller.signal)
      .then(setPrefs)
      .catch((error: unknown) => {
        if ((error as { name?: string }).name === "AbortError") return;
        setLoadError(error instanceof Error ? error.message : "Your notification settings didn't load.");
      });
    return () => controller.abort();
  }, []);

  if (loadError) {
    return (
      <p className={ui.error} role="alert">
        {loadError}
      </p>
    );
  }
  if (!prefs) return <div className={ui.skeleton} style={{ height: "14rem" }} aria-busy="true" aria-label="Loading" />;

  const change = async (kind: NotificationKind, on: boolean) => {
    const before = prefs;
    setPrefs({ ...prefs, [kind]: on });
    setStatus(null);
    try {
      setPrefs(await updateNotificationPreferences({ [kind]: on }));
      setStatus({ ok: true, message: "Saved." });
    } catch (error) {
      setPrefs(before);
      setStatus({ ok: false, message: error instanceof Error ? error.message : "That didn't save. Try again." });
    }
  };

  return (
    <div className={styles.switchList}>
      {NOTIFICATION_TYPES.map((type) => (
        <Switch
          key={type.kind}
          id={`notify-${type.kind}`}
          label={type.label}
          hint={type.hint}
          checked={prefs[type.kind]}
          onChange={(value) => void change(type.kind, value)}
        />
      ))}
      <p className={`${styles.saveStatus} ${status?.ok === false ? styles.saveError : ""}`} role="status" aria-live="polite">
        {status?.message ?? ""}
      </p>
    </div>
  );
}
