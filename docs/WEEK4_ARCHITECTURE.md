# Week 4 architecture

```mermaid
flowchart LR
  U[Browser: Next.js 14] -->|JWT Bearer| API[FastAPI app]
  subgraph API
    AUTH[/auth/* JWT, /admin/* session/]
    PROF[/me/* profile CRUD/]
    ML[/api/v1/predict, /clusters/]
    FAQ1[/api/v1/faq keyword, legacy/]
    RAG[/api/v2/faq RAG with citations/]
    TOOLS[/api/v2/tools/*/]
  end
  RAG --> GUARD[Injection and medical guards]
  GUARD --> RET[TF-IDF retriever]
  TOOLS -->|search_approved_documents| RET
  RET --> DOCS[(clinic_docs/*.md fictional)]
  TOOLS -->|check_appointment_availability| SCHED[(schedule.json fictional)]
  TOOLS -->|request_appointment_hold: JWT + human_confirmed| DB[(SQLite via SQLAlchemy + Alembic)]
  PROF --> DB
  AUTH --> DB
  ML --> ART[(ml/artifacts joblib, json)]
  RAG --> AUD[audit_events]
  TOOLS --> AUD
  AUD --> DB
```

## Request flow for a write tool

```mermaid
sequenceDiagram
  participant UI
  participant API
  participant DB
  UI->>API: POST /api/v2/tools/request_appointment_hold {slot_id, human_confirmed}
  API->>API: verify JWT (401 if missing or invalid)
  alt human_confirmed is false
    API->>DB: audit tool.denied (no_human_confirmation)
    API-->>UI: 400
  else slot not open, already held, or 2 active holds
    API->>DB: audit tool.denied
    API-->>UI: 409
  else provider timeout
    API->>DB: rollback hold, audit tool.failed
    API-->>UI: 503 "No hold was created"
  else ok
    API->>DB: insert hold + audit tool.approved_write (one transaction)
    API-->>UI: 201
  end
```

## Logging

Every RAG answer and tool call writes an `audit_events` row with `resource_type="tool"` and action `rag.answer`, `tool.call`, `tool.denied`, `tool.approved_write` or `tool.failed`. Metadata holds retrieval refs (chunk ids), setting, abstain reason, counts and error class names. It never holds question text, tokens or passwords (`app/audit.py` also strips forbidden keys).

## Migration note

`POST /api/v1/faq` (Week 3 keyword FAQ) is kept unchanged so Week 3 clients and tests keep working. New clients use `POST /api/v2/faq`, which returns `citations` (doc_id, title, chunk_id, score) and `reason` on abstain. The Week 4 UI page `/assistant` uses v2.
