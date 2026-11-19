import type { Metadata } from "next";
import type { ReactNode } from "react";

// The page is a client component, so its title lives here.
export const metadata: Metadata = { title: "Choose a new password" };

export default function ResetPasswordLayout({ children }: { children: ReactNode }) {
  return children;
}
