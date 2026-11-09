import test from "node:test";
import assert from "node:assert/strict";
import {
  BIG_THREE_SLOTS,
  bigThreeDone,
  categoriesDone,
  choose,
  nextOpenSlot,
  productsToAdd,
  type BigThreeChoices,
} from "./bigThree.ts";

type P = { id: string; name: string };
const pack: P = { id: "p1", name: "Atmos 65" };
const tent: P = { id: "t1", name: "Copper Spur" };
const quilt: P = { id: "q1", name: "Revelation" };
const pad: P = { id: "s1", name: "NeoAir XLite" };

test("one category at a time: backpack, shelter, then the sleep system's two picks", () => {
  assert.deepEqual(BIG_THREE_SLOTS.map((s) => s.slot), ["backpack", "shelter", "sleepBag", "sleepPad"]);
  assert.deepEqual([...new Set(BIG_THREE_SLOTS.map((s) => s.title))], ["Backpack", "Shelter", "Sleep system"]);
  let choices: BigThreeChoices<P> = {};
  assert.equal(nextOpenSlot(choices), "backpack");
  choices = choose(choices, "backpack", pack);
  assert.equal(nextOpenSlot(choices, "backpack"), "shelter");
  choices = choose(choices, "shelter", "none");
  assert.equal(nextOpenSlot(choices, "shelter"), "sleepBag");
  choices = choose(choices, "sleepBag", quilt);
  assert.equal(categoriesDone(choices), 2);
  assert.equal(bigThreeDone(choices), false);
  choices = choose(choices, "sleepPad", pad);
  assert.equal(nextOpenSlot(choices, "sleepPad"), null);
  assert.equal(bigThreeDone(choices), true);
  assert.equal(categoriesDone(choices), 3);
});

test("going back to an earlier pick then continues with what's still open", () => {
  const choices: BigThreeChoices<P> = { shelter: tent, sleepBag: quilt };
  assert.equal(nextOpenSlot(choices, "shelter"), "sleepPad");
  assert.equal(nextOpenSlot({ ...choices, sleepPad: pad }, "sleepPad"), "backpack");
});

test("'I don't have one / not sure' counts as an answer and adds nothing", () => {
  const choices: BigThreeChoices<P> = { backpack: "none", shelter: "none", sleepBag: "none", sleepPad: "none" };
  assert.equal(bigThreeDone(choices), true);
  assert.deepEqual(productsToAdd(choices), []);
});

test("tapping the same choice again clears it; another replaces it", () => {
  let choices = choose<P>({}, "backpack", pack);
  choices = choose(choices, "backpack", { ...pack });
  assert.equal(choices.backpack, undefined);
  choices = choose(choose(choices, "backpack", pack), "backpack", "none");
  assert.equal(choices.backpack, "none");
  assert.equal(choose(choices, "backpack", "none").backpack, undefined);
});

test("what gets added: the Big Three picks, then extras from 'Add more gear', once each", () => {
  const choices: BigThreeChoices<P> = { backpack: pack, shelter: "none", sleepBag: quilt, sleepPad: pad };
  const stove = { id: "x1", name: "PocketRocket" };
  assert.deepEqual(productsToAdd(choices, [stove, pack]).map((p) => p.id), ["p1", "q1", "s1", "x1"]);
});
