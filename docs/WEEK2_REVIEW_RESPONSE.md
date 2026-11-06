# Week 2 review response (PR #3, mentor @AhmedHashir10)

Scope: Week 2 only. Stack/retarget plan unchanged (this PR stays stacked on `week-1-auth-foundations`).

## 1. Atomic five-contact limit
- `create_contact` (backend/app/profiles.py) now runs `BEGIN IMMEDIATE` on the SQLite connection
  before the COUNT. That takes the RESERVED write lock, so a second writer cannot start its own
  count until the first commits or rolls back. Count, insert, audit row and commit all happen
  inside that one reservation.
- Bounded conflict handling: the SQLite busy timeout is 5 s (`backend/app/db.py`). If the lock
  cannot be acquired in time, the API returns `503 {"detail": "Profile is busy, please retry"}`
  and writes nothing.
- Documented rejection: `409 {"detail": "At most 5 emergency contacts allowed"}`, no audit row.
- Other databases: lock the parent `users` row with `SELECT ... FOR UPDATE` before counting and
  hold it through the insert and audit commit. Not needed for the supported SQLite stack.
- Regression: `test_contact_limit_two_connection_race` starts from 4 contacts, pauses request A
  inside its open transaction, starts request B on a separate connection, asserts B is blocked,
  releases A, then asserts A=201, B=409 with the documented detail, exactly 5 rows persisted and
  5 create audit rows (none for B). With the reservation removed the test fails (verified locally).

## 2. Phone and name validation
- Allowed formatting: spaces, dashes, dots, parentheses; at most one `+`, only as the first char.
- Rule: 7 to 15 digits after stripping formatting (15 = E.164 max). `-------`, `1------`,
  `92+300...`, `++92...` and letters are 422.
- Canonical stored form: optional `+` then digits, e.g. `+92 300 0000001` -> `+923000000001`.
  Same validator for POST and PUT.
- `name` and `relationship` are trimmed before `min_length=1`, so whitespace-only is 422.
- Duplicate policy: the same user may not store two contacts with the same canonical phone
  (409 `This phone number is already saved as one of your emergency contacts`, on create and
  update). Different users may list the same number.

## 3. Member UI CRUD (frontend/app/profile/page.tsx)
- Edit existing contact (inline form, Save/Cancel), Remove with confirmation.
- Delete demographic and Delete wellness buttons with confirmation.
- Every contact input has a `<label htmlFor>`; 422 responses show field-level errors under the
  matching input (`aria-invalid`, `aria-describedby`).
- Contact list changes use functional updaters (`lib/profileState.ts`); per-action pending keys
  disable the relevant buttons while a request is in flight.
- Test: `cd frontend && npm test` (node:test over the state helpers: overlapping add/remove,
  edit replace, pending keys, 422 parsing).

## 4. Transaction and migration evidence
- `test_populated_week1_db_upgrades_and_keeps_users_and_sessions`: upgrade to Week 1 baseline,
  insert users + an admin session, upgrade to head, assert rows unchanged and new tables usable.
- `test_audit_failure_rolls_back_domain_write`: audit insert raises during PUT demographic and
  POST contact; API returns 500 and no demographic, contact or profile audit row is persisted.
- Query plans: unchanged. `ix_users_email` (unique) supports exact auth lookup; admin search
  `lower(email) LIKE '%term%'` is a scan, as documented in WEEK2_INDEXING.md.

## Loom checklist (recorded separately)
Two users with cross-owner GET/PUT/DELETE denied; admin search with pagination and a JWT denied
on that route; invalid phone rejected (e.g. `-------`); audit rows showing field names only;
populated migration test run; one real AI prompt, the refinement, and the check that caught an error.
