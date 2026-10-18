# Cost per query by stage

Source: `python scripts/cost_analysis.py --prompt-version v2` (26 LLM-calling requests from the GREEN eval run,
model `openai/gpt-oss-120b`, avg 1003 input and 217 output tokens).

| Stage | Cost per query (USD) | Avg latency | Notes |
|---|---|---|---|
| Retrieval (ChromaDB + BM25 + local embeddings) | 0.00000000 | 33.8 ms | runs locally, no API call |
| Generation (LLM tokens) | **0.00028044** | 1661 ms | $0.15 / 1M input, $0.60 / 1M output |
| Tools | 0.00000000 | n/a | this pipeline calls none (the agent path does) |
| **Total** | **0.00028044** | | median 0.00025770, p95 0.00043815 |

About $0.28 per 1,000 queries and $28 per 100,000.

Generation is 100% of the API cost, so any saving has to come from generation tokens: fewer retrieved chunks
(top_k 3 gives ~1,000 input tokens), a shorter system prompt, prompt caching of the fixed prompt prefix, a semantic
cache for repeated questions, or routing easy questions to `gpt-oss-20b` ($0.075 / $0.30 per 1M).

Caveats: prices in `src/generation/cost.py` are list prices I entered from memory and must be verified against the
provider page. The measured 26 requests are eval questions, not production traffic. No saving has been implemented or
measured yet, so there is no before/after number; the brief asks for one improvement, which is still open.
