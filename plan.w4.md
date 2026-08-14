# Week 4 Implementation Plan — Debugging Retrieval

> **Domain:** Customer support tickets (billing migration)
> **Goal:** Prove where retrieval fails, make ONE change, show a before→after number.

---

## Context: Where We Stand After Week 3

The project already has three chunking collections in ChromaDB (`billing_baseline`,
`billing_structure_aware`, `billing_semantic`), a BGE-base embedding model, a
FastAPI `/api/ask` endpoint, and an Angular UI.

Week 3 evaluation used **hit@5** on 8 frozen questions and achieved 8/8 on both
the baseline and structure-aware collections. Week 4 changes two things:

1. We tighten the metric to **hit-rate@3** (top-3 only).
2. We test the **baseline** collection — not the structure-aware one — because
   that is the collection that actually exhibits the failure mode described in
   the problem statement ("face-plants on error codes"). Structure-aware already
   achieves rank-1 for everything by design (one error-code row per chunk); using
   it here would leave nothing to improve.

---

## Phase 1 — Golden Set Construction (12 questions)

### What

Extend the existing 8 frozen questions to **12**, committed as
`evaluation/golden_set.jsonl` before any retrieval change is made.

Each entry contains:
- `id` — Q1–Q12
- `question` — verbatim as a customer would type it
- `known_chunk_id` — the structure-aware chunk ID that contains the answer
  (canonical identifier; hit-rate is measured by evidence-term matching, but
  the chunk ID is the authoritative reference)
- `expected_article_id`, `expected_section`
- `required_evidence_terms` — ALL must appear in a retrieved chunk for it to
  count as a hit
- `exact_token` — boolean flag; true when the question contains an exact
  lexical token that dense retrieval is structurally bad at

### Why 12, not 8

The task requires at least 4 questions with exact tokens (error codes, plan IDs,
ticket IDs). We already have 4 (Q1–Q4). The new 4 (Q9–Q12) add more exact-token
queries from different error series to broaden the stress-test and avoid the
golden set looking like it was designed to pass.

### New Questions: Q9–Q12

| ID | Question | Exact token | Source |
|---|---|---|---|
| Q9 | What causes PAY-1001? | `PAY-1001` | HC-BILL-002 PAY-series table |
| Q10 | What does PLAN-ENT-V1 map to on the new platform? | `PLAN-ENT-V1` | HC-BILL-001 plan mapping table |
| Q11 | What does ERR-4155 mean? | `ERR-4155` | HC-BILL-002 core error codes table |
| Q12 | What causes SYNC-9001? | `SYNC-9001` | HC-BILL-002 SYNC-series table |

These four are chosen because:
- Each appears in a **table row** that would be merged with unrelated rows in
  the 800-char baseline chunks, diluting the embedding signal.
- Each token is syntactically unique (PAY-1001, PLAN-ENT-V1, ERR-4155, SYNC-9001)
  so BM25 can find it via exact match even if dense retrieval cannot.

### Rule: Frozen before measurement

The golden set file is committed before `scripts/run_w4_baseline.py` is run.
Any post-hoc change to the golden set invalidates the baseline number.

---

## Phase 2 — Baseline Measurement (hit-rate@3, dense only)

### Retriever under test

**Baseline collection** (`billing_baseline`) with **pure dense retrieval** (Chroma
cosine similarity, k=3). No reranking, no BM25. This is the retriever described
in the problem statement: "returns three warm, semantically-adjacent articles
about billing in general, none of which mention the code."

### Metric

**hit-rate@3** = fraction of 12 questions where at least one of the top-3 retrieved
chunks contains ALL `required_evidence_terms`.

This is identical to how `src/evaluation/hit_at_k.py` currently works, with k
changed from 5 to 3.

### Latency

For each of the 12 queries, repeat the retrieval call **5 times** and record
wall-clock time per call. Take the **p50 (median)** across all 12 × 5 = 60
measurements. This is the "before" latency.

### Script

`scripts/run_w4_baseline.py` — outputs `evaluation/w4_baseline.json`.

### What to write down before touching anything

The hit-rate@3 number and the p50 latency. These cannot be changed retrospectively.

---

## Phase 3 — Inspection View and Failure Labeling

### Inspection view

