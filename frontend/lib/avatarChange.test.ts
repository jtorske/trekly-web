import test from "node:test";
import assert from "node:assert/strict";
import { AvatarCleanupError, removeAvatar, replaceAvatar, undeletedPaths, type AvatarSteps } from "./avatarChange.ts";
import type { Profile, ProfileUpdate } from "./accountApi.ts";

const ME = "11111111-1111-4111-8111-111111111111";
const OLD = `${ME}/aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa.webp`;
const NEW = `${ME}/bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb.webp`;
const image = { blob: new Blob(["x"], { type: "image/webp" }), extension: "webp" as const };

/** Fake Storage + API that records every call in order. */
function fakeSteps(options: { failUpdate?: boolean; failRemove?: string[] } = {}) {
  const calls: string[] = [];
  const stored = new Set<string>([OLD]);
  let avatar: string | null = OLD;
  const steps: AvatarSteps = {
    upload: async (_image, onProgress) => {
      calls.push("upload");
      onProgress(1);
      stored.add(NEW);
      return NEW;
    },
    update: async (update: ProfileUpdate) => {
      calls.push(`update:${update.avatar_path}`);
      if (options.failUpdate) throw new Error("API down");
      avatar = update.avatar_path ?? null;
      return { id: ME, avatar_path: avatar } as Profile;
    },
    remove: async (paths) => {
      calls.push(`remove:${paths.join(",")}`);
      if (paths.some((path) => options.failRemove?.includes(path))) throw new Error("Storage didn't delete it");
      for (const path of paths) stored.delete(path);
    },
    announce: (profile) => calls.push(`announce:${profile.avatar_path}`),
  };
  return { steps, calls, stored, avatar: () => avatar };
}

test("replacing uploads, saves, tells the app, then deletes the old file", async () => {
  const fake = fakeSteps();
  const progress: number[] = [];
  const saved = await replaceAvatar(fake.steps, OLD, image, (fraction) => progress.push(fraction));
  assert.equal(saved.avatar_path, NEW);
  assert.deepEqual(fake.calls, ["upload", `update:${NEW}`, `announce:${NEW}`, `remove:${OLD}`]);
  assert.deepEqual([...fake.stored], [NEW]);
  assert.deepEqual(progress, [1]);
});

test("a first photo has nothing old to delete", async () => {
  const fake = fakeSteps();
  await replaceAvatar(fake.steps, null, image);
  assert.deepEqual(fake.calls, ["upload", `update:${NEW}`, `announce:${NEW}`]);
});

test("if saving fails, the new upload is deleted and the old photo stays", async () => {
  const fake = fakeSteps({ failUpdate: true });
  await assert.rejects(replaceAvatar(fake.steps, OLD, image), /API down/);
  assert.deepEqual(fake.calls, ["upload", `update:${NEW}`, `remove:${NEW}`]);
  assert.deepEqual([...fake.stored], [OLD]);
  assert.equal(fake.avatar(), OLD);
});

test("an old file that won't delete doesn't undo a saved new photo", async () => {
  const fake = fakeSteps({ failRemove: [OLD] });
  const saved = await replaceAvatar(fake.steps, OLD, image);
  assert.equal(saved.avatar_path, NEW);
});

test("removing clears the profile first, then deletes the file", async () => {
  const fake = fakeSteps();
  const saved = await removeAvatar(fake.steps, OLD);
  assert.equal(saved.avatar_path, null);
  assert.deepEqual(fake.calls, ["update:null", "announce:null", `remove:${OLD}`]);
  assert.equal(fake.stored.size, 0);
});

test("a delete Storage doesn't confirm is reported, with the path to retry", async () => {
  const fake = fakeSteps({ failRemove: [OLD] });
  await assert.rejects(removeAvatar(fake.steps, OLD), (error: unknown) => {
    assert.ok(error instanceof AvatarCleanupError);
    assert.equal(error.retryPath, OLD);
    return true;
  });
  // The profile no longer points at it, so the photo is gone from the app.
  assert.equal(fake.avatar(), null);
});

test("if clearing the profile fails, nothing is deleted", async () => {
  const fake = fakeSteps({ failUpdate: true });
  await assert.rejects(removeAvatar(fake.steps, OLD), /API down/);
  assert.deepEqual(fake.calls, ["update:null"]);
  assert.deepEqual([...fake.stored], [OLD]);
});

test("undeletedPaths: Storage's empty success for a refused delete counts as not deleted", () => {
  assert.deepEqual(undeletedPaths([OLD], [{ name: OLD }]), []);
  // What Supabase returns when a policy blocks the delete (another user's file).
  assert.deepEqual(undeletedPaths([OLD], []), [OLD]);
  assert.deepEqual(undeletedPaths([OLD], null), [OLD]);
  assert.deepEqual(undeletedPaths([OLD, NEW], [{ name: NEW }]), [OLD]);
});
