import test, { mock } from "node:test";
import assert from "node:assert/strict";
import { createHeroRotation, shuffledCycle } from "./heroRotation.ts";

// The landing hero rotates (HeroCarousel drives this controller). Guarding it
// here because 5f2b75d once replaced the slideshow with a single photo.

function setup(count: number, start = 0, random = Math.random) {
  mock.timers.enable({ apis: ["setTimeout"] });
  const preloaded: number[] = [];
  const shown: number[] = [];
  const rotation = createHeroRotation({
    count,
    start,
    random,
    onPreload: (i) => preloaded.push(i),
    onShow: (i) => shown.push(i),
  });
  return { rotation, preloaded, shown };
}

test.afterEach(() => mock.timers.reset());

// Node's mock timers start a timeout set inside a callback from the end of the
// whole tick, so step through time the way real timers would see it.
function advance(ms: number) {
  for (; ms > 0; ms -= 100) mock.timers.tick(Math.min(100, ms));
}

test("crossfades to a new photo every 7 seconds", () => {
  const { rotation, preloaded, shown } = setup(4, 2);
  rotation.play();
  advance(4999);
  assert.deepEqual(preloaded, [], "nothing loads ahead early");
  advance(1);
  assert.equal(preloaded.length, 1, "the next photo loads 2 s before its turn");
  rotation.loaded(preloaded[0]);
  advance(1999);
  assert.deepEqual(shown, []);
  advance(1);
  assert.deepEqual(shown, [preloaded[0]]);
  assert.notEqual(shown[0], 2);
  assert.equal(rotation.current(), shown[0]);
});

test("cycles the whole pool in a shuffled order without immediate repeats", () => {
  const { rotation, preloaded, shown } = setup(5, 3);
  rotation.play();
  for (let turn = 0; turn < 20; turn++) {
    advance(5000);
    rotation.loaded(preloaded.at(-1)!);
    advance(2000);
  }
  assert.equal(shown.length, 20);
  const sequence = [3, ...shown];
  for (let i = 1; i < sequence.length; i++) assert.notEqual(sequence[i], sequence[i - 1]);
  // The first cycle (start photo + 4 more) covers every photo once.
  assert.deepEqual([...sequence.slice(0, 5)].sort(), [0, 1, 2, 3, 4]);
  assert.deepEqual([...shown.slice(4, 9)].sort(), [0, 1, 2, 3, 4]);
});

test("preloads only one photo at a time", () => {
  const { rotation, preloaded } = setup(6);
  rotation.play();
  advance(60_000);
  assert.equal(preloaded.length, 1, "waits for the next photo instead of queueing more");
});

test("waits for a slow photo, then shows it as soon as it loads", () => {
  const { rotation, preloaded, shown } = setup(3);
  rotation.play();
  advance(9000);
  assert.deepEqual(shown, []);
  rotation.loaded(preloaded[0]);
  assert.deepEqual(shown, [preloaded[0]]);
});

test("holds still while paused (hidden tab) and resumes with a full turn", () => {
  const { rotation, preloaded, shown } = setup(3);
  rotation.play();
  advance(6000);
  rotation.loaded(preloaded[0]);
  rotation.pause();
  advance(30_000);
  assert.deepEqual(shown, []);
  rotation.play();
  advance(6999);
  assert.deepEqual(shown, []);
  advance(1);
  assert.deepEqual(shown, [preloaded[0]]);
});

test("a single photo never rotates", () => {
  const { rotation, preloaded, shown } = setup(1);
  rotation.play();
  advance(60_000);
  assert.deepEqual([preloaded, shown], [[], []]);
});

test("shuffledCycle never opens with the photo on screen", () => {
  for (const r of [0, 0.2, 0.5, 0.8, 0.999999]) {
    for (let avoid = 0; avoid < 4; avoid++) {
      const order = shuffledCycle(4, avoid, () => r);
      assert.notEqual(order[0], avoid);
      assert.deepEqual([...order].sort(), [0, 1, 2, 3]);
    }
  }
});
