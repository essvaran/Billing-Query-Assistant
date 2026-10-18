# Diagrams

Both diagrams are checked in as source, so they can be edited and re-rendered. GitHub and VS Code render the Mermaid blocks below.

| File | What it is |
|---|---|
| `architecture.svg` | The architecture diagram as a standalone picture (open it in a browser or paste it into a slide) |
| `architecture.mmd` | The same diagram as Mermaid source |
| `entity_diagram.mmd` | The database entity diagram (all 10 tables in `data/tier1.db`, defined in `tier1/db.py`) |

The entity diagram was checked against the real SQLite schema: every table and column name matches.
Notes: `tickets` carries the eval ground truth (`kind`, `expected_*`, `gold_slug`), which the API never returns to the UI.
`spans.trace_id` joins `ai_results` and `jobs` by value, not by a declared foreign key, because spans are also written by the MCP server processes.
`handoffs.ticket_ref` can also hold a non-ticket reference, so it has no foreign key either.

## Architecture

```mermaid
flowchart TD
  UI["Angular workspace<br/>queue, review, insights"] --> API["FastAPI router<br/>thin, no logic"]
  CLI["CLI and eval suite<br/>python -m tier1"] --> SVC
  API --> SVC

  subgraph SVC["Single entry point: handle_ticket()"]
    direction LR
    PRE["Pre-guard<br/>no model call"] --> AGENT["Agent loop<br/>budgeted, 3 tools"] --> POST["Post-guard<br/>citations, windows"]
  end

  AGENT --> GW["LLM gateway<br/>cache, token limiter"]
  AGENT --> TOOLS["MCP: tier1-tools<br/>order, plan, handoff"]
  AGENT --> HELP["MCP: help-centre<br/>hybrid search"]

  GW --> GROQ["Groq model API<br/>free tier"]
  TOOLS --> DB[("SQLite tier1.db<br/>orders, spans, queue")]
  HELP --> IDX[("Vector index<br/>Chroma plus BM25")]

  TRACE["Tracing and PII redaction on every hop"]:::cross
  SVC -.-> TRACE
  TOOLS -.-> TRACE
  HELP -.-> TRACE

  classDef cross fill:none,stroke:#888,stroke-dasharray:5 4
```

## Entity diagram

```mermaid
erDiagram
  CUSTOMERS ||--o{ ORDERS : places
  CUSTOMERS ||--o{ TICKETS : sends
  ORDERS ||--o{ TICKETS : "is about"
  TICKETS ||--o{ AI_RESULTS : "gets drafts"
  TICKETS ||--o{ DECISIONS : "gets human decisions"
  TICKETS ||--o{ TICKET_FEEDBACK : "gets reports"
  TICKETS ||--o{ HANDOFFS : "may escalate to"
  AI_RESULTS }o--o{ SPANS : "same trace_id"
  JOBS }o--o{ SPANS : "same trace_id"
  SPANS ||--o{ SPANS : "parent_id"
```

The full column list for each table is in `entity_diagram.mmd`.
