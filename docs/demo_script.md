# Week 5 Practical Demo Script

> Read this top-to-bottom before your demo. Every graded point is marked with its marks.

---

## Before You Walk In — Run These First

```bash
# Terminal 1 — start the API
uvicorn api.main:app --reload --port 8000

# Terminal 2 — start the UI
cd frontend && npm start

# Terminal 3 — generate traces (do this ONCE before demo)
python scripts/generate_traces.py
```

Open browser at `http://localhost:4200`

---

## Step 1 — Show the System Works (Context Setting)

**What to say:**

> "This is the billing support RAG app I built in Week 3 and 4.
> A user types a billing question, the system retrieves relevant chunks
> from ChromaDB, sends them to the LLM, and returns a grounded answer."

**What to do:**

- Type this question in the chat: `What does ERR-4032 mean?`
- Show the answer appears with citations
- Point out: _"The answer cites a chunk ID in brackets — this proves the answer came from our knowledge base, not the model's memory."_

---

## Step 2 — Show Trace Logging is Working [20 marks]

**What to say:**

> "In Week 5, I added trace logging. Every single request is now
> permanently recorded as a JSON line in traces.jsonl.
> This is what makes error analysis possible."

**What to do:**

- Click the **Traces** tab in the nav bar
- Show the trace that just appeared from the question you typed
- Point out the fields: trace_id, timestamp, question, retriever, citations_valid

**Then say:**

> "Each trace has everything needed to REPLAY it — the question,
> which chunks were retrieved, the exact LLM model used, and the
> raw output before any validation."

### Show the Trace Schema (open `src/generation/answer.py`)

Point at `_write_trace()` and explain each field group:

| Field group | Fields                                               | Why it matters                                |
| ----------- | ---------------------------------------------------- | --------------------------------------------- |
| Identity    | `trace_id`, `timestamp`                              | Unique ID + when it happened                  |
| Input       | `question`, `prompt_version`, `model`, `temperature` | Reproduce the exact LLM call                  |
| Retrieval   | `retrieved_chunks`, `collection`, `top_k`            | What context the LLM saw                      |
| Generation  | `raw_output`, `final_answer`, `citations_valid`      | What the LLM said and what we showed the user |
| Performance | `retrieval_ms`, `generation_ms`, `total_ms`          | Latency breakdown                             |
| Tokens      | `input_tokens`, `output_tokens`                      | Cost tracking                                 |

---

## Step 3 — Show the Random Sample [20 marks]

**What to say:**

> "The assignment requires a provably random sample — not hand-picked traces,
> not the ones I know are broken. I used `random.seed(35)` so anyone can
> reproduce my exact 20 traces."

**What to demo — run this in terminal:**

```python
python -c "
import random, json

random.seed(35)
traces = [json.loads(l) for l in open('evaluation/traces.jsonl')]
sample = random.sample(traces, 20)

print('SEED: 35')
print(f'Total traces in file: {len(traces)}')
print(f'Sampled 20 trace IDs:')
for i, t in enumerate(sample, 1):
    print(f'  {i:2d}. {t[\"trace_id\"]}  |  {t[\"question\"][:50]}')
"
```

**What to say while it runs:**

> "Seed 35 means anyone — my assessor, a teammate — runs this same
> code and gets these exact same 20 traces. That's what makes it
> provable and not cherry-picked."

---

## Step 4 — Show Trace Replay [20 marks]

**What to say:**

> "Replayability means: given ONLY the trace record — no memory of
> what happened — I can reconstruct the exact inputs and re-run the
> LLM call. Let me show you."

**What to do:**

1. Pick one trace_id from the list above
2. Run in terminal:

```bash
python scripts/replay_trace.py --trace-id <paste-trace-id-here>
```

3. Show the output side by side — **original raw_output** vs **replayed output**

**What to say:**

> "The replayed output matches the original. The trace stored:
>
> - which chunks were retrieved (by ID)
> - the model name and temperature
> - the prompt version
>
> The only thing fetched live is the chunk TEXT from ChromaDB —
> if the knowledge base were re-ingested with different chunking,
> the replay would diverge. That's a known limitation and I've
> documented it."

---

## Step 5 — Open-Coding: 20 Observation Sentences [25 marks]

**What to say:**

> "Open-coding means reading each of my 20 sampled traces and writing
> ONE honest sentence about what I SAW — not what I think caused it,
> not what I would fix. Pure observation."

**Show `evaluation/notes.md`** — read 3–4 sentences aloud.

**What to say about the sentences:**

> "Notice these describe what happened in the trace specifically —
> which chunk was retrieved, what the model said, what citation
> appeared. I did NOT fix anything during this step.
> The zero-fix rule exists because fixing at trace 6 means
> the remaining 14 traces describe a different system."

**If asked why this discipline matters:**

