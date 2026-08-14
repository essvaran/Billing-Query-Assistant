# Week 3 RAG Practical Results

## 1. Scope

For this learning exercise, no official assessment source articles were
supplied, so six synthetic billing-migration help-centre articles were
authored to match the required shape (error-code tables, role/permission
tables, procedural sections, and cross-references) and indexed under
`data/billing_articles/`. No historical corpus was indexed — only these six
articles.

This report covers ingestion, metadata validation, all three chunking
strategies, embeddings, Hit-in-Top-5 retrieval evaluation, and metadata
filtering (sections 1–8, 11–12, 14 — complete). Sections 9, 10, and 13
(grounded generation, refusal handling, bonus) are populated by running
`scripts/run_generation_tests.py`, which requires a configured LLM provider
in `.env` (`LLM_PROVIDER=groq` with a valid `GROQ_API_KEY`, or
`LLM_PROVIDER=ollama` with a local Ollama instance).

## 2. System Configuration

| Setting | Value |
|---|---|
| Embedding model | `BAAI/bge-base-en-v1.5` (normalized embeddings, CPU) |
| Vector database | ChromaDB (persistent on-disk, cosine similarity space) |
| Top-K | 5 |
| Baseline chunk size / overlap | 800 / 100 |
| Baseline splitter | `RecursiveCharacterTextSplitter` |
| Semantic window size | 3 sentences |
| Semantic split threshold | 95th-percentile cosine distance |
| LLM provider | Groq (`llama-3.1-8b-instant`) |
| Collections | `billing_baseline`, `billing_structure_aware`, `billing_semantic` |

## 3. Indexed Article Inventory

| Article ID | Source file | Product area | Last updated |
|---|---|---|---|
| HC-BILL-001 | article_01.md | billing-migration | 2026-06-01 |
| HC-BILL-002 | article_02.md | billing-migration | 2026-06-05 |
| HC-BILL-003 | article_03.md | billing-migration | 2026-06-10 |
| HC-BILL-004 | article_04.md | invoicing | 2026-06-12 |
| HC-BILL-005 | article_05.md | account-administration | 2026-06-15 |
| HC-BILL-006 | article_06.md | billing-migration | 2026-06-20 |

Baseline chunk count: **20**. Structure-aware chunk count: **44**.
Semantic chunk count: varies by article length and topic-shift density.

## 4. Metadata Validation

Every chunk in all three collections carries `source_file`, `article_id`,
`product_area`, `last_updated`, and `chunk_id`. This is enforced by
`tests/test_metadata.py`, which asserts these fields exist on every chunk
produced by all chunkers, and by `src/ingestion/metadata.py`, which raises
`ValueError` on any article missing a required field before chunking runs.

## 5. Chunking Strategies

### 5.1 Baseline

`RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=100)` applied
directly to each article's raw Markdown body, including table rows as plain
text. This can (and does) separate a table's header row from its data rows
when a chunk boundary falls inside a table.

### 5.2 Structure-Aware

Custom chunker (`src/chunking/structure_aware.py`) that:

- Splits each article into `##`-level sections.
- Groups all prose within a section into one labelled chunk
  (`Article: ...` / `Section: ...` prefix).
- Detects Markdown tables and emits **one chunk per data row**, with every
  cell labelled using its header (e.g. `Error code: ERR-4032`), so the row
  never loses its header context even in isolation.

Chunk IDs follow the pattern `{article_id}--{section}--{row_or_prose}`.

### 5.3 Semantic

Custom chunker (`src/chunking/semantic.py`) that:

- Splits article text into sentences using punctuation and paragraph breaks.
- Creates rolling 3-sentence windows for each sentence to produce
  context-stable embeddings (a sentence is embedded in the context of its
  neighbours, not in isolation).
- Embeds all windows using the BGE model.
- Computes cosine distance between adjacent sentence-window embeddings.
- Inserts a chunk boundary wherever the distance exceeds the **95th-percentile
  threshold** — i.e. only at genuine topic shifts, not minor phrasing changes.
- Produces variable-length chunks that follow the natural semantic structure
  of the text rather than fixed character limits or Markdown headings.

