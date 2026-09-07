import type { Metadata } from "next";
import { Fraunces, DM_Sans } from "next/font/google";
import "./globals.css";
import Navbar from "@/components/Navbar";

// Display/heading font: organic, editorial character that complements the
// hand-drawn Trekly logo. UI/body font: clean and highly readable so the
// interface itself doesn't compete with it. Loaded once here so every page
// inherits the same typography without re-importing fonts per page.
const display = Fraunces({
  subsets: ["latin"],
  weight: ["500", "600"],
  style: ["normal", "italic"],
  variable: "--font-display",
  display: "swap",
});

const sans = DM_Sans({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-sans",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Trekly",
  description: "Discover hiking trails and adventures",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={`h-full ${display.variable} ${sans.variable}`}>
      <body className="flex min-h-full flex-col overflow-x-hidden">
        <Navbar />

        <div className="flex min-h-0 flex-1 flex-col">{children}</div>
      </body>
    </html>
  );
}
