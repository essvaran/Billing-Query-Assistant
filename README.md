# Week 3 RAG Practical — Billing Migration Support

This project builds and evaluates a RAG pipeline over six billing-migration
help-centre articles: **three chunking strategies** (baseline
recursive-character splitting, structure-aware table/section chunking, and
semantic cosine-distance splitting), a single fixed BGE embedding model,
Hit-in-Top-5 retrieval evaluation, and metadata filtering by `product_area`.

It also includes an interactive console app (`scripts/ask.py`) that answers
questions with grounded, cited responses via Groq (cloud LLM), and refuses
questions the corpus can't answer.

## Setup

PowerShell (the default on Windows — this is what you're in if your prompt
looks like `PS E:\...>`):

```powershell
git clone <repo-url>
cd week3-rag-billing-support

python -m venv .venv
.venv\Scripts\Activate.ps1

pip install -r requirements.txt
```

cmd.exe:

```bat
python -m venv .venv
.venv\Scripts\activate.bat

pip install -r requirements.txt
```

## Environment Variables

```powershell
copy .env.example .env
```

Edit `.env` and fill in your values. Required to run `scripts/ask.py` and
`scripts/run_generation_tests.py`. Not needed for ingestion/search/evaluation
scripts — those never call the LLM.

| Variable | What it is | How to get a value |
|---|---|---|
| `LLM_PROVIDER` | Which LLM backend to use (`groq` or `ollama`) | Set to `groq` to use the Groq cloud API (recommended). Set to `ollama` to use a local Ollama instance instead. |
| `GROQ_API_KEY` | Your Groq API key | Create a free account at [console.groq.com](https://console.groq.com), generate an API key, and paste it here. |
| `LLM_MODEL` | Model name to use for generation | Groq: `llama-3.1-8b-instant` (default). Ollama: e.g. `llama3.2:1b`. |
| `OLLAMA_BASE_URL` | Ollama server URL (only when `LLM_PROVIDER=ollama`) | Default is `http://localhost:11434`. Only change if Ollama runs on a different host/port. |

## Commands

The pipeline of scripts is run in order. No `PYTHONPATH` setup is needed —
every script under `scripts/` adds the project root to `sys.path` itself
(see `scripts/bootstrap.py`), so just run them with `python`, with the venv
activated:

```powershell
python scripts\ingest_articles.py
python scripts\run_search.py
python scripts\run_evaluation.py
python scripts\run_filter_demo.py
python scripts\run_generation_tests.py
```

Without activating the venv, use the venv's Python directly:

```powershell
.venv\Scripts\python.exe scripts\ingest_articles.py
.venv\Scripts\python.exe scripts\run_search.py
.venv\Scripts\python.exe scripts\run_evaluation.py
.venv\Scripts\python.exe scripts\run_filter_demo.py
.venv\Scripts\python.exe scripts\run_generation_tests.py
```

**Note:** On the first run, `ingest_articles.py` downloads `BAAI/bge-base-en-v1.5`
from Hugging Face and embeds all three collections (baseline, structure-aware,
semantic). This takes a few minutes; later runs use the local cache and are fast.
You only need to re-run it when article content changes.

## Run the Interactive App

Once `scripts/ingest_articles.py` has been run at least once (so the Chroma
collections exist) and `.env` is configured, start the console app:

```powershell
python scripts\ask.py
```

By default it uses the **structure-aware** collection. Use `--strategy` to
switch:

```powershell
python scripts\ask.py --strategy baseline
python scripts\ask.py --strategy structure
python scripts\ask.py --strategy semantic
```

The header line confirms which strategy is active:

```text
Billing Migration Help-Centre Assistant
Strategy: semantic  |  Collection: billing_semantic
Ask a question about billing migration, or type 'exit' to quit.
```

It opens a `>` prompt. Type a question and press Enter; type `exit` to quit.

```text
> What does ERR-4032 mean?

According to [HC-BILL-002--error-codes--err-4032], ERR-4032 means the
billing profile migration is incomplete because a required field was not
carried over from the legacy platform.

Timings  —  retrieval: 42 ms  |  generation: 830 ms  |  total: 872 ms

Cited chunks: HC-BILL-002--error-codes--err-4032

Retrieved (top 5):
  - HC-BILL-002--error-codes--err-4032 (score 0.87)
  - HC-BILL-003--payment-method-errors-during-migration--err-4040 (score 0.71)
  ...

> What is the guaranteed refund SLA?

I cannot answer that from the indexed help-centre articles.

> exit
```

Every answer either cites a real `chunk_id` from the retrieved context or
falls back to the refusal message. Citations pointing outside the retrieved
set are treated as ungrounded and replaced with the refusal.

Each response also shows split **timings**: retrieval (BGE embed + ChromaDB
cosine search) and generation (LLM round-trip) separately, so you can compare
strategies.

## Expected Output

```text
evaluation/baseline_search_dump.json
evaluation/structure_search_dump.json
evaluation/semantic_search_dump.json
evaluation/hit_at_5_results.json
evaluation/filter_comparison.json
evaluation/generation_transcripts.json
results.md
```

## Vector Database

ChromaDB is used as the vector database with **persistent on-disk storage**
(`chroma_db/` directory). It runs inside the Python process — no separate
server needed. Three collections are built:

| Collection | Strategy |
|---|---|
| `billing_baseline` | RecursiveCharacterTextSplitter (800/100) |
| `billing_structure_aware` | Table-row + section prose chunking |
| `billing_semantic` | Cosine-distance sentence-window splitting |

## Testing the App After Running

1. **Run the automated tests** — checks metadata completeness on every
   chunk and that table rows keep their header labels:

   ```bash
   pytest
   ```

   Expect `7 passed`.

2. **Check the Hit@5 numbers printed by `run_evaluation.py`** — all three
   strategies are reported, along with per-question rank for each.

3. **Spot-check a retrieved answer manually** — open any of the three
   `evaluation/*_search_dump.json` files and confirm the rank-1 result for
   a question (e.g. `Q1` / "What does ERR-4032 mean?") actually contains the
   answer text.

4. **Check the metadata-filter demo** — open
   `evaluation/filter_comparison.json` and confirm `"top1_changed": true`,
   i.e. filtering by `product_area` actually changed which chunk ranked first.

5. **Try the interactive app** with a supported question (e.g. "What does
   ERR-4032 mean?") and an unsupported one (e.g. "What is the guaranteed
   refund SLA?") and confirm the second one refuses instead of guessing. Try
   all three `--strategy` options and compare retrieval timings.

6. **Read `results.md`** for the full write-up, including the documented
   retrieval weakness (§11) and the final chunking strategy decision (§12).

## Scope Note

Only the six synthetic billing-migration articles under
`data/billing_articles/` are indexed. No historical corpus was indexed. See
`results.md` for the full write-up.
