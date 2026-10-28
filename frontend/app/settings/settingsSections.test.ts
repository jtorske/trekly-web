import test from "node:test";
import assert from "node:assert/strict";
import {
  DEFAULT_SECTION,
  SETTINGS_GROUPS,
  SETTINGS_SECTIONS,
  legacySettingsHref,
  sectionHref,
  settingsLocation,
} from "./settingsSections.ts";

test("Edit profile comes first and Delete account last, in the warning colour", () => {
  assert.equal(SETTINGS_SECTIONS[0].slug, "edit-profile");
  assert.equal(DEFAULT_SECTION, "edit-profile");
  const last = SETTINGS_SECTIONS.at(-1);
  assert.equal(last?.slug, "delete-account");
  assert.equal(last?.danger, true);
  assert.equal(SETTINGS_SECTIONS.filter((section) => section.danger).length, 1);
});

test("the sidebar groups are in order, with unique slugs", () => {
  assert.deepEqual(
    SETTINGS_GROUPS.map((group) => group.heading),
    ["Your profile", "Who can see your content", "Preferences", "Account"],
  );
  assert.deepEqual(
    SETTINGS_GROUPS.at(-1)?.sections.map((section) => section.label),
    ["Email and password", "Sign out", "Delete account"],
  );
  const slugs = SETTINGS_SECTIONS.map((section) => section.slug);
  assert.equal(new Set(slugs).size, slugs.length);
});

test("settingsLocation: bare /settings is the default section, not an explicit pick", () => {
  assert.deepEqual(settingsLocation("/settings"), { slug: "edit-profile", explicit: false });
  assert.deepEqual(settingsLocation("/settings/"), { slug: "edit-profile", explicit: false });
  assert.deepEqual(settingsLocation("/settings/edit-profile"), { slug: "edit-profile", explicit: true });
  assert.deepEqual(settingsLocation("/settings/privacy"), { slug: "privacy", explicit: true });
  assert.equal(settingsLocation("/settings/nope"), null);
  assert.equal(settingsLocation("/settingsx"), null);
  assert.equal(settingsLocation("/profile"), null);
});

test("every section has its own URL", () => {
  for (const section of SETTINGS_SECTIONS) {
    assert.deepEqual(settingsLocation(sectionHref(section.slug)), { slug: section.slug, explicit: true });
  }
});

test("old profile Settings-tab links land on the matching section", () => {
  assert.equal(legacySettingsHref(""), "/settings");
  assert.equal(legacySettingsHref("#privacy"), "/settings/privacy");
  assert.equal(legacySettingsHref("#units"), "/settings/units");
  assert.equal(legacySettingsHref("#email"), "/settings/email-and-password");
  assert.equal(legacySettingsHref("#password"), "/settings/email-and-password");
  assert.equal(legacySettingsHref("#session"), "/settings/sign-out");
  assert.equal(legacySettingsHref("#delete"), "/settings/delete-account");
  assert.equal(legacySettingsHref("#whatever"), "/settings");
});
