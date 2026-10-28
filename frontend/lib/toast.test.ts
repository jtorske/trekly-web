import test, { mock } from "node:test";
import assert from "node:assert/strict";
import {
  failureMessage,
  formProblem,
  getToasts,
  MAX_VISIBLE,
  pauseToasts,
  resetToasts,
  resumeToasts,
  toast,
  type CloseReason,
} from "./toast.ts";
import { isHidden, removeWithUndo, resetHidden, reveal } from "./undo.ts";

function setup(t: test.TestContext) {
  mock.timers.enable({ apis: ["setTimeout", "Date"] });
  resetToasts();
  resetHidden();
  t.after(() => {
    resetToasts();
    resetHidden();
    mock.timers.reset();
  });
}

/** Lets a resolved or rejected promise chain finish. */
const settle = () => new Promise<void>((resolve) => setImmediate(resolve));

test("success, error and info toasts show with their type", (t) => {
  setup(t);
  toast.success("Trail saved");
  toast.error("Couldn't save the trail.");
  toast.info("Units changed");
  assert.deepEqual(
    getToasts().map((x) => [x.type, x.message]),
    [
      ["success", "Trail saved"],
      ["error", "Couldn't save the trail."],
      ["info", "Units changed"],
    ],
  );
});

test("success closes after about 4 seconds and errors after about 6", (t) => {
  setup(t);
  toast.success("Saved");
  toast.error("Failed");
  mock.timers.tick(3999);
  assert.equal(getToasts().length, 2);
  mock.timers.tick(1);
  assert.deepEqual(getToasts().map((x) => x.message), ["Failed"]);
  mock.timers.tick(2000);
  assert.equal(getToasts().length, 0);
});

test("an identical toast refreshes the one showing instead of stacking", (t) => {
  setup(t);
  toast.success("Profile saved");
  mock.timers.tick(3000);
  toast.success("Profile saved");
  assert.equal(getToasts().length, 1);
  mock.timers.tick(3000);
  assert.equal(getToasts().length, 1, "the timer restarted");
});

test("at most three show at once; the oldest goes first", (t) => {
  setup(t);
  const closed: CloseReason[] = [];
  toast.info("one", { onClose: (reason) => closed.push(reason) });
  toast.info("two");
  toast.info("three");
  toast.info("four");
  assert.equal(getToasts().length, MAX_VISIBLE);
  assert.deepEqual(getToasts().map((x) => x.message), ["two", "three", "four"]);
  assert.deepEqual(closed, ["evicted"]);
});

test("pausing holds the timer where it is", (t) => {
  setup(t);
  toast.success("Saved");
  mock.timers.tick(3000);
  pauseToasts();
  mock.timers.tick(10_000);
  assert.equal(getToasts().length, 1);
  resumeToasts();
  mock.timers.tick(999);
  assert.equal(getToasts().length, 1);
  mock.timers.tick(1);
  assert.equal(getToasts().length, 0);
});

test("dismiss and act report why the toast closed", (t) => {
  setup(t);
  const reasons: CloseReason[] = [];
  let clicked = 0;
  const a = toast.success("A", { onClose: (r) => reasons.push(r) });
  const b = toast.success("B", { action: { label: "Undo", onClick: () => clicked++ }, onClose: (r) => reasons.push(r) });
  toast.dismiss(a);
  toast.act(b);
  assert.deepEqual(reasons, ["dismissed", "action"]);
  assert.equal(clicked, 1);
  assert.equal(getToasts().length, 0);
});

test("failure messages are plain language, never the API's text", () => {
  const offline = { name: "ApiError", status: 0, message: "TypeError: Failed to fetch" };
  const server = { name: "ApiError", status: 500, message: "IntegrityError: duplicate key" };
  assert.equal(failureMessage("save the trail", offline), "Couldn't save the trail. Check your connection and try again.");
  assert.equal(
    failureMessage("save the trail", server),
    "Couldn't save the trail. Trekly is having trouble right now. Try again in a moment.",
  );
  assert.equal(failureMessage("save the trail", new TypeError("x")), "Couldn't save the trail. Check your connection and try again.");
  assert.doesNotMatch(failureMessage("save", server), /IntegrityError/);
  assert.equal(failureMessage("upload the photo", new Error("Upload failed: bucket not found")), "Couldn't upload the photo. Try again.");
});

