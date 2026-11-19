import type { Metadata } from "next";
import type { ReactNode } from "react";
import SettingsShell from "./SettingsShell";

// A layout's title replaces the root template for the pages below it, so it
// carries its own: "Privacy · Settings | Trekly".
export const metadata: Metadata = { title: { default: "Settings", template: "%s · Settings | Trekly" } };

export default function SettingsLayout({ children }: { children: ReactNode }) {
  return <SettingsShell>{children}</SettingsShell>;
}
