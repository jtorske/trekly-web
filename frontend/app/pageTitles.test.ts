import test from "node:test";
import assert from "node:assert/strict";
import { readdirSync, readFileSync, existsSync } from "node:fs";
import { dirname, join, relative, sep } from "node:path";
import { fileURLToPath } from "node:url";

// Every page's <title> should end with "| Trekly" (the root layout's
// template). That only happens when the page, or a layout between it and the
// root, sets a title; otherwise it falls back to the brand-first default,
// which belongs to the landing page alone.

const APP = dirname(fileURLToPath(import.meta.url));
const SETS_TITLE = /\btitle\s*:|generateMetadata/;

function pages(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) return pages(path);
    return entry.name === "page.tsx" ? [path] : [];
  });
}

/** The page's own metadata, or a layout's on the way up (the root layout's default doesn't count). */
function titled(page: string): boolean {
  const own = readFileSync(page, "utf8");
  // "export { default, metadata } from './landing/page'": check that page instead.
  const reexport = own.match(/export \{[^}]*metadata[^}]*\} from "(\.[^"]+)"/);
  if (reexport) return titled(join(dirname(page), `${reexport[1]}.tsx`));
  if (/export (const metadata|async function generateMetadata)/.test(own) && SETS_TITLE.test(own)) return true;
  for (let dir = dirname(page); dir !== APP; dir = dirname(dir)) {
    const layout = join(dir, "layout.tsx");
    if (existsSync(layout) && SETS_TITLE.test(readFileSync(layout, "utf8"))) return true;
  }
  return false;
}

test("every page sets a title, so the template brands it", () => {
  const untitled = pages(APP)
    .filter((page) => !titled(page))
    .map((page) => relative(APP, page).split(sep).join("/"));
  assert.deepEqual(untitled, []);
});

test("no title repeats the brand the template adds", () => {
  const files = [...pages(APP), ...readdirSync(APP, { recursive: true, encoding: "utf8" }).filter((f) => f.endsWith("layout.tsx")).map((f) => join(APP, f))];
  for (const file of files) {
    const text = readFileSync(file, "utf8");
    assert.doesNotMatch(text, /title:\s*["`][^"`]*Trekly["`]/, relative(APP, file));
  }
});

test("layouts above titled pages keep a template", () => {
  // A layout's plain-string title cuts the root template off from the pages
  // below it, so their titles come out without "| Trekly".
  for (const page of pages(APP)) {
    if (!/generateMetadata|export const metadata[^;]*title/s.test(readFileSync(page, "utf8"))) continue;
    for (let dir = dirname(page); dir !== APP; dir = dirname(dir)) {
      const layout = join(dir, "layout.tsx");
      if (!existsSync(layout)) continue;
      const text = readFileSync(layout, "utf8");
      if (/title:\s*["`]/.test(text)) assert.fail(`${relative(APP, layout)} has a plain title above ${relative(APP, page)}`);
      if (/template:/.test(text)) break;
    }
  }
});
