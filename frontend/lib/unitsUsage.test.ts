import test from "node:test";
import assert from "node:assert/strict";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";

// Every unit conversion and unit label lives in lib/units.ts. This scans the
// rest of the app for code that converts or labels units by itself.
const ROOT = join(import.meta.dirname, "..");
const ALLOWED = new Set(["lib/units.ts"]);

const CONVERSION_FACTORS =
  /\b(?:3\.28\d*|1\.609\d*|0\.621\d*|28\.349\d*|453\.59\d*|2\.54|25\.4|2\.2046\d*|29\.57\d*|10\.7639|30\.48)\b|\* ?9 ?\/ ?5|9 ?\/ ?5 ?\*/;
// A unit right after an interpolated or literal number, in a string or JSX.
// "in" only counts after a digit, since "${count} in your gear" is English.
const UNIT_LABEL = /(?:(?:\}|\d)\s?(?:mi|ft|lbs?|oz|mph|km\/h|km|kg|°[CF]?|cm|mm)|\d\s?in)(?=[\s"'`<).,]|$)/;

function sources(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (name === "node_modules" || name.startsWith(".")) return [];
    if (statSync(path).isDirectory()) return sources(path);
    return /\.tsx?$/.test(name) && !/\.test\.ts$/.test(name) ? [path] : [];
  });
}

const files = ["app", "components", "lib"].flatMap((dir) => sources(join(ROOT, dir)));

function offending(pattern: RegExp): string[] {
  const hits: string[] = [];
  for (const file of files) {
    const name = relative(ROOT, file).replaceAll("\\", "/");
    if (ALLOWED.has(name)) continue;
    readFileSync(file, "utf8")
      .split(/\r?\n/)
      .forEach((line, i) => {
        const code = line.replace(/\/\/.*$/, "").trim();
        // Comments and SVG geometry aren't unit displays.
        if (!code || code.startsWith("*") || code.startsWith("/*") || /\bd=|viewBox|points=|"M\d/.test(code)) return;
        if (pattern.test(code)) hits.push(`${name}:${i + 1}: ${code}`);
      });
  }
  return hits;
}

test("the scan covers the app", () => {
  assert.ok(files.length > 50);
});

test("no component converts units itself", () => {
  assert.deepEqual(offending(CONVERSION_FACTORS), []);
});

test("no component writes its own unit labels", () => {
  assert.deepEqual(offending(UNIT_LABEL), []);
});

test("only lib/units.ts defines unit formatters", () => {
  assert.deepEqual(
    offending(
      /function\s+(?:\w*(?:ToFeet|ToMiles|ToFahrenheit|ToOunces|ToPounds|ToInches)|format(?:Weight|Distance|Elevation|Temperature|Degrees|Wind|Precip|Snow|Capacity|Length))\b/,
    ),
    [],
  );
});
