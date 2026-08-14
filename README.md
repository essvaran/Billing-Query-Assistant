# Billing Support RAG

A Retrieval-Augmented Generation (RAG) system for answering billing migration questions. Ingests help-centre articles in multiple formats, indexes them with three chunking strategies, and serves grounded answers through a FastAPI backend and Angular chat UI.

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Architecture](#2-architecture)
3. [Folder Structure](#3-folder-structure)
4. [Prerequisites](#4-prerequisites)
5. [Setup](#5-setup)
6. [API Keys and LLM Models](#6-api-keys-and-llm-models)
7. [Running the Pipeline](#7-running-the-pipeline)
8. [Running the Application](#8-running-the-application)
9. [Sharing via ngrok](#9-sharing-via-ngrok)
10. [CLI Usage](#10-cli-usage)
11. [Supported File Formats](#11-supported-file-formats)
12. [Chunking Strategies](#12-chunking-strategies)
13. [Evaluation](#13-evaluation)
14. [Running Tests](#14-running-tests)

---

## 1. Project Overview

This system answers questions about billing migrations by:

- **Ingesting** help-centre articles (PDF, Word, Excel, Markdown, plain text)
- **Chunking** them with three strategies and embedding with `BAAI/bge-base-en-v1.5`
- **Storing** embeddings in ChromaDB (local, no server needed)
- **Retrieving** the most relevant chunks at query time
- **Generating** grounded, cited answers via a cloud or local LLM
- **Refusing** questions the indexed articles cannot answer

The default chunking strategy is **structure-aware**, which achieves 8/8 Hit@5 on the evaluation set including all table-dependent questions.

---

## 2. Architecture

```
Browser / ngrok
      │
      ▼
Angular UI  (port 4200)
      │  /api/* proxy
      ▼
FastAPI server  (port 8000)
      │
      ├── ChromaDB  (chroma_db/ — local disk)
      │       └── billing_structure_aware collection (default)
      │
      └── LLM  (Groq cloud  OR  local Ollama)
```

**Tech stack**

| Layer | Technology |
|---|---|
| Embeddings | `BAAI/bge-base-en-v1.5` via `sentence-transformers` |
| Vector store | ChromaDB (persistent, in-process) |
| LLM | Groq (`llama-3.1-8b-instant`) or Ollama (local) |
| API | FastAPI + Uvicorn |
| UI | Angular 19 |
| Tunnelling | ngrok (optional, for remote sharing) |

---

## 3. Folder Structure

```
rag-billing-support/
├── api/                        FastAPI server
│   ├── main.py                 App entrypoint, CORS, /api/ask endpoint
│   └── models.py               Pydantic request/response models
│
├── data/
│   ├── billing_articles/       Source PDFs (ingested by default pipeline)
│   └── markdown/               Markdown versions (used for structure-aware chunking)
│
├── evaluation/                 Evaluation datasets and results
│   ├── questions.json          Frozen test questions with evidence terms
│   ├── hit_at_5_results.json   Hit@5 scores per strategy
│   └── results.md              Full evaluation write-up
│
├── frontend/                   Angular 19 chat UI
│   ├── src/app/
│   │   ├── components/chat/    Chat bubble UI, sources panel, timing bar
│   │   └── services/           HTTP client to FastAPI
│   └── proxy.conf.json         Dev proxy: /api → localhost:8000
│
├── scripts/                    CLI tools (run in order)
│   ├── ingest_articles.py      Load, chunk, embed, store in ChromaDB
│   ├── run_search.py           Dump retrieval results for all strategies
│   ├── run_evaluation.py       Compute Hit@5 scores
│   ├── run_filter_demo.py      Demo metadata filtering by product_area
│   ├── run_generation_tests.py Run answerable + refusal Q&A tests
│   └── ask.py                  Interactive CLI assistant
│
├── src/                        Core RAG pipeline (Python package)
│   ├── config.py               All paths and constants
│   ├── chunking/               baseline, structure_aware, semantic chunkers
│   ├── generation/             LLM client, prompts, citations, refusal
│   ├── ingestion/              File loaders (PDF, DOCX, Excel, MD, TXT)
│   └── retrieval/              ChromaDB queries, metadata filters
│
├── tests/                      pytest test suite
├── .env                        Your local secrets (gitignored)
├── .env.example                Template — copy to .env and fill in
└── requirements.txt            Python dependencies
```

---

## 4. Prerequisites

| Tool | Version | Notes |
|---|---|---|
| Python | 3.11+ | |
| Node.js | 18+ | For the Angular UI |
| npm | 9+ | Comes with Node |
| Angular CLI | 19+ | Installed automatically via `npx` |
| ngrok | Any | Only needed for remote sharing |

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

> **First run note:** `ingest_articles.py` downloads the `BAAI/bge-base-en-v1.5` model (~440 MB) from Hugging Face and caches it locally. Subsequent runs skip the download.

### 3. Configure environment variables

```powershell
copy .env.example .env
```

Open `.env` and fill in your values — see [Section 6](#6-api-keys-and-llm-models) for how to get them.

### 4. Install Angular dependencies

```powershell
cd frontend
npm install
cd ..
```

---

## 6. API Keys and LLM Models

### Groq (recommended — free, cloud)

Groq provides fast, free inference for open-weight models.

1. Go to [console.groq.com](https://console.groq.com) and create a free account
2. Navigate to **API Keys** → **Create API Key**
3. Copy the key and paste it into `.env`:

```env
LLM_PROVIDER=groq
GROQ_API_KEY=gsk_...your_key_here...
LLM_MODEL=llama-3.1-8b-instant
```

**Available Groq models** (set as `LLM_MODEL`):

| Model | Speed | Quality | Notes |
|---|---|---|---|
| `llama-3.1-8b-instant` | Very fast | Good | Default — best for this use case |
| `llama-3.3-70b-versatile` | Moderate | Excellent | Better reasoning, higher latency |
| `gemma2-9b-it` | Fast | Good | Google Gemma alternative |
| `mixtral-8x7b-32768` | Fast | Good | Long context window |

> Free tier limits: 14,400 requests/day, 500,000 tokens/minute. More than enough for development.

---

### Ollama (alternative — fully local, no API key)

Run models locally with no internet dependency.

1. Download and install Ollama from [ollama.com](https://ollama.com)
2. Pull a model:

```powershell
ollama pull llama3.2:latest       # 2 GB — fast, good quality
ollama pull llama3.2:1b           # 0.8 GB — very fast, smaller
ollama pull mistral:latest        # 4 GB — strong reasoning
```

3. Start the Ollama server (runs in the background automatically after install):

```powershell
ollama serve
```

4. Set `.env`:

```env
LLM_PROVIDER=ollama
LLM_MODEL=llama3.2:latest
OLLAMA_BASE_URL=http://localhost:11434
```

---

### Full `.env` reference

```env
# ── LLM Provider ─────────────────────────────────────────────────────────────
# Set to "groq" for cloud inference or "ollama" for local inference
LLM_PROVIDER=groq

# ── Groq (cloud) ─────────────────────────────────────────────────────────────
# Required when LLM_PROVIDER=groq
# Get your key at: https://console.groq.com → API Keys
GROQ_API_KEY=gsk_...

# Model name — see table above for options
LLM_MODEL=llama-3.1-8b-instant

# ── Ollama (local) ────────────────────────────────────────────────────────────
# Only needed when LLM_PROVIDER=ollama
# OLLAMA_BASE_URL=http://localhost:11434
```

---

## 7. Running the Pipeline

Run these scripts in order once before starting the application. The virtual environment must be active.

### Step 1 — Ingest articles and build ChromaDB collections

```powershell
python scripts\ingest_articles.py
```

Reads all articles from `data/billing_articles/`, chunks them with all three strategies, embeds them, and writes three ChromaDB collections to `chroma_db/`.

```
Loaded articles: 6
Metadata validation passed: 6/6
Baseline chunk count:        41
Structure-aware chunk count: 87
Semantic chunk count:        53
Built collection: billing_baseline
Built collection: billing_structure_aware
Built collection: billing_semantic
```

> Re-run this whenever you add or change articles. Ingestion is the only step that requires time — subsequent runs of the API and UI use the stored embeddings.

### Step 2 (optional) — Run retrieval evaluation

```powershell
python scripts\run_evaluation.py
```

Outputs Hit@5 scores for all three strategies against the 8 frozen evaluation questions.

### Step 3 (optional) — Run generation tests

```powershell
python scripts\run_generation_tests.py
```

Tests answerable questions and refusal behaviour. Requires `.env` to be configured with a working LLM provider.

---

## 8. Running the Application

Open **two terminals** in the project root, both with the virtual environment active.

### Terminal 1 — FastAPI backend

```powershell
.venv\Scripts\python.exe -m uvicorn api.main:app --port 8000
```

API is available at `http://127.0.0.1:8000`.  
Interactive API docs: `http://127.0.0.1:8000/docs`

### Terminal 2 — Angular UI

```powershell
cd frontend
npx ng serve --port 4200 --proxy-config proxy.conf.json
```

Open `http://localhost:4200` in your browser.

The Angular dev server proxies all `/api/*` requests to `http://127.0.0.1:8000`, so the UI and API stay decoupled.

---

## 9. Sharing via ngrok

ngrok creates a public HTTPS URL that tunnels to your local application, letting someone on a different network use your local running version.

### Install ngrok

Download from [ngrok.com/download](https://ngrok.com/download) or use winget:

```powershell
winget install ngrok
```

### (Optional) Add a free auth token to remove the interstitial page

1. Create a free account at [dashboard.ngrok.com](https://dashboard.ngrok.com)
2. Copy your authtoken from **Your Authtoken**
3. Run:

```powershell
ngrok config add-authtoken <your-authtoken>
```

This removes the "Visit Site" warning page that appears for unauthenticated tunnels.

### Start ngrok

With both the FastAPI backend and Angular dev server already running:

```powershell
ngrok http 4200
```

ngrok will display a public URL like:

```
Forwarding   https://abc123.ngrok-free.app → http://localhost:4200
```

Share that URL. The person opening it:
1. Sees an ngrok warning page on first visit (click **Visit Site** to continue) — not shown if you added an authtoken
2. Gets the full chat UI, fully connected to your local RAG pipeline

> **Note:** The public URL changes every time you restart ngrok (free plan). For a permanent URL, upgrade to a paid ngrok plan and use `ngrok http 4200 --domain=your-name.ngrok.app`.

---

## 10. CLI Usage

The interactive CLI assistant runs directly in the terminal without the Angular UI.

```powershell
python scripts\ask.py
```

```
Billing Migration Help-Centre Assistant
Strategy: structure  |  Collection: billing_structure_aware
Loading embedding model... ready.

Ask a question about billing migration, or type 'exit' to quit.

> What does ERR-4032 mean?

According to [HC-BILL-002--error-codes--err-4032], ERR-4032 means the billing
profile migration is incomplete because a required field was not carried over
from the legacy platform.

Cited chunks: HC-BILL-002--error-codes--err-4032
Timings — retrieval: 43 ms | generation: 812 ms | total: 855 ms

> exit
```

**Flags:**

```powershell
# Switch chunking strategy
python scripts\ask.py --strategy baseline
python scripts\ask.py --strategy structure    # default
python scripts\ask.py --strategy semantic

# Filter results by product area
python scripts\ask.py --filter-product-area billing-migration

# Show filtered vs unfiltered results side by side
python scripts\ask.py --filter-product-area billing-migration --compare-filters
```

---

## 11. Supported File Formats

Drop any supported file into `data/billing_articles/` and re-run `ingest_articles.py`.

| Format | Extension | Notes |
|---|---|---|
| Plain text | `.txt` | Read as-is |
| Markdown | `.md` | YAML front matter supported; `##` headings enable structure-aware chunking |
| Word | `.docx` | All paragraph text extracted |
| PDF | `.pdf` | Text extracted page by page via `pypdf` |
| Excel (modern) | `.xlsx` | Each sheet converted to a Markdown table; rows become individual chunks |
| Excel (legacy) | `.xls` | Same as `.xlsx` using `xlrd` |

### Adding metadata to articles

For `.md` and `.txt` files, add a YAML front matter block at the top to control how the article is indexed:

```markdown
---
article_id: HC-BILL-007
product_area: billing-migration
last_updated: 2026-01-15
---

# Your Article Title

Content goes here...
```

For other formats (PDF, DOCX, Excel), the `article_id` defaults to the filename stem and `product_area` defaults to `unknown`.

### Excel format tips

For best results with Excel files, put column headers in the first row of each sheet. The structure-aware chunker will index each data row as a separate chunk with its column labels — ideal for lookup tables like error codes or pricing plans.

---

## 12. Chunking Strategies

Three strategies are built and evaluated. The default for the API and CLI is **structure-aware**.

| Strategy | Collection | How it works | Best for |
|---|---|---|---|
| **Structure-aware** | `billing_structure_aware` | Splits on `##` section headings; parses Markdown tables into one chunk per row | Articles with clear sections and lookup tables |
| **Baseline** | `billing_baseline` | RecursiveCharacterTextSplitter (800 chars / 100 overlap) | General-purpose prose |
| **Semantic** | `billing_semantic` | Embeds sentences in a rolling window, splits where cosine distance spikes | Dense narrative text |

**Evaluation results (Hit@5 on 8 questions):**

| Strategy | Hit@5 | Table questions |
|---|---|---|
| Structure-aware | **8 / 8** | All rank 1 |
| Semantic | 8 / 8 | Q4 only at rank 5 |
| Baseline | 7 / 8 | Missed Q4 entirely |

---

## 13. Evaluation

The evaluation set is in `evaluation/questions.json` — 8 frozen questions with known answers and required evidence terms. Run the full evaluation with:

```powershell
python scripts\run_search.py       # dumps retrieval results for all 3 strategies
python scripts\run_evaluation.py   # computes Hit@5 and writes hit_at_5_results.json
```

Results are written to:

| File | Contents |
|---|---|
| `evaluation/baseline_search_dump.json` | Top-7 results per question, baseline |
| `evaluation/structure_search_dump.json` | Top-7 results per question, structure-aware |
| `evaluation/semantic_search_dump.json` | Top-7 results per question, semantic |
| `evaluation/hit_at_5_results.json` | Hit@5 scores per question and strategy |
| `evaluation/filter_comparison.json` | Filtered vs unfiltered retrieval comparison |
| `evaluation/results.md` | Full write-up with analysis |

---

## 14. Running Tests

```powershell
pytest
```

Expected: **8 passed**

The test suite covers:

- All 6 articles load and pass metadata validation
- Baseline and structure-aware chunks contain all required metadata fields
- Plain text files load without front matter
- Excel (`.xlsx`) files load and produce Markdown table output
- Empty Excel sheets are skipped
- Invalid metadata raises a `ValueError`
