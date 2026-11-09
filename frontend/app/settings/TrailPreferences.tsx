"use client";

import { useEffect, useState, type FormEvent } from "react";
import { ExperienceCards, HikingStyleCards, RegionPicker } from "@/components/OnboardingChoices";
import ui from "@/components/ui.module.css";
import type { Experience, HikingStyle } from "@/lib/onboarding";
import { getPreferences, updatePreferences, type Preferences } from "@/lib/preferencesApi";
import { toast } from "@/lib/toast";
import styles from "./settings.module.css";

/**
 * Settings → Trail preferences: the /welcome answers, changeable any time.
 * Private: Trekly uses them only to pick trails, and never shows them on a profile.
 */
export default function TrailPreferences() {
  const [saved, setSaved] = useState<Preferences | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    getPreferences(controller.signal)
      .then(setSaved)
      .catch((error: unknown) => {
        if ((error as { name?: string }).name !== "AbortError") {
          setLoadError(error instanceof Error ? error.message : "Couldn't load your preferences.");
        }
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
  if (!saved) return <div className={ui.skeleton} style={{ height: "12rem" }} aria-busy="true" aria-label="Loading" />;
  return <PreferencesForm saved={saved} onSaved={setSaved} />;
}

function PreferencesForm({ saved, onSaved }: { saved: Preferences; onSaved: (prefs: Preferences) => void }) {
  const [style, setStyle] = useState<HikingStyle | null>(saved.hiking_style);
  const [experience, setExperience] = useState<Experience | null>(saved.experience);
  const [regions, setRegions] = useState(saved.favourite_regions);
  const [saving, setSaving] = useState(false);

  const same = (a: string[], b: string[]) => a.length === b.length && a.every((value, index) => value === b[index]);
  const dirty =
    style !== saved.hiking_style ||
    experience !== saved.experience ||
    !same(regions, saved.favourite_regions);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!dirty || saving) return;
    setSaving(true);
    try {
      onSaved(await updatePreferences({ hiking_style: style, experience, favourite_regions: regions }));
      toast.success("Trail preferences saved");
    } catch (caught) {
      toast.failure("save your trail preferences", caught);
    } finally {
      setSaving(false);
    }
  };

  return (
    <form className={styles.preferences} onSubmit={submit}>
      <section className={styles.preferenceGroup} aria-labelledby="pref-style">
        <h3 id="pref-style" className={styles.cardTitle}>
          How you like to hike
        </h3>
        <HikingStyleCards value={style} onChange={setStyle} />
      </section>
      <section className={styles.preferenceGroup} aria-labelledby="pref-experience">
        <h3 id="pref-experience" className={styles.cardTitle}>
          Trail experience
        </h3>
        <ExperienceCards value={experience} onChange={setExperience} />
      </section>
      <section className={styles.preferenceGroup} aria-labelledby="pref-regions">
        <h3 id="pref-regions" className={styles.cardTitle}>
          Places on your radar
        </h3>
        <p className={ui.hint}>These come first in Explore&apos;s quick filters.</p>
        <RegionPicker values={regions} onChange={setRegions} />
      </section>
      <div className={styles.preferenceActions}>
        <button type="submit" className={ui.primary} disabled={!dirty || saving}>
          {saving ? "Saving…" : "Save preferences"}
        </button>
      </div>
    </form>
  );
}
