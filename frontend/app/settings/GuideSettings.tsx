"use client";

import { useEffect, useState } from "react";
import ui from "@/components/ui.module.css";
import { SCENERY_OPTIONS } from "@/lib/guide";
import { getGuideSettings, updateGuideSettings, type GuideSettings as Settings } from "@/lib/guideApi";
import { toast } from "@/lib/toast";
import { Switch } from "./PrivacySettings";
import styles from "./settings.module.css";

/**
 * Settings → Trekly Guide. Private to the owner, like Trail preferences.
 * "Use my history" off: the Guide ignores the Trail Journal, saved trails
 * and gear, and works from the planner's answers alone.
 */
export default function GuideSettings() {
  const [settings, setSettings] = useState<Settings | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    getGuideSettings(controller.signal)
      .then(setSettings)
      .catch((error: unknown) => {
        if ((error as { name?: string }).name !== "AbortError") {
          setLoadError(error instanceof Error ? error.message : "Couldn't load your Trekly Guide settings.");
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
  if (!settings) return <div className={ui.skeleton} style={{ height: "10rem" }} aria-busy="true" aria-label="Loading" />;

  const save = async (update: Partial<Settings>, what: string) => {
    const before = settings;
    setSettings({ ...settings, ...update });
    setSaving(true);
    try {
      setSettings(await updateGuideSettings(update));
      toast.success(what);
    } catch (caught) {
      setSettings(before);
      toast.failure("save your Trekly Guide settings", caught);
    } finally {
      setSaving(false);
    }
  };

  const toggleScenery = (value: string) => {
    const next = settings.scenery.includes(value)
      ? settings.scenery.filter((item) => item !== value)
      : [...settings.scenery, value];
    void save({ scenery: next }, "Scenery saved");
  };

  return (
    <div className={styles.preferences}>
      <Switch
        id="guide-use-history"
        label="Use my history to personalize Trekly Guide"
        hint="Your Trail Journal (distances, climbs, times on trail), saved trails and gear. Off: the Guide uses only what you tell it in the planner."
        checked={settings.use_history}
        disabled={saving}
        onChange={(value) => void save({ use_history: value }, value ? "Trekly Guide will use your history" : "Trekly Guide won't use your history")}
      />
      <Switch
        id="guide-dog"
        label="I usually hike with a dog"
        hint="The planner offers dog-friendly trails first."
        checked={settings.hikes_with_dog}
        disabled={saving}
        onChange={(value) => void save({ hikes_with_dog: value }, "Saved")}
      />
      <section className={styles.preferenceGroup} aria-labelledby="guide-scenery">
        <h3 id="guide-scenery" className={styles.cardTitle}>
          Scenery you like
        </h3>
        <p className={ui.hint}>Trails with these come a little higher in your picks.</p>
        <div className={ui.chips} role="group" aria-labelledby="guide-scenery">
          {SCENERY_OPTIONS.map((option) => (
            <button
              key={option.value}
              type="button"
              className={ui.chip}
              aria-pressed={settings.scenery.includes(option.value)}
              disabled={saving}
              onClick={() => toggleScenery(option.value)}
            >
              {option.label}
            </button>
          ))}
        </div>
      </section>
    </div>
  );
}
