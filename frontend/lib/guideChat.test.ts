import test from "node:test";
import assert from "node:assert/strict";
import { MAX_TURNS, clearHistory, loadHistory, requestTurns, saveHistory, shownTrailIds, type ChatTurn } from "./guideChat.ts";

function memory() {
  const data = new Map<string, string>();
  return {
    getItem: (k: string) => data.get(k) ?? null,
    setItem: (k: string, v: string) => void data.set(k, v),
    removeItem: (k: string) => void data.delete(k),
    data,
  };
}

const card = (id: string) => ({ type: "trail" as const, trail: { id } as never, reasons: [], est_label: null, dog_note: null, dog_policy: "unknown" });

test("only the last turns go to the server, text only", () => {
  const history: ChatTurn[] = Array.from({ length: 14 }, (_, i) => ({
    role: i % 2 ? "assistant" : "user",
    content: `m${i}`,
    cards: [card(`t${i}`)],
  }));
  const sent = requestTurns(history);
  assert.equal(sent.length, MAX_TURNS);
  assert.deepEqual(sent[0], { role: "user", content: "m4" });
  assert.ok(sent.every((t) => !("cards" in t)));
});

test("shown trail ids come from trail cards, once each", () => {
  const history: ChatTurn[] = [
    { role: "assistant", content: "a", cards: [card("x"), card("y")] },
    { role: "assistant", content: "b", cards: [card("x")] },
  ];
  assert.deepEqual(shownTrailIds(history), ["x", "y"]);
});

test("history survives in session storage and clears", () => {
  const storage = memory();
  saveHistory([{ role: "user", content: "hi" }], storage);
  assert.deepEqual(loadHistory(storage), [{ role: "user", content: "hi" }]);
  clearHistory(storage);
  assert.deepEqual(loadHistory(storage), []);
  storage.setItem("trekly:guide-chat", "not json");
  assert.deepEqual(loadHistory(storage), []);
});
