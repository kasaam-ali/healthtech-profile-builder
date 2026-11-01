# Week 2: Indexing and query-plan evidence

Database: SQLite (local), schema created by `alembic upgrade head` (revision `0002_week2_profiles`),
data from `python -m scripts.seed_users` (fictional users only).

## Indexes and why they exist

| Index | Table / columns | Query it serves |
|---|---|---|
| `ix_users_email` (unique) | users(email) | login, signup duplicate check, admin search by email |
| `ix_demographics_user_id` (unique) | demographics(user_id) | `GET/PUT /me/demographic` (every profile load); also enforces 1:1 |
| `ix_wellness_preferences_user_id` (unique) | wellness_preferences(user_id) | `GET/PUT /me/wellness`; enforces 1:1 |
| `ix_emergency_contacts_user_id` | emergency_contacts(user_id) | `GET /me/emergency-contacts`, ownership-scoped lookups, contact count limit |
| `ix_demographics_city` | demographics(city) | admin filter `GET /admin/profiles?city=` |
| `ix_audit_actor_created` | audit_events(actor_user_id, created_at) | "what did actor X do recently" (newest first) |
| `ix_admin_sessions_user_id` | admin_sessions(user_id) | Week 1 session lookups per admin |

Not indexed on purpose: `q` (email/name contains) uses `LIKE '%term%'`, which a B-tree index
cannot serve. At demo scale a scan is fine; at larger scale use SQLite FTS5 or Postgres trigram.

## Frequent lookup: demographic by user_id

Command:
```bash
cd backend
DATABASE_URL=sqlite:////tmp/e.db ENVIRONMENT=development alembic upgrade head
DATABASE_URL=sqlite:////tmp/e.db ENVIRONMENT=development python -m scripts.seed_users
sqlite3 /tmp/e.db "EXPLAIN QUERY PLAN SELECT * FROM demographics WHERE user_id = 1;"
```

With the index (actual output):
```
SEARCH demographics USING INDEX ix_demographics_user_id (user_id=?)
```

Same data copied into a table with no index (`CREATE TABLE demo_noidx AS SELECT * FROM demographics`):
```
SCAN demo_noidx
```

`SEARCH ... USING INDEX` is an O(log n) B-tree lookup; `SCAN` reads every row. Because each
member request loads their own profile by `user_id`, this is the hottest query in Week 2.

## Other plans captured

```
SELECT * FROM emergency_contacts WHERE user_id = 1 ORDER BY id
  SEARCH emergency_contacts USING INDEX ix_emergency_contacts_user_id (user_id=?)

SELECT * FROM users u LEFT JOIN demographics d ON d.user_id = u.id WHERE d.city = 'Lahore'
  SEARCH d USING INDEX ix_demographics_city (city=?)
  SEARCH u USING INTEGER PRIMARY KEY (rowid=?)

SELECT * FROM audit_events WHERE actor_user_id = 1 ORDER BY created_at DESC LIMIT 20
  SEARCH audit_events USING INDEX ix_audit_actor_created (actor_user_id=?)
```
The audit plan has no separate "USE TEMP B-TREE FOR ORDER BY" step: the composite index
already returns rows in created_at order for one actor.
