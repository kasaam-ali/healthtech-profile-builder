# HealthTech Profile Builder: Week 1 (Auth) + Week 2 (Relational Profiles)

Elevate Engine Full-Stack AI/ML internship, Week 1. FastAPI + SQLAlchemy + SQLite backend, Next.js (App Router) frontend.
**Fictional data only. No real patient data.** Weeks 3-4 (ML, RAG, Docker, CI) are intentionally not implemented.

## Architecture
```
Next.js (localhost:3000)  --JSON/Bearer JWT-->  FastAPI (localhost:8000)  --SQLAlchemy-->  SQLite
  /signup /login /profile                        /auth/* /me  (JWT)
                                                 /admin/*      (server-signed session cookie)
```
- `backend/app/security.py` - bcrypt hashing, JWT create/verify (HS256, `type` claim = access|refresh)
- `backend/app/deps.py` - `current_user` (Bearer JWT) and `current_admin` (session cookie + `is_admin`)
- `backend/app/main.py` - routes; `backend/scripts/` - admin + seed commands; `backend/tests/` - pytest smoke tests

## Setup & run
Backend (Python 3.11+):
```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # keeps ENVIRONMENT=development for local; set admin password
alembic upgrade head            # creates/upgrades the schema (Week 2: Alembic, no create_all)
python -m scripts.create_admin  # creates admin from ADMIN_EMAIL/ADMIN_PASSWORD (no public admin signup)
python -m scripts.seed_users    # fictional users + profile sections, password DemoPass123!
uvicorn app.main:app --reload --port 8000   # docs: http://localhost:8000/docs
```
Frontend (Node 18+):
```bash
cd frontend
cp .env.example .env.local
npm install && npm run dev      # http://localhost:3000
```
Tests:
```bash
cd backend && pytest -q
```

## Auth design (JWT vs session)
- **Users → JWT.** Stateless: server signs a token, client sends `Authorization: Bearer <token>`. Good for APIs / SPAs.
  - Access token: 15 min (`ACCESS_TOKEN_MINUTES`). Refresh token: 7 days (`REFRESH_TOKEN_DAYS`).
  - `POST /auth/refresh` exchanges a valid refresh token for a new pair. Tokens carry a `type` claim, so a refresh token is rejected on `/me`.
  - Trade-off: JWTs can't be revoked before expiry without extra state (denylist / rotation table): hence short access lifetime.
  - **Refresh-token limitation (documented, Week 1):** refresh tokens are NOT rotated or revocable: a refresh token stays reusable until its 7-day expiry (logout on the client does not kill it). Blast radius of a leaked refresh token: attacker can mint access tokens for that member until expiry or until `JWT_SECRET` is rotated (which logs everyone out). Rotation + reuse detection (jti table) is planned with the persistence work.
- **Admins → revocable server-side session.** `POST /admin/login` creates a random opaque id (`secrets.token_urlsafe(32)`) in the `admin_sessions` table (user_id, created_at, expires_at, revoked). The signed cookie carries only that id. Login rotates the id (old one revoked); `POST /admin/logout` marks the record revoked, so a copied pre-logout cookie is rejected (403). Every admin request re-checks the DB record (exists, not revoked, not expired) **and** `users.is_admin`. A user JWT is never accepted on `/admin/*`.
- **Role separation:** admin accounts are blocked from `POST /auth/login` (403 "Admin accounts must use /admin/login") and `/auth/refresh`; admins only ever hold an admin session, never a member JWT.
- **CSRF policy (cookie-authenticated mutations):** every cookie-authenticated mutating route (`/admin/login`, `/admin/logout`) requires an `Origin` header (or, if absent, a `Referer`) whose origin is listed in `CORS_ORIGINS`; missing or foreign → 403. Plus `SameSite=Lax` cookies. Member routes use Bearer headers, which browsers never attach cross-site, so they need no CSRF token. (curl examples below therefore send `-H 'Origin: http://localhost:3000'`.)
- Passwords hashed with bcrypt (salted); hashes never returned by the API. bcrypt only uses the first **72 UTF-8 bytes**, so signup and login both reject passwords over 72 bytes with a 422 ("Password must be at most 72 bytes when UTF-8 encoded"): no silent truncation. Signup ignores any `is_admin` field.

