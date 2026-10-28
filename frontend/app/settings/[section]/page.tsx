import type { Metadata } from "next";
import { notFound } from "next/navigation";
import SettingsSection from "../SettingsSection";
import { SETTINGS_SECTIONS, findSection } from "../settingsSections";

type Props = { params: Promise<{ section: string }> };

// Any other /settings/... is a 404.
export const dynamicParams = false;

export function generateStaticParams() {
  return SETTINGS_SECTIONS.map((section) => ({ section: section.slug }));
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const section = findSection((await params).section);
  return { title: section ? `${section.label} · Settings · Trekly` : "Settings · Trekly" };
}

export default async function SettingsSectionPage({ params }: Props) {
  const { section } = await params;
  if (!findSection(section)) notFound();
  return <SettingsSection slug={section} />;
}
