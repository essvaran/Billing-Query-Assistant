# Billing Support RAG

A production-ready Retrieval-Augmented Generation (RAG) system for answering billing questions and resolving support tickets. Supports both a conversational RAG chat interface and an agentic ReAct loop that resolves tickets by calling structured tools via the Model Context Protocol (MCP).

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Architecture](#2-architecture)
3. [Folder Structure](#3-folder-structure)
4. [Prerequisites](#4-prerequisites)
5. [Setup](#5-setup)
6. [Environment Variables](#6-environment-variables)
7. [Building the Knowledge Base](#7-building-the-knowledge-base)
8. [Running the Application](#8-running-the-application)
9. [Authentication](#9-authentication)
10. [Chat Modes](#10-chat-modes)
11. [Admin Panel](#11-admin-panel)
12. [Supported File Formats](#12-supported-file-formats)
13. [Chunking Strategies](#13-chunking-strategies)
14. [Evaluation](#14-evaluation)
15. [Running Tests](#15-running-tests)
16. [CLI Usage](#16-cli-usage)

---

## 1. Project Overview

This system answers billing questions and resolves support tickets by:

- **Ingesting** help-centre articles (PDF, Markdown, Word, Excel, plain text) into three local vector store collections
- **Retrieving** relevant chunks via hybrid search (BM25 + dense vector, fused by Reciprocal Rank Fusion)
- **Generating** grounded, cited answers via a cloud (Groq) or local (Ollama) LLM
- **Refusing** questions the indexed articles cannot answer
- **Resolving tickets** with a ReAct agent that calls billing tools via MCP servers
- **Tracking** every trace with Langfuse observability (optional)

---

## 2. Architecture

```
Browser
    |
    v
Angular 19 UI  (port 4200)
    |  /api/* proxy
    v
FastAPI server  (port 8000)
    |
    |-- Google OAuth + JWT auth
    |
    |-- RAG pipeline
    |       |-- Local vector store (chroma_db/ -- numpy + JSON on disk)
    |       |       -- billing_structure_aware (default)
    |       |       -- billing_baseline
    |       |       -- billing_semantic
    |       |
    |       -- LLM (Groq cloud OR local Ollama)
    |
    |-- Agent (ReAct loop)
    |       |-- MCP client
    |               -- billing-tools MCP server
    |                       -- get_ticket
    |                       -- get_order
    |                       -- get_customer_tier
    |                       -- search_knowledge_base
    |
    -- SQLite (data/app.db)
            -- users, tickets, orders, customers, jobs
```

**Tech stack**

| Layer | Technology |
|---|---|
| Embeddings | `BAAI/bge-base-en-v1.5` via `sentence-transformers` |
| Vector store | Local numpy store (persistent JSON + .npy files) |
| Keyword search | BM25 (`rank-bm25`) |
| Fusion | Reciprocal Rank Fusion (RRF, k=60) |
| LLM (RAG) | Groq `llama-3.1-8b-instant` or Ollama |
| LLM (Agent) | Groq `llama-3.3-70b-versatile` or Ollama |
| Tool protocol | Model Context Protocol (MCP) over stdio |
| API | FastAPI + Uvicorn |
| Auth | Google OAuth 2.0 + JWT |
| Rate limiting | slowapi (10 req/min on /api/ask) |
| Observability | Langfuse (optional) |
| Database | SQLite |
| UI | Angular 19 |

---

## 3. Folder Structure

```
rag-billing-support/
|
|-- api/                        FastAPI backend
|   |-- main.py                 App entrypoint, CORS, rate limiting, /api/ask
|   |-- auth.py                 Google OAuth token verification + JWT issuance
|   |-- config.py               Environment-based configuration
|   |-- database.py             SQLite schema + seed data
|   |-- models.py               Pydantic request/response models
|   |-- admin_router.py         Admin CRUD: tickets, orders, customers, users
|   |-- agent_router.py         Agent job queue (SQLite-backed, daemon threads)
|   |-- race_router.py          Agent-vs-workflow race endpoint
|   `-- trajectory_router.py    Trajectory evaluation endpoints
|
|-- agent/                      ReAct agentic loop
|   |-- agent_loop.py           Main loop: budgets, MCP dispatch, Langfuse tracing
|   |-- tools.py                Tool implementations (get_ticket, get_order, etc.)
|   |-- tickets.py              Fixture data: 13 tickets, orders, customers
|   |-- mcp_client.py           MCP stdio client manager
|   |-- workflow.py             Deterministic workflow (for race comparison)
|   |-- trajectory_eval.py      Trajectory evaluation logic
|   |-- mitigations.py          Prompt hardening + argument validation
|   `-- injection_test.py       Prompt injection test cases
|
|-- mcp_servers/
|   `-- billing_tools_server.py MCP server: get_ticket, get_order, get_customer_tier, search_knowledge_base
|
|-- src/                        Core RAG library
|   |-- config.py               Paths, model names, score thresholds
|   |-- chunking/               baseline, structure_aware, semantic chunkers
|   |-- ingestion/              File loaders (PDF, DOCX, Excel, MD, TXT)
|   |-- retrieval/              Dense search, BM25, hybrid RRF, query filter
|   `-- generation/             LLM client, prompts, citations, refusal, Langfuse
|
|-- frontend/                   Angular 19 SPA
|   |-- src/app/
|   |   |-- app.routes.ts       Routes (/ for users; admin routes for admins)
|   |   |-- components/
|   |   |   |-- login/          Google OAuth sign-in
|   |   |   |-- chat/           RAG + Agent chat (unified)
|   |   |   |-- admin/          Admin CRUD panel (admin only)
|   |   |   |-- traces/         Trace browser (admin only)
|   |   |   |-- eval/           Eval dashboard (admin only)
|   |   |   |-- race/           Agent vs Workflow race (admin only)
|   |   |   `-- trajectory/     Trajectory eval + security (admin only)
|   |   |-- services/           HTTP service wrappers
|   |   |-- guards/             auth.guard.ts, admin.guard.ts
|   |   `-- interceptors/       auth.interceptor.ts (attaches JWT)
|   `-- proxy.conf.json         Dev proxy: /api -> localhost:8000
|
|-- data/
|   |-- billing_articles/       Source PDFs (6 billing help articles -- add more here)
|   |-- markdown/               Markdown versions of articles
|   `-- app.db                  SQLite database
|
|-- evaluation/                 Eval artifacts
|   |-- traces.jsonl            All RAG traces (append-only log)
|   |-- golden_set.jsonl        25-question golden eval set
|   |-- labels_25.json          Human labels for 25 cases
|   `-- judge.py                LLM-as-judge runner
|
|-- scripts/                    Utility scripts
|   |-- bootstrap.py            Build ChromaDB collections from scratch
|   |-- ingest_articles.py      Ingest all billing articles
|   |-- ask.py                  CLI ask utility
|   `-- run_evaluation.py       Run evaluation pipeline
|
|-- tests/                      pytest test suite
|-- docs/                       Internal project notes and weekly writeups
|-- mcp_config.json             MCP server process configuration
|-- .env                        Local secrets (gitignored)
|-- .env.example                Template -- copy to .env and fill in
`-- requirements.txt            Python dependencies
```

---

## 4. Prerequisites

| Tool | Version | Notes |
|---|---|---|
| Python | 3.11+ | |
| Node.js | 18+ | For the Angular UI |
| npm | 9+ | Comes with Node |
| Google Cloud account | -- | For OAuth credentials |

---

## 5. Setup

### 1. Clone and create a virtual environment

```powershell
git clone <repo-url>
cd rag-billing-support

python -m venv .venv
.venv\Scripts\Activate.ps1      # PowerShell
# or
.venv\Scripts\activate.bat      # cmd.exe
```

### 2. Install Python dependencies

```powershell
pip install -r requirements.txt
```

> **First run note:** ingestion downloads the `BAAI/bge-base-en-v1.5` embedding model (~440 MB) from Hugging Face and caches it locally.

### 3. Configure environment variables

```powershell
copy .env.example .env
```

Open `.env` and fill in all values. See [Section 6](#6-environment-variables) for details.

### 4. Install Angular dependencies

```powershell
cd frontend
npm install
cd ..
```

---

## 6. Environment Variables

All required variables must be set in `.env`. The server exits with a clear error message if any required variable is missing.

```env
# ── LLM Provider ──────────────────────────────────────────────────────────────
LLM_PROVIDER=groq                         # "groq" or "ollama"

# ── Groq (cloud, recommended) ─────────────────────────────────────────────────
# Get a free key at https://console.groq.com -> API Keys
GROQ_API_KEY=gsk_your_key_here
LLM_MODEL=llama-3.1-8b-instant            # RAG model; agent uses llama-3.3-70b-versatile

# ── Ollama (local, optional) ──────────────────────────────────────────────────
# OLLAMA_BASE_URL=http://localhost:11434
# LLM_MODEL=llama3.2:latest

# ── Auth -- required ──────────────────────────────────────────────────────────
# Google OAuth client ID (web application)
# console.cloud.google.com > APIs & Services > Credentials > Create OAuth 2.0 Client ID
# Add http://localhost:4200 to Authorized JavaScript origins
GOOGLE_CLIENT_ID=your_client_id.apps.googleusercontent.com

# JWT signing secret -- generate with: python -c "import secrets; print(secrets.token_hex(32))"
JWT_SECRET=change_me_to_a_random_secret_at_least_32_chars

# Email address that receives admin role on first login (required -- no default)
ADMIN_EMAIL=your_admin_email@example.com

# ── CORS ──────────────────────────────────────────────────────────────────────
# Comma-separated list of allowed origins (default: http://localhost:4200)
# ALLOWED_ORIGINS=http://localhost:4200,https://your-production-domain.com

# ── Langfuse observability (optional) ─────────────────────────────────────────
# Leave blank to disable. Get keys at https://cloud.langfuse.com
# LANGFUSE_PUBLIC_KEY=pk-...
# LANGFUSE_SECRET_KEY=sk-...
# LANGFUSE_HOST=https://cloud.langfuse.com

# ── Upload limits ─────────────────────────────────────────────────────────────
# MAX_UPLOAD_BYTES=20971520    # 20 MB (default)
```

---

## 7. Building the Knowledge Base

Run once before starting the application (and again whenever you add new articles).

```powershell
python scripts\bootstrap.py
python scripts\ingest_articles.py
```

This reads all PDFs from `data/billing_articles/`, chunks them with three strategies, embeds them with `BAAI/bge-base-en-v1.5`, and writes three collections to `chroma_db/` (stored as JSON + .npy files, no C++ dependencies).

```
Loaded articles: 6
Structure-aware chunk count: 87
Built collection: billing_structure_aware  (default)
Built collection: billing_baseline
Built collection: billing_semantic
```

> Re-run after adding or removing articles from `data/billing_articles/`.

---

## 8. Running the Application

Open two terminals with the virtual environment active.

### Terminal 1 -- FastAPI backend

```powershell
.venv\Scripts\python.exe -m uvicorn api.main:app --port 8000
```

The API runs at `http://127.0.0.1:8000`. Interactive docs: `http://127.0.0.1:8000/api/docs`

### Terminal 2 -- Angular UI

```powershell
cd frontend
npx ng serve --port 4200 --proxy-config proxy.conf.json
```

Open `http://localhost:4200` in your browser.

---

## 9. Authentication

The app uses Google OAuth 2.0 for sign-in. On first login, the account matching `ADMIN_EMAIL` is granted the `admin` role; all other accounts receive the `user` role.

**To set up Google OAuth:**

1. Go to [console.cloud.google.com](https://console.cloud.google.com) > APIs & Services > Credentials
2. Create an **OAuth 2.0 Client ID** (Web application)
3. Add `http://localhost:4200` to **Authorized JavaScript origins**
4. Copy the Client ID into `.env` as `GOOGLE_CLIENT_ID`
5. Also paste the same Client ID into `frontend/src/app/components/login/login.component.ts`

JWTs expire after 7 days. The Angular auth interceptor attaches the token automatically on every request.

---

## 10. Chat Modes

The chat interface has two modes, selectable from the input bar:

### RAG mode (default)

Answers billing questions by retrieving relevant chunks from the knowledge base and generating a cited response. Uses hybrid retrieval (BM25 + dense vector, fused by RRF).

- If no relevant chunks are found, the system returns a friendly fallback rather than hallucinating.
- Sources can be expanded below each answer (article name + section heading + excerpt).

### Agent mode

Resolves support tickets using a ReAct loop. The agent calls billing tools in sequence until it has enough information to reach a verdict (approve / deny / escalate).

**Tools available:**
- `get_ticket` -- retrieves the ticket text, customer ID, and order ID
- `get_order` -- fetches purchase date, amount, and fulfilment status
- `get_customer_tier` -- returns the customer's tier and refund window
- `search_knowledge_base` -- runs a RAG search over the billing articles

The agent shows a summary of which steps it took and its final answer.

---

## 11. Admin Panel

Accessible at `/admin` for accounts with the `admin` role.

**Tabs:**

| Tab | Description |
|---|---|
| Tickets | CRUD for support tickets (ticket ID, customer, order, text, expected verdict) |
| Orders | CRUD for orders (order ID, purchase date, amount, status) |
| Customers | CRUD for customers (customer ID, tier, refund window in days) |
| Documents | Upload new articles (PDF, MD, TXT, DOCX, XLSX -- max 20 MB) to add to the knowledge base |
| Users | View all users and change roles (admin cannot demote the primary admin) |

**Admin-only routes** (also guarded by the admin role):

| Route | Description |
|---|---|
| `/traces` | Browse all RAG traces with filters |
| `/sample` | Curated sample traces |
| `/replay/:id` | Re-run LLM with original trace's chunks |
| `/taxonomy` | Query taxonomy explorer |
| `/eval` | Eval dashboard (25-question golden set) |
| `/race` | Agent vs Workflow comparison |
| `/trajectory` | Trajectory eval, mitigation analysis, and prompt injection tests |

---

## 12. Supported File Formats

Drop any supported file into `data/billing_articles/` and re-run `ingest_articles.py`. Files can also be uploaded through the Admin panel without restarting the server.

| Format | Extension |
|---|---|
| Plain text | `.txt` |
| Markdown | `.md` |
| Word | `.docx` |
| PDF | `.pdf` |
| Excel (modern) | `.xlsx` |
| Excel (legacy) | `.xls` |

For `.md` and `.txt` files, add YAML front matter to control indexing metadata:

```markdown
---
article_id: HC-BILL-007
product_area: billing-migration
last_updated: 2026-01-15
---

# Article Title

Content here...
```

---

## 13. Chunking Strategies

Three strategies are built. The default is **structure-aware**.

| Strategy | Collection | How it works |
|---|---|---|
| **Structure-aware** | `billing_structure_aware` | Splits on `##` section headings; parses Markdown tables into one chunk per row |
| **Baseline** | `billing_baseline` | RecursiveCharacterTextSplitter (800 chars / 100 overlap) |
| **Semantic** | `billing_semantic` | Splits where cosine distance between sentence windows spikes |

---

## 14. Evaluation

### RAG evaluation (25-question golden set)

```powershell
python evaluation\run_eval.py
```

Runs 4 deterministic assertions and an LLM-as-judge across 25 labelled questions. Results are written to `evaluation/`.

### Agent trajectory evaluation

Access `/trajectory` (admin only) in the UI to run trajectory evaluation, apply mitigations, and test prompt injection defence.

### Langfuse traces

Every RAG call and agent run is traced in Langfuse when `LANGFUSE_PUBLIC_KEY` is set. Traces are also written locally to `evaluation/traces.jsonl` regardless of Langfuse availability.

---

## 15. Running Tests

```powershell
pytest
```

The test suite covers:

- Article loading and metadata validation
- Chunking (baseline, structure-aware)
- Bootstrap script
- API endpoints (auth, ask, upload, admin, agent)

---

## 16. CLI Usage

Ask a billing question directly from the terminal without the UI:

```powershell
python scripts\ask.py
```

```
> What does ERR-4032 mean?

According to [HC-BILL-002--error-codes--err-4032], ERR-4032 means the billing
profile migration is incomplete because a required field was not carried over
from the legacy platform.
```
