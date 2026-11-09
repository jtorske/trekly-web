import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";
// @ts-expect-error -- plain ESM build script, no type declarations
import { TEMPLATES, render } from "../../supabase/templates/build.mjs";
import { CONFIRM_TYPES } from "./emailLinks.ts";

/** The Supabase Auth email templates in supabase/templates (see build.mjs). */
const dir = join(process.cwd(), "..", "supabase", "templates");
const config = readFileSync(join(process.cwd(), "..", "supabase", "config.toml"), "utf8").replace(/\r\n/g, "\n");

type Template = { file: string; subject: string; code?: string };
const templates = TEMPLATES as Template[];

test("there is a template for every auth email", () => {
  assert.deepEqual(
    templates.map((t) => t.file).sort(),
    ["confirmation", "email_change", "invite", "magic_link", "reauthentication", "recovery"].map((n) => `${n}.html`),
  );
});

for (const t of templates) {
  const html = readFileSync(join(dir, t.file), "utf8");

  test(`${t.file} is up to date with build.mjs`, () => {
    assert.equal(html.replace(/\r\n/g, "\n"), render(t), "run: node supabase/templates/build.mjs");
  });

  test(`${t.file} links only through our own site`, () => {
    assert.doesNotMatch(html, /ConfirmationURL|supabase\.(co|in)|bit\.ly|tinyurl/i);
    const hrefs = [...html.matchAll(/href="([^"]+)"/g)].map((m) => m[1]);
    for (const href of hrefs) {
      assert.match(href, /^(\{\{ \.SiteURL \}\}|mailto:treklyusersupport@gmail\.com$)/, href);
    }
    if (t.code) {
      assert.match(html, /\{\{ \.Token \}\}/);
    } else {
      const links = hrefs.filter((h) => h.includes("/auth/confirm"));
      assert.equal(links.length, 2, "button + fallback link");
      const type = links[0].match(/type=([a-z_]+)$/)?.[1];
      assert.ok(type && (CONFIRM_TYPES as readonly string[]).includes(type), `known type: ${type}`);
      assert.match(links[0], /^\{\{ \.SiteURL \}\}\/auth\/confirm\?token_hash=\{\{ \.TokenHash \}\}&amp;type=/);
      assert.match(html, /Or paste this link into your browser/);
    }
  });

  test(`${t.file} is email-safe`, () => {
    assert.ok(Buffer.byteLength(html) < 30_000, "under 30 KB");
    assert.doesNotMatch(html, /<(link|style|script|iframe|form)\b/i);
    for (const img of html.match(/<img\b[^>]*>/g) ?? []) {
      assert.match(img, /\balt="[^"]+"/, img);
      assert.match(img, /src="\{\{ \.SiteURL \}\}\//, img);
      assert.match(img, /width="\d+" height="\d+"/, img);
    }
    assert.match(html, /treklyusersupport@gmail\.com/);
    assert.doesNotMatch(html, /click here|act now|free|limited time|!!/i);
  });

  test(`${t.file} is wired into config.toml with its subject`, () => {
    const key = t.file.replace(".html", "");
    const block = config.match(new RegExp(`\\[auth\\.email\\.template\\.${key}\\]\\nsubject = "([^"]+)"\\ncontent_path = "([^"]+)"`));
    assert.ok(block, `[auth.email.template.${key}] in config.toml`);
    assert.equal(block[1], t.subject);
    assert.equal(block[2], `./supabase/templates/${t.file}`);
  });
}