> "If you diagnose and fix at the same time as observing, you find
> exactly the modes you expected. You miss the surprises. The whole
> point of error analysis is to discover failure modes you didn't
> already know about."

---

## Step 6 — Show the Failure Taxonomy [30 marks]

**What to say:**

> "After open-coding all 20, I clustered my observations into
> named failure modes. The names have to be legible to a stranger —
> not 'retrieval issue' but something specific enough to act on."

**Show `evaluation/taxonomy.md`** — walk through the table:

| Column           | What to say                                                                           |
| ---------------- | ------------------------------------------------------------------------------------- |
| Mode name        | "This name tells a non-technical manager exactly what's wrong"                        |
| Count            | "This many of my 20 traces showed this pattern"                                       |
| Frequency %      | "Count divided by 20"                                                                 |
| Severity         | "Embarrasses the client = wrong answer shown. Annoys the user = unnecessary refusal." |
| Example trace_id | "I can open this specific trace in the viewer and show you exactly what happened"     |

**Then open the Traces UI**, filter by `Citations: invalid`, and expand one trace from your top failure mode:

> "Here is a live trace from the failure mode I named. You can see
> exactly what was retrieved, what the model said, and why
> citations_valid is false."

---

## Step 7 — Show the Prediction [15 marks]

**What to say:**

> "The prediction must be falsifiable — a specific claim with
> specific numbers, committed to git BEFORE I apply any fix.
> That way I can't cheat by adjusting the number after I see
> the result."

**Show the git commit:**

```bash
git log --oneline -3
```

**Read the commit message aloud** — it should say something like:

> "Week 5: failure taxonomy + dated prediction (2026-08-24)
>
> Prediction: [specific change] will reduce [mode name]
> from X% (N/20) to under Y% by [date]"

**What to say:**

> "The date in the commit proves I wrote this before applying any fix.
> Next week I make the change, measure the new frequency,
> and check whether I hit the number. Being wrong teaches me something.
> An unfalsifiable prediction — 'this should improve things' —
> teaches me nothing."

---

## Step 8 — Benchmark Note [10 marks]

**What to say:**

> "The final requirement is 3 sentences on why a public benchmark
> score — like BEIR or MMLU — would not have surfaced any of
> my top 3 failure modes."

**Read your 3 sentences from `evaluation/notes.md`.**

**If asked to elaborate:**

> **Sentence 1 — Domain gap:**
> "Public benchmarks cover general knowledge. Billing error codes
> like ERR-4032 and PLAN-ENT-V1 appear nowhere in those datasets.
> A model scoring 90% on BEIR has never seen this vocabulary."

> **Sentence 2 — Metric gap:**
> "Citation validation failures — where the model writes a good
> answer but cites a hallucinated chunk ID — score perfectly fine
> on EM and F1 because those metrics compare answer TEXT, not
> the SOURCE of the claims."

> **Sentence 3 — Distribution gap:**
> "Benchmark questions are carefully authored and clean.
> Real users type 'migration is stuck' and 'billing page shows error'.
> The failure modes from that distribution are invisible to a
> benchmark whose questions were written by researchers."

---

## Demo Flow Summary (5 minutes total)

| Time | Action                                                  | Marks covered |
| ---- | ------------------------------------------------------- | ------------- |
| 0:00 | Show chat working, ask one question                     | Context       |
| 0:45 | Click Traces tab — show the trace just created          | 20 marks      |
| 1:30 | Run the seeded sample script in terminal                | 20 marks      |
| 2:15 | Run replay_trace.py — show original vs replayed         | 20 marks      |
| 3:00 | Show notes.md — read 2-3 observation sentences          | 25 marks      |
| 3:30 | Show taxonomy.md — walk the table, open one trace in UI | 30 marks      |
| 4:15 | Show git log — read prediction commit                   | 15 marks      |
| 4:45 | Read 3 benchmark sentences                              | 10 marks      |

---

## Things NOT to Say

| Don't say                                           | Say instead                                                    |
| --------------------------------------------------- | -------------------------------------------------------------- |
| "retrieval issue"                                   | The specific chunk ID that was missing or wrong                |
| "hallucination"                                     | "The model cited a chunk ID that was not in the retrieved set" |
| "this should improve things"                        | "This specific change will drop mode X from N% to under Y%"    |
| "I fixed it during analysis"                        | Never say this — zero fixes during open-coding                 |
| "I picked these 20 because they looked interesting" | "I used random.seed(35) — here's the code"                     |

---

## Files to Have Open Before Demo Starts

- `evaluation/notes.md` — 20 observation sentences
- `evaluation/taxonomy.md` — failure mode table
- `src/generation/answer.py` — to show `_write_trace()`
- Terminal with API running (port 8000)
- Browser at `http://localhost:4200`