For each of the 12 questions, print:
1. The question
2. The top-3 retrieved chunks (rank, chunk_id, score, first 200 chars of text)
3. Whether the required evidence appeared in any of the 3

This is the "inspection view" the task refers to. It is not a separate UI;
it is the detailed output in `evaluation/w4_baseline.json` rendered by the
evaluation script.

### Labeling rules

For each **miss** (question where hit@3 = No):

| Label | Meaning | Evidence required |
|---|---|---|
| **R** | Retrieval failure — correct context was not in top-3 | Show the top-3 chunk_ids; none contains the evidence terms |
| **G** | Generation failure — correct context WAS in top-3 but answer was wrong | Show the chunk that contains the evidence terms at rank ≤3 |
| **Not-In-Corpus** | The answer does not exist in any indexed chunk | Show that no chunk in the full collection contains the evidence terms |

Label every miss with ONE line of evidence (e.g. "Top-3 chunks are
HC-BILL-002--baseline--0002, HC-BILL-003--baseline--0002, HC-BILL-001--baseline--0005;
none contains 'PAY-1001'").

### Expected outcome

Dense retrieval on a baseline chunker is structurally bad at exact tokens because:

- The BGE embedding of "PAY-1001" is semantically close to "payment method
  migration error" — which matches MANY chunks across all articles about payment.
- The baseline chunker groups multiple error-code rows into one 800-char chunk,
  so the embedding of the chunk containing PAY-1001 is dominated by the generic
  "payment error table" signal rather than the specific token PAY-1001.
- BM25 scores a chunk containing exactly the token "PAY-1001" much higher than
  any generic "payment error" chunk.

We expect the R-tally to be ≥2 (the failures that BM25+RRF will fix).

---

## Phase 4 — Single Retrieval Change: BM25 + RRF Fusion (k=60)

### The change

Add BM25 retrieval over the baseline collection's chunks and fuse its ranked
list with the dense ranked list using Reciprocal Rank Fusion (k=60). Return
the top-3 by RRF score. This is **one** change (two components are one
algorithm: hybrid search).

### Implementation

**New file: `src/retrieval/bm25_search.py`**
- Loads all chunk texts from ChromaDB at startup into a `rank_bm25.BM25Okapi` index
- `bm25_search(query, k=25)` — tokenizes query, returns top-k chunks by BM25 score

**New file: `src/retrieval/hybrid_search.py`**
- `hybrid_search(collection_name, query, dense_k=25, bm25_k=25, rrf_k=60, top_n=3)`
- Calls dense search (Chroma, k=25) and BM25 search (k=25) in parallel
- Fuses with RRF: `score(doc) = Σ 1/(rrf_k + rank)`
- Returns top_n by RRF score

**New library: `rank_bm25`** — added to `requirements.txt`

### Why exactly one change

The task explicitly warns: "Adding BM25 AND a reranker in the same run, then
reporting one delta — two changes means zero information about which one earned
it." We add BM25+RRF only. The cross-encoder reranker is evaluated in the Bonus
section (if attempted) as a separate run.

---

## Reasoning: Why BM25 + RRF?

### Root cause of the failures

The R-failures in Phase 3 share a single root cause: the **vocabulary gap**
between the query token (e.g. `PAY-1001`) and the dense embedding space.

The BGE-base-en-v1.5 model is trained on natural language. When it embeds
`PAY-1001`, it produces a vector that is close to "payment method error" or
"billing issue" — not specifically close to the chunk that contains exactly
the string `PAY-1001`. Any chunk about payment errors will score similarly.

This is fundamentally a **lexical retrieval problem**, not a semantic one.
Lexical retrieval is what BM25 was designed for.

### Why BM25 works here

BM25 (Best Matching 25) scores a document by:

```
score(d, q) = Σ_t IDF(t) × [TF(t,d) × (k1+1)] / [TF(t,d) + k1 × (1 - b + b × |d|/avgdl)]
```

Where:
- `TF(t,d)` = frequency of term t in document d
- `IDF(t)` = log((N - n(t) + 0.5) / (n(t) + 0.5)) — high when the term is rare
- `k1=1.5`, `b=0.75` — tuning constants (defaults in `rank_bm25`)

If the query is "PAY-1001" and exactly ONE chunk contains "PAY-1001":
- `IDF(PAY-1001)` ≈ log(N/1) — very high because the token is rare in the corpus
- That chunk gets a score several times higher than any other chunk
- The correct chunk ranks #1 in BM25 virtually guaranteed

### Why RRF instead of score addition or averaging

BM25 scores (typically 0–15 on a small corpus) and dense cosine scores (0–1)
are **not on the same scale**. Adding or averaging them gives the higher-scale
metric complete dominance.

RRF fuses **ranks** instead of scores:

```
rrf_score(d) = 1/(k + rank_dense(d)) + 1/(k + rank_bm25(d))
```

A document ranked 1st in dense and 5th in BM25 gets `1/61 + 1/65 = 0.0164`.
A document ranked 40th in dense but 1st in BM25 gets `1/100 + 1/61 = 0.0264`.
The BM25-top result wins, which is correct for exact-token queries.

The constant `k=60` comes from the original RRF paper (Cormack et al., 2009).
It controls how steeply rank differences are penalized. k=60 is robust across
most retrieval settings because it smooths the 1/rank curve without removing
the ranking signal entirely.

---

## Alternatives Considered and Their Best Use Cases

### Alternative 1: Cross-Encoder Reranker

**What it is:** A BERT-style model (e.g. `cross-encoder/ms-marco-MiniLM-L-6-v2`
or `BAAI/bge-reranker-base`) that takes (query, chunk) pairs and produces a
relevance score. Applied to the top-25 from dense retrieval to re-rank them.

**Best scenario:** The correct chunk IS already in the dense top-25 but is
ranked poorly (rank 10–25). The reranker, which reads both query and chunk
jointly, can recognize the correct match and push it to rank 1.

**Why not selected:**
Our R-failures are **recall failures**, not ranking failures. If `PAY-1001` is
not in the dense top-25 at all, the reranker never sees it — it can only
reorder what dense retrieval provides. BM25+RRF expands the candidate set;
reranking cannot.

Additionally: the reranker adds O(25 × query) model inferences per query.
On CPU with bge-reranker-base (110M params), this is 500–2000ms per query.
BM25+RRF adds ~1–5ms.

**When to prefer reranker over BM25+RRF:**
- Your dense retriever has good recall (correct chunk is almost always in
  top-25) but poor precision (wrong things outrank the correct one).
- The query-document matching benefit requires reading both simultaneously
  (complex multi-hop queries, negations, comparative questions).
- You have GPU and latency budget.

### Alternative 2: HyDE (Hypothetical Document Embeddings)

**What it is:** Ask an LLM to generate a hypothetical answer, embed the
hypothetical, use that vector as the query instead of the raw query.

**Best scenario:** The user's query vocabulary doesn't match the document
vocabulary but a hypothetical answer would. Example: "credit card not
working" → LLM generates "The payment method returned a declined response;
ERR-4040 indicates..." → that hypothetical embeds close to the actual chunk.

**Why not selected:**
Our failures are exact-token queries (`PAY-1001`, `PLAN-ENT-V1`). If the LLM
generates a hypothetical for "What causes PAY-1001?", it might hallucinate
wrong causes or use different error code terminology. The hypothetical loses
the exact token that BM25 would reliably find.

Adds one LLM round-trip per query (500–2000ms) with no benefit for lexical
retrieval failures.

**When to prefer HyDE over BM25+RRF:**
- Queries are vague or conversational ("something about my billing being wrong").
- Document vocabulary is highly technical but queries are casual.
- You are NOT dealing with exact-identifier lookups.

### Alternative 3: Metadata Pre-filtering + Dense Retrieval

**What it is:** Use metadata (e.g. `product_area=billing-migration`) to
restrict the ChromaDB query to a subset of chunks before running dense retrieval.

**Best scenario:** You know the category of each query in advance. For a
helpdesk system where tickets are already tagged with category labels, filtering
reduces the search space dramatically.

**Why not selected:**
Error codes span multiple articles and product areas. `PAY-1001` is in
`article_02.md` (billing-migration), but `SYNC-9001` is also in `article_02.md`
while referring to accounting integrations. We cannot reliably determine which
filter to apply from the query alone without another classifier. Adding a query
classifier is a second change.

**When to prefer filtering over BM25+RRF:**
- Categories are known (user selects a ticket type before asking).
- You want to reduce latency by shrinking the search space (fewer chunks to embed/score).
- Corpus has large, clearly separated domains.

### Alternative 4: MMR (Maximal Marginal Relevance)

**What it is:** At reranking time, select chunks that are relevant to the query
AND maximally diverse from each other. Penalizes near-duplicate results.

```
MMR(d) = λ × sim(d, query) - (1-λ) × max_{d' ∈ selected} sim(d, d')
```

**Best scenario:** Your top-3 contains three near-copies of the same section
(the Bonus scenario in the task). MMR promotes diversity.

**Why not selected as the primary change:**
MMR does not fix recall. If the correct chunk is not in the dense top-25, MMR
doesn't bring it in. Worse, MMR can push the correct chunk OUT of the top-3
in the name of variety — the task explicitly notes this risk.

**When to prefer MMR over BM25+RRF:**
- Dense retrieval has good recall but the top-K is dominated by redundant chunks.
- You have a large corpus with many near-duplicate passages.
- You have measured that diversity improves downstream answer quality.

### Alternative 5: Fine-Tuning the Embedding Model

**What it is:** Domain-adapt BGE-base on (query, correct-chunk, negative-chunk)
triplets from the golden set and similar support data.

**Best scenario:** The failure is systematic across the entire domain — the model
consistently fails to close the vocabulary gap between user queries and support
articles.

**Why not selected:**
- The golden set has only 12 questions — far too few labeled pairs for effective
  fine-tuning (typical minimum is hundreds to thousands of pairs).
- Fine-tuning requires significant setup, compute, and re-indexing the entire
  corpus after training.
- BM25+RRF is a zero-training fix that addresses the exact same root cause
  for this type of failure.

**When to prefer fine-tuning over BM25+RRF:**
- You have a large labeled dataset (500+ query-chunk pairs).
- The failure is semantic (not lexical) — the model genuinely cannot understand
  the domain, not just that it misses exact tokens.
- You have the infrastructure to retrain and re-index regularly.

---

## Phase 5 — Post-Change Measurement

Run the SAME 12 questions through the hybrid retriever (BM25+RRF, k=60, top-3).

Measure:
- hit-rate@3 (same evidence-term matching)
- p50 latency (same 5-repeat methodology)

Report: `before → after` for both metrics.

For each question, record: **Fixed** (was miss, now hit), **Unfixed** (still a
miss), or **Still Passing** (was hit, still hit).

Explain which specific R-failures the change addressed and which (if any) it
left untouched.

---

## Phase 6 — Result Documentation (`result.w4.md`)

The result file contains, in order:

1. The 12-question golden set table with known-correct chunk_ids
2. Baseline hit-rate@3 (written before any change)
3. R/G/Not-In-Corpus tally with one line of evidence per failure
4. One-paragraph justification of the BM25+RRF choice (referencing the tally)
5. After hit-rate@3
6. Before/after p50 latency (one table)
7. Per-question fixed/unfixed table
8. Shipping decision with the number behind it

---

## File Checklist

| File | Purpose |
|---|---|
| `evaluation/golden_set.jsonl` | 12 questions, frozen before baseline run |
| `src/retrieval/bm25_search.py` | BM25 index + search |
| `src/retrieval/hybrid_search.py` | RRF fusion |
| `scripts/run_w4_baseline.py` | Measure hit@3 + latency before change |
| `scripts/run_w4_hybrid.py` | Measure hit@3 + latency after change |
| `evaluation/w4_baseline.json` | Raw baseline results |
| `evaluation/w4_hybrid.json` | Raw hybrid results |
| `result.w4.md` | Final report |
| `requirements.txt` | Add `rank-bm25` |

---

## Anti-Patterns to Avoid

- **Two changes in one run.** Adding BM25 + reranker together means you cannot
  attribute the delta to either change. Do BM25+RRF only.
- **Fusing scores instead of ranks.** BM25 scores (0–15) and cosine scores
  (0–1) are not comparable. Use RRF on ranks.
- **Inventing golden set questions to make the baseline look bad.** Questions
  must come from real support scenarios. Q9–Q12 come directly from error codes
  that appear in the indexed articles.
- **Labelling a miss as R without checking the top-3.** If the correct chunk is
  in the top-3 but the LLM gave a wrong answer, that is G — no retrieval change
  fixes it.
- **Agreeing to swap the LLM model.** If the tally says the failures are R,
  a better LLM changes none of them.
