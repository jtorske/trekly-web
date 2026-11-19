import type { Metadata } from "next";
import type { ReactNode } from "react";

// The page is a client component, so its title lives here.
export const metadata: Metadata = { title: "Forgot your password?" };

export default function ForgotPasswordLayout({ children }: { children: ReactNode }) {
  return children;
}
