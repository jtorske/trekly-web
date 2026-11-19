import type { Metadata } from "next";
import type { ReactNode } from "react";

// The page is a client component, so its title lives here.
export const metadata: Metadata = { title: "Signing you in", robots: { index: false } };

export default function AuthLayout({ children }: { children: ReactNode }) {
  return children;
}
