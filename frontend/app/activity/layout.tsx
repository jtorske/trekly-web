import type { Metadata } from "next";
import type { ReactNode } from "react";

// A layout's title replaces the root template for the pages below it, so it
// carries its own: a post's page is "Post | Trekly".
export const metadata: Metadata = {
  title: { default: "Activity", template: "%s | Trekly" },
  description: "What hikers have recently done: trails hiked, badges earned and ranks reached.",
};

export default function ActivityLayout({ children }: { children: ReactNode }) {
  return <div className="flex flex-1 flex-col">{children}</div>;
}