test("validation messages stay with the form; failed requests don't", () => {
  const taken = Object.assign(new Error("That username is taken."), { status: 409 });
  assert.equal(formProblem(taken), "That username is taken.");
  assert.equal(formProblem(Object.assign(new Error("db down"), { status: 500 })), null);
  assert.equal(formProblem(new TypeError("Failed to fetch")), null);
});

test("a failed request shows an error toast with Retry", async (t) => {
  setup(t);
  let attempts = 0;
  const save = async () => {
    attempts += 1;
    if (attempts === 1) throw Object.assign(new Error("boom"), { status: 503 });
  };
  const run = () => save().then(() => toast.success("Trail saved"), (error) => toast.failure("save the trail", error, run));
  await run();
  const [shown] = getToasts();
  assert.equal(shown.type, "error");
  assert.equal(shown.message, "Couldn't save the trail. Trekly is having trouble right now. Try again in a moment.");
  assert.equal(shown.action?.label, "Retry");
  toast.act(shown.id);
  await settle();
  assert.equal(attempts, 2);
  assert.deepEqual(getToasts().map((x) => [x.type, x.message]), [["success", "Trail saved"]]);
});

test("aborted requests don't toast", (t) => {
  setup(t);
  assert.equal(toast.failure("save", Object.assign(new Error("x"), { name: "AbortError" })), null);
  assert.equal(getToasts().length, 0);
});

test("Undo restores the item and never sends the delete", async (t) => {
  setup(t);
  const server = new Set(["gear:1"]);
  let restored = 0;
  const id = removeWithUndo({
    key: "gear:1",
    message: "Removed Tent from your gear",
    what: "remove the item",
    commit: async () => void server.delete("gear:1"),
    onRestored: () => restored++,
  });
  assert.ok(isHidden("gear:1"), "hidden straight away");
  toast.act(id);
  assert.equal(isHidden("gear:1"), false);
  assert.equal(restored, 1);
  mock.timers.tick(10_000);
  await settle();
  assert.ok(server.has("gear:1"), "the delete never went out");
});

test("without Undo the delete goes out when the toast closes, and the item stays hidden", async (t) => {
  setup(t);
  const server = new Set(["plan:1"]);
  let committed = 0;
  removeWithUndo({
    key: "plan:1",
    message: "Trip plan deleted",
    what: "delete the plan",
    commit: async () => void server.delete("plan:1"),
    onCommitted: () => committed++,
  });
  mock.timers.tick(5999);
  await settle();
  assert.ok(server.has("plan:1"), "still waiting on the toast");
  mock.timers.tick(1);
  await settle();
  assert.equal(server.has("plan:1"), false);
  assert.equal(committed, 1);
  assert.ok(isHidden("plan:1"), "a stale copy of the list can't bring it back");
  reveal("plan:1");
  assert.equal(isHidden("plan:1"), false);
});

test("a failed delete puts the item back and offers Retry", async (t) => {
  setup(t);
  let fail = true;
  let restored = 0;
  removeWithUndo({
    key: "saved:lake-agnes",
    message: "Removed from saved",
    what: "remove the trail",
    commit: async () => {
      if (fail) throw Object.assign(new Error("Internal"), { status: 0 });
    },
    onRestored: () => restored++,
  });
  toast.dismiss(getToasts()[0].id);
  await settle();
  assert.equal(isHidden("saved:lake-agnes"), false);
  assert.equal(restored, 1);
  const [error] = getToasts();
  assert.equal(error.message, "Couldn't remove the trail. Check your connection and try again.");
  fail = false;
  toast.act(error.id);
  assert.ok(isHidden("saved:lake-agnes"), "Retry removes it again, with a fresh Undo");
  assert.equal(getToasts().at(-1)?.action?.label, "Undo");
});

test("re-saving before the Undo toast closes cancels the delete for good", async (t) => {
  setup(t);
  let deletes = 0;
  removeWithUndo({ key: "saved:x", message: "Removed from saved", what: "remove", commit: async () => void deletes++ });
  reveal("saved:x");
  assert.equal(isHidden("saved:x"), false);
  assert.equal(getToasts().length, 0, "the Undo toast closes with it");
  mock.timers.tick(10_000);
  await settle();
  assert.equal(deletes, 0);
});
