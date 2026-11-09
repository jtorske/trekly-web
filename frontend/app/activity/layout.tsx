import type { Metadata } from "next";
import type { ReactNode } from "react";

export const metadata: Metadata = {
  title: "Activity · Trekly",
  description: "What hikers have recently done: trails hiked, badges earned and ranks reached.",
};

export default function ActivityLayout({ children }: { children: ReactNode }) {
  return <div className="flex flex-1 flex-col">{children}</div>;
}
