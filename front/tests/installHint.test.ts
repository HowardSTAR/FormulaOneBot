import { test } from "node:test";
import assert from "node:assert/strict";
import { mobilePlatform, shouldShowInstallHint } from "../src/helpers/installHint.ts";
test("detect phones and desktop-mode iPad, not desktop Mac", () => {
  assert.equal(mobilePlatform("iPhone", 5), "ios");
  assert.equal(mobilePlatform("Macintosh", 5), "ios");
  assert.equal(mobilePlatform("Macintosh", 0), null);
  assert.equal(mobilePlatform("Android", 5), "android");
});
test("monthly cooldown, limit and permanent dismissal", () => {
  const now = 100 * 86400000;
  assert.equal(shouldShowInstallHint({}, now), true);
  assert.equal(shouldShowInstallHint({ lastShown: now - 86400000 }, now), false);
  assert.equal(shouldShowInstallHint({ lastShown: now - 31 * 86400000, count: 1 }, now), true);
  assert.equal(shouldShowInstallHint({ count: 3 }, now), false);
  assert.equal(shouldShowInstallHint({ dismissed: true }, now), false);
});
