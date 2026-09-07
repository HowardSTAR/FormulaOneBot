import { test } from "node:test";
import assert from "node:assert/strict";
import { splitGlossaryText } from "../src/helpers/glossaryMatcher.ts";

test("longest phrase wins, Cyrillic boundaries and case are respected", () => {
  const parts = splitGlossaryText("Виртуальная машина безопасности, СПРИНТ и спринтер.");
  assert.deepEqual(parts.filter(p => p.item).map(p => p.item?.id), ["virtual-safety-car", "sprint"]);
  assert.equal(parts.map(p => p.text).join(""), "Виртуальная машина безопасности, СПРИНТ и спринтер.");
});
test("aliases, English abbreviations and repeated matches", () => {
  assert.deepEqual(splitGlossaryText("Время поула; DRS, DRS; лучший круг").filter(p => p.item).map(p => p.item?.id),
    ["pole-position", "drs", "drs", "fastest-lap"]);
});
test("plain and empty text remain unchanged", () => {
  assert.deepEqual(splitGlossaryText(""), []);
  assert.deepEqual(splitGlossaryText("Привет!"), [{ text: "Привет!" }]);
});
