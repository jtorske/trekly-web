import type { Metadata } from "next";
import { Suspense } from "react";
import WelcomeFlow from "./WelcomeFlow";

export const metadata: Metadata = {
  title: "Welcome · Trekly",
  robots: { index: false },
};

/** The setup flow every new account runs once, before the app. See lib/onboarding.ts. */
export default function WelcomePage() {
  return (
    <Suspense>
      <WelcomeFlow />
    </Suspense>
  );
}
