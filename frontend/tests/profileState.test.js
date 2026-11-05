// Interaction-level test of the profile page state logic: overlapping add/remove/edit
// responses applied in arbitrary order must not lose updates. Run with `npm test`.
const test = require("node:test");
const assert = require("node:assert");
const s = require("../.test-build/profileState.js");

const c = (id, name = `C${id}`) => ({ id, name, phone: `+9230000000${id}`, relationship: "friend" });

test("overlapping add and remove both survive (functional updates)", () => {
  // Both handlers captured the same stale list [1, 2]; with functional updates the
  // second update sees the first one's result instead of the stale snapshot.
  let state = [c(1), c(2)];
  const pendingResponses = [s.contactsAdd(c(3)), s.contactsRemove(1), s.contactsAdd(c(4))];
  for (const u of pendingResponses) state = u(state);
  assert.deepStrictEqual(state.map((x) => x.id), [2, 3, 4]);
});

test("edit replaces only the matching contact and duplicate add is ignored", () => {
  let state = [c(1), c(2)];
  state = s.contactsReplace(c(2, "Edited"))(state);
  state = s.contactsAdd(c(2, "Again"))(state);
  assert.deepStrictEqual(state.map((x) => x.name), ["C1", "Edited"]);
});

test("pending keys lock and release controls independently", () => {
  let p = new Set();
  p = s.pendingAdd("add")(p); p = s.pendingAdd("contact:1")(p);
  p = s.pendingDone("add")(p);
  assert.deepStrictEqual([...p], ["contact:1"]);
});

test("422 detail becomes per-field messages", () => {
  const e = s.fieldErrorsFrom([
    { loc: ["body", "phone"], msg: "Value error, phone must contain 7 to 15 digits" },
    { loc: ["body", "name"], msg: "String should have at least 1 character" },
  ]);
  assert.deepStrictEqual(e, { phone: "phone must contain 7 to 15 digits",
    name: "String should have at least 1 character" });
  assert.deepStrictEqual(s.fieldErrorsFrom("Not found"), {});
});
