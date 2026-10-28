import type { Metadata } from "next";
import type { ReactNode } from "react";
import SettingsShell from "./SettingsShell";

export const metadata: Metadata = { title: "Settings · Trekly" };

export default function SettingsLayout({ children }: { children: ReactNode }) {
  return <SettingsShell>{children}</SettingsShell>;
}
