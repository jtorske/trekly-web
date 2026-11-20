import test from "node:test";
import assert from "node:assert/strict";
import { cleanComment, commentCount, postPagePath, replyPrefix, viewAllLabel } from "./activity.ts";

test("comment counts read naturally", () => {
  assert.equal(commentCount(0), "0 comments");
  assert.equal(commentCount(1), "1 comment");
  assert.equal(commentCount(14), "14 comments");
});

test("'View all' shows only when the preview doesn't hold them all", () => {
  assert.equal(viewAllLabel(2, 2), null);
  assert.equal(viewAllLabel(1, 1), null);
  assert.equal(viewAllLabel(14, 2), "View all 14 comments");
  assert.equal(viewAllLabel(2, 1), "View both comments");
});

test("a reply starts with the @mention, once", () => {
  assert.equal(replyPrefix("ana"), "@ana ");
  assert.equal(replyPrefix("ana", "nice"), "@ana nice");
  assert.equal(replyPrefix("ana", "@ana already"), "@ana already");
  assert.equal(replyPrefix("ana", "hi @ANA"), "hi @ANA");
  // A longer username that starts the same isn't a mention of her.
  assert.equal(replyPrefix("ana", "@ana_b hi"), "@ana @ana_b hi");
});

test("comment text is cleaned like the server does", () => {
  assert.equal(cleanComment("  Hello \r\n\r\n\r\n\r\nthere  "), "Hello\n\nthere");
  assert.equal(cleanComment("a  \nb"), "a\nb");
  assert.equal(cleanComment("   "), "");
});

test("a post's own page", () => {
  assert.equal(postPagePath("abc-123"), "/activity/abc-123");
});

test("high-five counts, including the author's zero", async () => {
  const { highFivesLabel } = await import("./activity.ts");
  assert.equal(highFivesLabel(0), "No high fives yet");
  assert.equal(highFivesLabel(1), "1 high five");
  assert.equal(highFivesLabel(2), "2 high fives");
});
