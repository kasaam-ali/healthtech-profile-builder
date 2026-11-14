# Week 4 deploy and local runbook

Fictional demo. No real patient data. No API keys or network needed.

## Option A: local (Python 3.13, Node 20)

```
# backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env            # ENVIRONMENT=development for local
python -m alembic upgrade head  # creates tables incl. appointment_holds
python -m scripts.train_ml      # optional: artifacts are committed
python -m scripts.create_admin  # optional: admin for /admin/*
uvicorn app.main:app --reload --port 8000

# frontend (second terminal)
cd frontend
npm ci
NEXT_PUBLIC_API_URL=http://localhost:8000 npm run dev
```

Open http://localhost:3000. End-to-end demo path: Sign up, Log in, My profile (fill demographics and a contact), ML demo (predict, clusters), Assistant (ask "How long does a hold last?", check availability, tick the confirmation box, request a hold).

## Option B: Docker Compose

```
cp backend/.env.example backend/.env
docker compose up --build
```

Backend on :8000 (runs `alembic upgrade head` at start, SQLite in a named volume), frontend on :3000. Note: the compose file was written and YAML-validated, but not run on the build box (no Docker there).

## Checks (same as CI, `.github/workflows/ci.yml`)

```
cd backend && ruff check --select E9,F app ml scripts tests && python -m pytest -q && python -m scripts.eval_rag
cd frontend && npm run lint && npm test && npm run build
```

## API quick reference (Week 4)

| method | path | auth | notes |
|---|---|---|---|
| POST | /api/v2/faq | none | `{question, setting?: baseline or tuned}` returns answer, citations, abstained, reason |
| POST | /api/v2/tools/search_approved_documents | none | `{query, top_k 1-5}` read only |
| POST | /api/v2/tools/check_appointment_availability | none | `{date?: YYYY-MM-DD, coach?}` read only, excludes held slots |
| POST | /api/v2/tools/request_appointment_hold | member JWT | `{slot_id, human_confirmed: true}` mock write; 400 without confirmation |
| GET | /api/v2/tools/my_holds | member JWT | own holds only |

## Troubleshooting

- 503 from /api/v2/*: retrieval or calendar provider failure. Nothing was written; retry.
- 503 from /api/v1/predict, /api/v1/model, /api/v1/clusters or /api/v1/clusters/plot: a model or report artifact in `backend/ml/artifacts/` is missing or invalid (details in the server log only). Run `python -m scripts.train_ml` or restore the files; the next request recovers without a restart.
- App refuses to start: production mode needs strong JWT_SECRET and SESSION_SECRET; set ENVIRONMENT=development locally.
- `alembic check` fails: models and migrations drifted; add a new revision.
