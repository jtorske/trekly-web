import type { Metadata } from "next";
import type { ReactNode } from "react";

export const metadata: Metadata = {
  title: "Search · Trekly",
  description: "Search Trekly's trails, and find other hikers to follow.",
  // Results depend on who's searching; nothing here is worth indexing.
  robots: { index: false },
};

export default function SearchLayout({ children }: { children: ReactNode }) {
  return <div className="flex flex-1 flex-col">{children}</div>;
}