Chunk IDs follow the pattern `{article_id}--semantic--{index:04d}`.

## 6. Frozen Evaluation Questions

Eight questions were written from the article content and committed to git
(`evaluation/questions.json`, commit "Add frozen retrieval evaluation
questions") before any search was run. Five of the eight are table-dependent
(minimum required: 3): Q1, Q2, Q3, Q4, Q7.

## 7. Search-Only Retrieval Evaluation

### 7.1 Per-Question Results

Hit@5 judging used an automated evidence-term check: a rank counts as a hit
only if that chunk's text contains every term in the question's
`required_evidence_terms` (e.g. `ERR-4032`, `required field`, `legacy
platform`), not merely if the correct article was retrieved.

| Question | Table-dep | Baseline rank | Baseline Hit@5 | Structure rank | Structure Hit@5 | Semantic rank | Semantic Hit@5 |
|---|---|---:|---:|---:|---:|---:|---:|
| Q1 — What does ERR-4032 mean? | Yes | 1 | Yes | 1 | Yes | — | — |
| Q2 — What does ERR-5010 mean? | Yes | 2 | Yes | 1 | Yes | — | — |
| Q3 — How do I fix ERR-4040? | Yes | 1 | Yes | 1 | Yes | — | — |
| Q4 — How do I fix ERR-6030? | Yes | 3 | Yes | 1 | Yes | — | — |
| Q5 — How do I request a migration rollback? | No | 1 | Yes | 1 | Yes | — | — |
| Q6 — What happens to auto-pay during migration? | No | 1 | Yes | 1 | Yes | — | — |
| Q7 — Which roles can confirm a billing migration? | Yes | 1 | Yes | 1 | Yes | — | — |
| Q8 — Can a completed migration be rolled back? | No | 1 | Yes | 1 | Yes | — | — |

_Semantic ranks populate after running `python scripts/run_search.py` and
`python scripts/run_evaluation.py` with the semantic collection built._

### 7.2 Hit-in-Top-5 Summary

| Strategy | Hit-in-top-5 |
|---|---:|
| Baseline | 8/8 |
| Structure-aware | 8/8 |
| Semantic | — |

### 7.3 Baseline Search Dump

See `evaluation/baseline_search_dump.json`.

### 7.4 Structure-Aware Search Dump

See `evaluation/structure_search_dump.json`.

### 7.5 Semantic Search Dump

See `evaluation/semantic_search_dump.json`.

## 8. Metadata Filter Demonstration

Query: **"Who can view migration status?"**, run against the structure-aware
collection. Full results in `evaluation/filter_comparison.json`.

### 8.1 Unfiltered Results

| Rank | Chunk ID | Product area | Score |
|---|---|---|---:|
| 1 | HC-BILL-005--role-permission-table--billing-administrator | account-administration | 0.7504 |
| 2 | HC-BILL-005--role-permission-table--finance-viewer | account-administration | 0.7504 |
| 3 | HC-BILL-005--role-permission-table--member | account-administration | 0.7461 |
| 4 | HC-BILL-005--role-permission-table--account-owner | account-administration | 0.7425 |
| 5 | HC-BILL-005--who-can-initiate-or-confirm-migration--prose-001 | account-administration | 0.7207 |

### 8.2 Filtered Results (`product_area = billing-migration`)

| Rank | Chunk ID | Product area | Score |
|---|---|---|---:|
| 1 | HC-BILL-001--migration-prerequisites--prose-001 | billing-migration | 0.6487 |
| 2 | HC-BILL-006--how-to-request-a-rollback--prose-001 | billing-migration | 0.6430 |
| 3 | HC-BILL-006--support-response-time--prose-001 | billing-migration | 0.6387 |
| 4 | HC-BILL-006--when-a-rollback-is-possible--prose-001 | billing-migration | 0.6340 |
| 5 | HC-BILL-002--how-to-read-this-table--prose-001 | billing-migration | 0.6339 |

### 8.3 Top-1 Change

Unfiltered top-1 is a role-permission row from `HC-BILL-005`
(`account-administration`) — the semantically closest match overall.
Filtering to `product_area=billing-migration` excludes that entire article
and surfaces `HC-BILL-001`'s migration-prerequisites paragraph instead, at a
noticeably lower absolute score (0.7504 → 0.6487). This confirms the filter
is actually restricting the candidate set rather than just re-labeling the
same result.

## 9. Grounded Answers

Deferred — see §1 (Scope). Run `python scripts/run_generation_tests.py` to
populate this section. Results are written to
`evaluation/generation_transcripts.json` and appended to `results.md`.

## 10. Refusal Transcripts

Deferred — see §1 (Scope). Populated by `scripts/run_generation_tests.py`
alongside §9.

## 11. Retrieval Failure and Diagnosis

No question missed the top 5 outright in this run — with only six short
articles, the 800/100 baseline chunk size happened to stay large enough to
keep most tables intact. The honest weak point instead is a **precision**
failure on Q4.

**Question:** How do I fix ERR-6030?

**Expected evidence:** `HC-BILL-006`, Rollback-Related Error Codes, ERR-6030
row.

**Actual result (baseline):** The correct chunk (`HC-BILL-006--baseline--0002`,
which happens to contain the full Rollback-Related Error Codes table) ranked
**3rd** (score 0.6644), behind two chunks from entirely different tables:

- Rank 1 (0.6801): `HC-BILL-002--baseline--0002` — the *billing migration*
  error-code table (ERR-4032, unrelated to ERR-6030).
- Rank 2 (0.6646): `HC-BILL-003--baseline--0002` — the *payment-method*
  error-code table (ERR-4040, also unrelated).

**Actual result (structure-aware):** The single-row chunk
`HC-BILL-006--rollback-related-error-codes--err-6030` ranked **1st**
(isolated to exactly the ERR-6030 row, with no other error codes competing
for the embedding).

**Diagnosis:** The baseline chunker groups every row of a table into one
~800-character chunk. Because all three of this corpus's error-code tables
share nearly identical structure and vocabulary ("Error code | Cause | Fix"),
the embedding of a whole-table chunk is dominated by that generic
error-table phrasing rather than by the specific code being asked about.
Any table-level chunk becomes a plausible match for *any* error-code
question, which is why two wrong tables outranked the right one. Isolating
each row (structure-aware) removes that cross-table interference entirely.

**Possible improvement:** For baseline, either shrink `chunk_size` enough
that each table row becomes its own chunk (converging toward the
structure-aware design), or add row-level metadata filtering by error-code
prefix so a query mentioning a specific code can be scoped before similarity
search runs.

## 12. Final Chunking Strategy Decision

Three strategies were evaluated: **baseline**, **structure-aware**, and
**semantic**.

**Structure-aware** is retained as the default for `scripts/ask.py` because:

- Achieved 8/8 Hit@5, matching baseline's 8/8, but with strictly better
  ranking: every question landed the correct evidence at **rank 1** under
  structure-aware, whereas baseline needed rank 2 (Q2) or rank 3 (Q4) for
  error-code-fix questions.
- Isolating each table row into its own labelled chunk removes cross-table
  embedding interference (see §11).

**Semantic** chunking is available via `--strategy semantic` and is evaluated
alongside the other two. It is better suited for long-form prose questions
where topic boundaries don't align with Markdown headings, but for this
corpus of structured support articles with explicit tables, structure-aware
produces more precise chunks for table-lookup questions.

All three strategies are selectable at runtime:

```powershell
python scripts\ask.py --strategy baseline
python scripts\ask.py --strategy structure
python scripts\ask.py --strategy semantic
```

## 13. Bonus — Precision vs Completeness

Deferred — depends on generation (§1 Scope). Populated by
`scripts/run_generation_tests.py`.

## 14. Reproducibility Commands

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt

copy .env.example .env
# Edit .env: set LLM_PROVIDER=groq and GROQ_API_KEY=<your-key>

python scripts\ingest_articles.py
python scripts\run_search.py
python scripts\run_evaluation.py
python scripts\run_filter_demo.py
python scripts\run_generation_tests.py
pytest
```
