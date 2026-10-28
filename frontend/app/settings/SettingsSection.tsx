"use client";

import type { ReactNode } from "react";
import { useRouter } from "next/navigation";
import { ChangeEmail, ChangePassword, DeleteAccount, SignOut, UnitsSetting } from "./AccountSettings";
import EditProfileSection from "./EditProfileSection";
import PrivacySettingsForm from "./PrivacySettings";
import { useSettingsProfile } from "./SettingsShell";
import { findSection, sectionHref } from "./settingsSections";
import styles from "./settings.module.css";

function Card({ title, description, children }: { title?: string; description?: string; children: ReactNode }) {
  return (
    <div className={styles.card}>
      {title && <h3 className={styles.cardTitle}>{title}</h3>}
      {description && <p className={styles.cardDescription}>{description}</p>}
      {children}
    </div>
  );
}

const DESCRIPTIONS: Record<string, string> = {
  "edit-profile": "How you appear in Trekly.",
  privacy: "Your profile can be seen by anyone at its public address. Choose what's on it.",
  units: "Distances, elevations, gear weights and weather across Trekly.",
  "sign-out": "Ends your session in this browser. Your data stays saved to your account.",
};

/** One Settings section: its heading, then its form. */
export default function SettingsSection({ slug }: { slug: string }) {
  const router = useRouter();
  const profile = useSettingsProfile();
  const section = findSection(slug);
  if (!section) return null;

  let body: ReactNode;
  switch (slug) {
    case "edit-profile":
      body = <EditProfileSection key={profile.id} profile={profile} />;
      break;
    case "privacy":
      body = (
        <Card>
          <PrivacySettingsForm onEditProfile={() => router.push(sectionHref("edit-profile"))} />
        </Card>
      );
      break;
    case "units":
      body = (
        <Card>
          <UnitsSetting />
        </Card>
      );
      break;
    case "email-and-password":
      body = (
        <>
          <Card title="Email">
            <ChangeEmail email={profile.email} />
          </Card>
          <Card title="Password">
            <ChangePassword />
          </Card>
        </>
      );
      break;
    case "sign-out":
      body = (
        <Card>
          <SignOut />
        </Card>
      );
      break;
    case "delete-account":
      body = (
        <Card>
          <DeleteAccount />
        </Card>
      );
      break;
  }

  return (
    <section className={styles.section} aria-labelledby="settings-section-title">
      <header className={styles.sectionHeader}>
        <h2 id="settings-section-title" className={styles.sectionTitle} tabIndex={-1} data-section-heading>
          {section.label}
        </h2>
        {DESCRIPTIONS[slug] && <p className={styles.sectionDescription}>{DESCRIPTIONS[slug]}</p>}
      </header>
      {body}
    </section>
  );
}
