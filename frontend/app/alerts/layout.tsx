import type { Metadata } from "next";
import type { ReactNode } from "react";

// The page is a client component, so its title lives here.
export const metadata: Metadata = { title: "Alerts" };

export default function AlertsLayout({ children }: { children: ReactNode }) {
  return children;
}
