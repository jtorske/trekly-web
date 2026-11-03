/**
 * Supabase's service-role key must never reach the browser. The admin area's
 * account actions use it only on the backend (backend/app/supabase_admin.py);
 * the frontend sends nothing but the signed-in user's own access token.
 *
 * Checked three ways, without needing the key itself:
 * - no frontend source names it (SUPABASE_SERVICE_ROLE_KEY, service_role,
 *   sb_secret_), so nothing can read it from process.env;
 * - no NEXT_PUBLIC_ variable (the only ones Next.js inlines into the bundle)
 *   holds a service-role JWT or a secret key, in any .env file here;
 * - the built client bundle (.next/static, after `next build`) contains no
 *   service-role JWT or secret key. Skipped when there's no build yet.
 */
import test from "node:test";
import assert from "node:assert/strict";
import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";

const ROOT = join(import.meta.dirname, "..");
const SOURCE_DIRS = ["app", "components", "hooks", "lib", "libs", "public"];
const SOURCE_FILES = ["next.config.ts", "package.json"];
const SELF = relative(ROOT, import.meta.filename);
const NAMES = /SERVICE_ROLE|service_role|sb_secret_/;
const JWT = /eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}/g;

function* walk(dir: string): Generator<string> {
  if (!existsSync(dir)) return;
  for (const name of readdirSync(dir)) {
    if (name === "node_modules" || name === ".next") continue;
    const path = join(dir, name);
    if (statSync(path).isDirectory()) yield* walk(path);
    else yield path;
  }
}

/** True if `text` holds a JWT whose role is service_role, or a new-style secret key. */
function holdsSecret(text: string): boolean {
  if (/sb_secret_[A-Za-z0-9_-]{8,}/.test(text)) return true;
  for (const token of text.match(JWT) ?? []) {
    try {
      const payload = JSON.parse(Buffer.from(token.split(".")[1], "base64url").toString("utf8"));
      if (payload?.role === "service_role") return true;
    } catch {
      // not a JWT after all
    }
  }
  return false;
}

test("the detector recognises a service-role JWT and a secret key", () => {
  const encode = (value: object) => Buffer.from(JSON.stringify(value)).toString("base64url");
  const jwt = (role: string) => `${encode({ alg: "HS256", typ: "JWT" })}.${encode({ iss: "supabase", role, exp: 1 })}.signature0123456789`;
  assert.equal(holdsSecret(`const k = "${jwt("service_role")}"`), true);
  assert.equal(holdsSecret(`const k = "${jwt("anon")}"`), false);
  assert.equal(holdsSecret("sb_secret_abcdefghijkl"), true);
  assert.equal(holdsSecret("sb_publishable_abcdefghijkl"), false);
});

test("no frontend source refers to the service-role key", () => {
  const offenders: string[] = [];
  const files = [...SOURCE_DIRS.flatMap((dir) => [...walk(join(ROOT, dir))]), ...SOURCE_FILES.map((f) => join(ROOT, f))];
  for (const file of files) {
    if (!existsSync(file) || relative(ROOT, file) === SELF || !/\.(tsx?|jsx?|mjs|json|css|html|svg|txt)$/.test(file)) continue;
    const text = readFileSync(file, "utf8");
    if (NAMES.test(text) || holdsSecret(text)) offenders.push(relative(ROOT, file));
  }
  assert.deepEqual(offenders, []);
});

test("no public (browser-inlined) environment variable holds a secret", () => {
  for (const name of readdirSync(ROOT).filter((n) => n.startsWith(".env"))) {
    for (const line of readFileSync(join(ROOT, name), "utf8").split(/\r?\n/)) {
      const match = /^\s*(NEXT_PUBLIC_[A-Z0-9_]+)\s*=\s*(.*)$/.exec(line);
      if (!match) continue;
      assert.doesNotMatch(match[1], /SERVICE|SECRET/, `${name}: ${match[1]}`);
      assert.equal(holdsSecret(match[2]), false, `${name}: ${match[1]} holds a secret key`);
    }
  }
});

test("the built client bundle holds no secret key", (t) => {
  const staticDir = join(ROOT, ".next", "static");
  if (!existsSync(staticDir)) {
    t.skip("no build yet (run next build first)");
    return;
  }
  const offenders = [...walk(staticDir)].filter((file) => holdsSecret(readFileSync(file, "latin1")));
  assert.deepEqual(offenders.map((f) => relative(ROOT, f)), []);
});