## Configuration: local vs production
| Setting | Local (`ENVIRONMENT=development`) | Production (`ENVIRONMENT=production`, the default) |
|---|---|---|
| `JWT_SECRET` / `SESSION_SECRET` | may be omitted → explicit, publicly known dev-only defaults | **required**, ≥32 chars, not a known default/placeholder, must differ: otherwise the app **refuses to start** (`InsecureConfigError`) |
| Session cookie `Secure` (`https_only`) | off (http://localhost) | on (HTTPS only) |
| `CORS_ORIGINS` | `http://localhost:3000` | your real frontend origin(s); also the CSRF trusted-Origin list |

If `ENVIRONMENT` is unset the app assumes production and fails closed. Generate secrets with `python -c "import secrets; print(secrets.token_urlsafe(48))"`.

## Sample requests
```bash
curl -X POST localhost:8000/auth/signup -H 'content-type: application/json' \
  -d '{"email":"sara.demo@example.com","full_name":"Sara Demo","password":"DemoPass123!"}'
curl -X POST localhost:8000/auth/login -H 'content-type: application/json' \
  -d '{"email":"sara.demo@example.com","password":"DemoPass123!"}'      # -> access_token, refresh_token
curl localhost:8000/me -H "Authorization: Bearer <access_token>"         # 200; without header -> 401
curl -X POST localhost:8000/auth/refresh -H 'content-type: application/json' -d '{"refresh_token":"<refresh_token>"}'
curl -c jar -X POST localhost:8000/admin/login -H 'content-type: application/json' -H 'Origin: http://localhost:3000' \
  -d '{"email":"admin@example.com","password":"<ADMIN_PASSWORD>"}'
curl -b jar localhost:8000/admin/users                                   # 200 with admin session; else 403
```

## Week 1 acceptance checklist
- [x] Unauthenticated request fails (`/me` → 401, `/admin/users` → 403): tested
- [x] Ordinary user cannot access admin routes (user JWT → 403; user creds on `/admin/login` → 401): tested
- [x] Passwords hashed (bcrypt `$2b$…`): tested
- [x] Secrets only in `.env` (gitignored); only `.env.example` committed
- [x] Admin created via script, no public admin signup
- [x] JWT expiry + refresh documented above; refresh token can't be used as access: tested
- [x] Fictional seed data only
- [ ] Feature branch + PR with reviewer `@ahmedhashir10`
- [ ] 5-10 min Loom (demo, real AI prompts used, challenges, blast radius) + links posted in team Slack

## Limitations (Week 1 scope)
- Frontend stores the access token in `sessionStorage` (XSS-exposed); production should use httpOnly cookies. Frontend does not auto-refresh tokens yet.
- No refresh-token rotation/revocation (reusable until expiry: see above), no rate limiting on login. CSRF is handled by trusted-Origin checks rather than a token. Cookie `Secure` only in production.
- SQLite + `create_all` instead of migrations (Alembic later). No admin UI: admin is API-only.

## Week 2: Relational profiles, authorization, API quality

Docs: [schema diagram](docs/WEEK2_SCHEMA.md), [indexing + EXPLAIN evidence](docs/WEEK2_INDEXING.md).
Code: `backend/app/profiles.py` (routes), `backend/app/audit.py` (audit helper), `backend/alembic/` (migrations).

### Tables (Alembic `0001_week1_baseline` then `0002_week2_profiles`)
- `demographics` (1:1, unique `user_id`): date_of_birth, gender, city, country
- `wellness_preferences` (1:1, unique `user_id`): activity_level (low|moderate|high), diet_notes, reminder_opt_in
- `emergency_contacts` (1:N, max 5 per user): name, phone, relationship
- `audit_events`: actor_user_id, action, resource_type, resource_id, metadata_json, created_at

### Endpoints
Member (Bearer JWT; always scoped to the token's user, body never carries `user_id`):
| Method | Path | Notes |
|---|---|---|
| GET / PUT / DELETE | `/me/demographic` | PUT is an upsert; 404 if none yet |
| GET / PUT / DELETE | `/me/wellness` | PUT is an upsert |
| GET / POST | `/me/emergency-contacts` | POST 409 after 5 contacts |
| GET / PUT / DELETE | `/me/emergency-contacts/{id}` | another user's id returns 404 (no existence leak) |

Admin (server-side session cookie only; a user JWT gets 403):
| Method | Path | Notes |
|---|---|---|
| GET | `/admin/profiles?q=&city=&page=1&page_size=20` | `q` = email/name contains (case-insensitive), `city` = exact; `page_size` max 100; returns `{items,total,page,page_size}` |

Authorization rules:
- Object-level ownership is inside the SQL (`WHERE id = :id AND user_id = :current_user`), so IDOR attempts look like a missing row (404).
- Request bodies use `extra="forbid"`: sending `user_id` (or any unknown field) is a 422, not silently trusted.
- Malformed input (bad date, future DOB, unknown activity level, invalid phone, empty name) is a 422.

Audit trail: profile create/update/delete and admin list access write an `audit_events` row. Metadata holds only changed
field names or filter keys plus page/result count, never values, passwords, or tokens.

### Migrate, seed, run
```bash
cd backend
pip install -r requirements.txt
alembic upgrade head                 # clean DB or upgrade
python -m scripts.seed_users         # fictional profiles for ayesha/bilal demo users
uvicorn app.main:app --reload --port 8000
# new migration after model changes:
alembic revision --autogenerate -m "describe change" && alembic upgrade head
```
Existing Week 1 `healthtech.db` (made by `create_all`, no `alembic_version`): either delete it and run `alembic upgrade head`,
or run `alembic stamp 0001_week1_baseline && alembic upgrade head`.

### Tests
```bash
cd backend && pytest -q    # Week 1 + Week 2, includes alembic upgrade/check/downgrade on a temp DB
```
Week 2 tests (`tests/test_week2_profiles.py`, `tests/test_migrations.py`): happy-path CRUD, IDOR (User A cannot read/edit/delete
User B), admin session vs member JWT separation, malformed input 422, contact limit, admin pagination + filters, audit rows without PII.

### Indexing note
Indexes on every `user_id` FK (unique for 1:1 sections), `demographics.city` (admin filter), `users.email`, and
`audit_events(actor_user_id, created_at)`. `EXPLAIN QUERY PLAN` for the hottest lookup (demographic by user_id) shows
`SEARCH demographics USING INDEX ix_demographics_user_id` versus `SCAN` without it. Details in [docs/WEEK2_INDEXING.md](docs/WEEK2_INDEXING.md).

### Frontend
`/profile` now shows editable forms for demographic, wellness, and emergency contacts (fictional data only).

### Week 2 checklist
- [x] Ownership-linked tables + migrations + justified indexes + EXPLAIN evidence
- [x] User-owned CRUD, IDOR tests, admin-only paginated search, audit trail
- [x] Schema diagram, API docs (this section + `/docs` OpenAPI)
- [ ] PR with reviewer `@ahmedhashir10` + Loom

## Week 3: Educational ML and FAQ (synthetic data only)

> Fictional educational demo. Not medical advice, diagnosis, triage, or treatment. Every predict and FAQ response carries this disclaimer.

**Train / recreate artifacts** (from `backend/`, venv active):
```bash
pip install -r requirements.txt
python -m scripts.train_ml
```
Writes `ml/data/wellness_engagement.csv`, `ml/artifacts/engagement_model.joblib` (version `engagement-v1.1.0`), `metrics.json`, `clusters.json`, `pca_clusters.png`.

**Model selection and results** (seed 42, 1500 train / 500 test rows): the model is chosen by 5-fold stratified CV F1 on the training split only, then scored once on the held-out test split.
- CV F1: Logistic Regression 0.7491 +/- 0.0194, Random Forest 0.7323 +/- 0.0234, always-engaged baseline 0.6673. Chosen: Logistic Regression.
- Final test (not used for selection): Logistic Regression F1 0.7254, accuracy 0.732; always-engaged prevalence baseline F1 0.6667, accuracy 0.500.
- K-Means k=3 silhouette 0.2823 (modest separation, exploratory only). Details in `docs/WEEK3_MODEL_COMPARISON.md`.

**Endpoints**
- `POST /api/v1/predict` body: `{"age":34,"sessions_last_30d":8,"avg_session_minutes":15,"days_since_signup":200,"reminders_opt_in":true,"preferred_channel":"app"}`. Out of range, wrong type, unknown fields: 422. Returns prediction, probability, model_version, disclaimer.
- `GET /api/v1/model`: metrics and comparison.
- `GET /api/v1/clusters`: K-Means summary and silhouette.
- `POST /api/v1/faq` body `{"question":"..."}`: answer with sources, or safe abstention.

**Frontend:** `/ml` (comparison, predict form, clusters) and `/faq`.

Docs: `docs/WEEK3_DATASET.md`, `docs/WEEK3_MODEL_COMPARISON.md`, `docs/WEEK3_CLUSTERING.md`, `docs/WEEK3_FAQ_EVAL.md`.
