# At 10x ticket volume, what breaks first?

**A rate limit breaks first, the Groq tokens-per-minute cap: 8,000 TPM allows about 6.5 requests/min (8,000 / 1,232 avg tokens per request), and 10x of a modest 5 requests/min needs about 62,000 TPM, 7.7x over.**

Numbers (limits read from live `x-ratelimit-*` response headers on this key; averages from the `traces` table):

| Constraint | Limit / value | At 10x (50 req/min, assumed baseline 5/min) | Verdict |
|---|---|---|---|
| Tokens per minute | 8,000 | 61,600 needed | breaks first (7.7x over) |
| Requests per day | 1,000 | 72,000/day; cap hit in 20 min | breaks second |
| Cost | $0.00028 / request | about $20/day | not the problem |
| Latency | 34 ms retrieval + 1.66 s generation | unchanged until limited | not the problem; 429 backoff then adds 10 to 60 s |

Already visible today: the peak observed was 10 requests in one minute (about 12,300 tokens), which exceeds 8,000 TPM,
and `llm_client.py` handles it only by sleeping on 429 (4 attempts, 10 to 60 s waits).

Caveats: the 5 requests/min baseline is an assumption (there is no production traffic yet); the limits shown are this
key's tier and will differ on a paid tier. SQLite WAL handles the trace writes at this volume, so the old
`traces.jsonl` concurrent-append risk is no longer the bottleneck (the JSONL dual-write remains until the API and
replay scripts are moved to SQLite).
