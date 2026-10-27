"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import ui from "@/components/ui.module.css";
import { getPrivacy, publicProfilePath, updatePrivacy, type PrivacySettings, type PrivacyUpdate } from "@/lib/profilesApi";
import { SECTION_LABELS, type SectionSetting } from "@/lib/publicProfile";
import styles from "./page.module.css";

type Toggle = keyof PrivacyUpdate & keyof PrivacySettings;

const SECTION_HINTS: Record<SectionSetting, string> = {
  show_journal: "The trails you've hiked, with your notes and photos, and your badges.",
  show_rank: "Your trail rank, from how many trails you've logged.",
  show_gear: "Your gear and your setups, without your notes about them.",
  show_saved_trails: "Trails you've bookmarked.",
  show_trip_plans: "The trail, dates and length of trips you're planning. Bookings and notes stay private.",
};

const SECTION_WARNINGS: Partial<Record<SectionSetting, string>> = {
  show_trip_plans: "Public trip plans show where and when you'll be on the trail.",
};

function Switch({
  id,
  label,
  hint,
  warning,
  checked,
  disabled,
  onChange,
}: {
  id: string;
  label: string;
  hint?: string;
  /** A safety note, read out with the switch. */
  warning?: string;
  checked: boolean;
  disabled?: boolean;
  onChange: (value: boolean) => void;
}) {
  return (
    <label className={`${styles.switchRow} ${disabled ? styles.switchDisabled : ""}`} htmlFor={id}>
      <span className={styles.switchText}>
        <span className={styles.switchLabel}>{label}</span>
        {hint && <span className={styles.switchHint}>{hint}</span>}
        {warning && (
          <span id={`${id}-warning`} className={styles.switchWarning}>
            <span aria-hidden="true">⚠ </span>
            {warning}
          </span>
        )}
      </span>
      <input
        id={id}
        type="checkbox"
        role="switch"
        className={styles.switch}
        checked={checked}
        disabled={disabled}
        aria-describedby={warning ? `${id}-warning` : undefined}
        onChange={(event) => onChange(event.target.checked)}
      />
    </label>
  );
}

/**
 * Settings → Privacy. Each switch saves as soon as it's flipped, and the
 * API and database apply it to the next request, so there's no Save button.
 */
export default function PrivacySettingsForm({ onEditProfile }: { onEditProfile: () => void }) {
  const [settings, setSettings] = useState<PrivacySettings | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [status, setStatus] = useState<{ ok: boolean; message: string } | null>(null);
  const [pending, setPending] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    getPrivacy(controller.signal)
      .then(setSettings)
      .catch((error: unknown) => {
        if ((error as { name?: string }).name === "AbortError") return;
        setLoadError(error instanceof Error ? error.message : "Your privacy settings didn't load.");
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
  if (!settings) return <div className={`${ui.skeleton} ${styles.skeletonRow}`} aria-label="Loading" />;

  const change = async (key: Toggle, value: boolean) => {
    const before = settings;
    setSettings({ ...settings, [key]: value });
    setPending((n) => n + 1);
    setStatus(null);
    try {
      const saved = await updatePrivacy({ [key]: value });
      setSettings(saved);
      setStatus({ ok: true, message: "Saved. Visitors see the change right away." });
    } catch (caught) {
      setSettings(before);
      setStatus({ ok: false, message: caught instanceof Error ? caught.message : "That didn't save. Try again." });
    } finally {
      setPending((n) => n - 1);
    }
  };

  const username = settings.username;
  return (
    <div className={styles.form}>
      {settings.hidden_by_moderators && (
        <p className={ui.error} role="alert">
          Trekly&apos;s moderators have hidden your profile, so nobody else can see it, whatever these settings say.
          Questions? Email <a href="mailto:treklyusersupport@gmail.com">treklyusersupport@gmail.com</a>.
        </p>
      )}
      {username ? (
        <div className={styles.privacyLinks}>
          <Link href={publicProfilePath(username)} className={ui.secondary}>
            View public profile
          </Link>
          <Link href={`${publicProfilePath(username)}?preview=1`} className={ui.ghost}>
            Preview as visitor
          </Link>
        </div>
      ) : (
        <div className={ui.notice}>
          You need a username for a public profile.{" "}
          <button type="button" className={ui.ghost} onClick={onEditProfile}>
            Choose a username
          </button>
        </div>
      )}

      <Switch
        id="privacy-private"
        label="Private profile"
        hint="Visitors see only “This profile is private”, your name, username and photo."
        checked={settings.is_private}
        onChange={(value) => change("is_private", value)}
      />

      <fieldset className={styles.switchGroup} disabled={settings.is_private}>
        <legend className={styles.switchLegend}>
          What visitors see{settings.is_private && " (turn off Private profile to choose)"}
        </legend>
        {(Object.keys(SECTION_LABELS) as SectionSetting[]).map((key) => (
          <Switch
            key={key}
            id={`privacy-${key}`}
            label={SECTION_LABELS[key]}
            hint={SECTION_HINTS[key]}
            warning={SECTION_WARNINGS[key]}
            checked={settings[key]}
            disabled={settings.is_private}
            onChange={(value) => change(key, value)}
          />
        ))}
      </fieldset>

      <fieldset className={styles.switchGroup}>
        <legend className={styles.switchLegend}>More options</legend>
        <Switch
          id="privacy-dates"
          label="Hide dates on my hikes"
          hint="Show which trails you've hiked, but not when."
          checked={settings.hide_hike_dates}
          onChange={(value) => change("hide_hike_dates", value)}
        />
        <Switch
          id="privacy-indexing"
          label="Let search engines show my profile"
          hint="Off: search engines are asked not to list your profile. Never applies while it's private."
          checked={settings.allow_search_indexing}
          onChange={(value) => change("allow_search_indexing", value)}
        />
      </fieldset>

      <p className={ui.hint}>Your email address and campsite alerts are always private.</p>
      <p className={`${styles.saveStatus} ${status?.ok === false ? styles.saveError : ""}`} role="status" aria-live="polite">
        {pending > 0 ? "Saving…" : (status?.message ?? "")}
      </p>
    </div>
  );
}
