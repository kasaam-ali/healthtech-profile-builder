# HealthTech Profile Builder — Week 1 (Auth Foundation)

Elevate Engine Full-Stack AI/ML internship, Week 1. FastAPI + SQLAlchemy + SQLite backend, Next.js (App Router) frontend.
**Fictional data only. No real patient data.** Weeks 2–4 (ML, RAG, Docker, CI) are intentionally not implemented.

## Architecture
```
Next.js (localhost:3000)  --JSON/Bearer JWT-->  FastAPI (localhost:8000)  --SQLAlchemy-->  SQLite
  /signup /login /profile                        /auth/* /me  (JWT)
                                                 /admin/*      (server-signed session cookie)
```
- `backend/app/security.py` – bcrypt hashing, JWT create/verify (HS256, `type` claim = access|refresh)
- `backend/app/deps.py` – `current_user` (Bearer JWT) and `current_admin` (session cookie + `is_admin`)
- `backend/app/main.py` – routes; `backend/scripts/` – admin + seed commands; `backend/tests/` – pytest smoke tests

## Setup & run
Backend (Python 3.11+):
```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # then put real random secrets + admin password in .env
python -m scripts.create_admin  # creates admin from ADMIN_EMAIL/ADMIN_PASSWORD (no public admin signup)
python -m scripts.seed_users    # fictional users, password DemoPass123!
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
  - Trade-off: JWTs can't be revoked before expiry without extra state (denylist / rotation table) — hence short access lifetime.
- **Admins → server session.** `POST /admin/login` sets a signed, httpOnly session cookie (Starlette `SessionMiddleware`). Logout clears it immediately. A user JWT is never accepted on `/admin/*`.
- Passwords hashed with bcrypt (salted); hashes never returned by the API. Pydantic validates all input (email format, password 8–72 chars). Signup ignores any `is_admin` field.

## Sample requests
```bash
curl -X POST localhost:8000/auth/signup -H 'content-type: application/json' \
  -d '{"email":"sara.demo@example.com","full_name":"Sara Demo","password":"DemoPass123!"}'
curl -X POST localhost:8000/auth/login -H 'content-type: application/json' \
  -d '{"email":"sara.demo@example.com","password":"DemoPass123!"}'      # -> access_token, refresh_token
curl localhost:8000/me -H "Authorization: Bearer <access_token>"         # 200; without header -> 401
curl -X POST localhost:8000/auth/refresh -H 'content-type: application/json' -d '{"refresh_token":"<refresh_token>"}'
curl -c jar -X POST localhost:8000/admin/login -H 'content-type: application/json' \
  -d '{"email":"admin@example.com","password":"<ADMIN_PASSWORD>"}'
curl -b jar localhost:8000/admin/users                                   # 200 with admin session; else 403
```

## Week 1 acceptance checklist
- [x] Unauthenticated request fails (`/me` → 401, `/admin/users` → 403) — tested
- [x] Ordinary user cannot access admin routes (user JWT → 403; user creds on `/admin/login` → 401) — tested
- [x] Passwords hashed (bcrypt `$2b$…`) — tested
- [x] Secrets only in `.env` (gitignored); only `.env.example` committed
- [x] Admin created via script, no public admin signup
- [x] JWT expiry + refresh documented above; refresh token can't be used as access — tested
- [x] Fictional seed data only
- [ ] Feature branch + PR with reviewer `@ahmedhashir10`
- [ ] 5–10 min Loom (demo, real AI prompts used, challenges, blast radius) + links posted in team Slack

## Limitations (Week 1 scope)
- Frontend stores the access token in `sessionStorage` (XSS-exposed); production should use httpOnly cookies. Frontend does not auto-refresh tokens yet.
- No refresh-token rotation/revocation, no rate limiting on login, no CSRF token for admin session (SameSite=Lax mitigates), cookie not `Secure` (local HTTP).
- SQLite + `create_all` instead of migrations (Alembic later). No admin UI — admin is API-only.
