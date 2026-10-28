import SettingsSection from "./SettingsSection";
import { DEFAULT_SECTION } from "./settingsSections";

// Wide screens show Edit profile beside the list; phones show just the list.
export default function SettingsPage() {
  return <SettingsSection slug={DEFAULT_SECTION} />;
}
