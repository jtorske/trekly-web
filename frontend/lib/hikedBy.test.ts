import test from "node:test";
import assert from "node:assert/strict";
import { communityBlocker, othersLabel, shortenNote } from "./hikedBy.ts";

test("othersLabel counts the hikers beyond the avatars", () => {
  assert.equal(othersLabel(0), null);
  assert.equal(othersLabel(1), "and 1 other");
  assert.equal(othersLabel(12), "and 12 others");
});

test("short notes aren't cut", () => {
  assert.equal(shortenNote("Larches were golden."), null);
  assert.equal(shortenNote("x".repeat(160)), null);
});

test("long notes are cut at a word, with an ellipsis", () => {
  const note = "The larches were at their peak and the lake was perfectly still. ".repeat(4);
  const short = shortenNote(note)!;
  assert.ok(short.length <= 161, short);
  assert.ok(short.endsWith("…"));
  assert.ok(note.startsWith(short.slice(0, -1)));
  assert.match(short, /\w…$/);
});

test("a single long word is still cut", () => {
  assert.equal(shortenNote("a".repeat(200), 10), `${"a".repeat(10)}…`);
});

test("community features need a public profile and journal", () => {
  assert.equal(communityBlocker({ is_private: false, show_journal: true }), null);
  assert.match(communityBlocker({ is_private: true, show_journal: true })!, /private/);
  assert.match(communityBlocker({ is_private: false, show_journal: false })!, /Trail Journal is hidden/);
  // Private wins: that's the switch to change first.
  assert.match(communityBlocker({ is_private: true, show_journal: false })!, /private/);
});
