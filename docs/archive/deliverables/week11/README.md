# Week 11 - Module 6: Production Observability, Cost & the Failure-to-Test Loop

> **Goal:** Make your app watch itself -- find any bad answer, control its cost, and stop mistakes from coming back.

---

## Table of Contents

1. [Observability & Per-Request Logging](#1-observability--per-request-logging)
2. [Traces & Spans](#2-traces--spans)
3. [LangSmith / Phoenix / OpenTelemetry](#3-langsmith--phoenix--opentelemetry)
4. [The Support Drill](#4-the-support-drill)
5. [Cost Per Query](#5-cost-per-query)
6. [Prompt Caching](#6-prompt-caching)
7. [Semantic Caching](#7-semantic-caching)
8. [Model Routing (LiteLLM)](#8-model-routing-litellm)
9. [Fallbacks & Rate Limits](#9-fallbacks--rate-limits)
10. [The Data Flywheel](#10-the-data-flywheel)
11. [The 10x Plan (Scaling)](#11-the-10x-plan-scaling)
12. [Fine-Tuning (Last Resort)](#12-fine-tuning-last-resort)
13. [The Failure-to-Test Loop](#13-the-failure-to-test-loop)

---

## 1. Observability & Per-Request Logging

### What it is
Observability is the ability to understand what your app did, when it did it, and why -- by looking at the data it produces. Per-request logging means recording key details for every single LLM call: the question asked, the answer given, which documents were retrieved, how long it took, and how much it cost.

### Why we need it / Problem without it
Without logging, when a customer complains "it gave me a wrong answer yesterday," you have no way to find that answer, understand why it happened, or prove it was fixed. If it isn't logged, it effectively didn't happen -- you are flying blind.

**Problems without it:**
- Cannot reproduce or investigate bugs
- Cannot prove your app is working correctly
- Cannot track down which user got a bad answer
- Cannot measure performance or cost trends over time

### What to log per request (minimum)
| Field | Why |
|-------|-----|
| `request_id` (UUID) | Unique ID to find this exact request later |
| `timestamp` | When it happened |
| `user_query` | What the user asked |
| `retrieved_docs` | What context was fetched from the vector store |
| `llm_response` | What the model answered |
| `latency_ms` | Time each step took |
| `tokens_in / tokens_out` | To calculate cost |
| `model_used` | Which model answered |
| `cost_usd` | Actual dollar cost of this request |

### Alternatives
| Option | Description |
|--------|-------------|
| Print statements | Simple but not searchable, disappear on restart |
| Python `logging` module | Better, but no structure or query interface |
| **Structured JSON logs** (recommended) | Searchable, filterable, works with every log tool |
| Dedicated platforms (LangSmith, Phoenix) | Full UI + search + replay -- best for LLM apps |

**Best choice:** Structured JSON logs written to a file or database, plus a platform like LangSmith or Phoenix for UI-based search.

### Use cases
- Any app in production where users can get bad answers
- Compliance-sensitive apps where you must prove what the system said
- Multi-step RAG pipelines where you need to know which step failed

### Negatives
- Logs can grow very large and become expensive to store
- Logging raw user queries may raise privacy concerns -- must be handled carefully
- Over-logging slows down your app if done synchronously on the main thread

---

## 2. Traces & Spans

### What it is
A **trace** is the full record of one user request from start to finish. A **span** is one step inside that trace (e.g., "retrieve docs" is one span, "call LLM" is another span). Together they show you a timeline of exactly what happened, how long each part took, and where time or money was spent.

Think of it like a receipt that breaks down every item -- not just the total at the bottom.

### Why we need it / Problem without it
Without traces and spans, you only see one lump number: "this request took 4 seconds." You cannot tell if the delay was in retrieval, in the LLM call, or in post-processing. You cannot optimize what you cannot see at the step level.

### What problem it solves
- Pinpoints which step is slow or expensive
- Lets you replay a specific user's request for debugging
- Shows nested calls (e.g., an agent calling sub-agents) as a tree

### Alternatives
| Option | Description |
|--------|-------------|
| Manual timers (`time.time()`) | Works but tedious and not structured |
| Python profilers | Good for CPU but not for async/LLM calls |
| **OpenTelemetry spans** (recommended) | Industry standard, works with all backends |

**Best choice:** OpenTelemetry -- it is vendor-neutral and any monitoring platform can ingest it.

### Use cases
- Multi-step RAG pipelines with retrieval + reranking + LLM
- Agent systems where one request triggers many sub-calls
- Any scenario where you need to audit "what did the system do for this user"

### Negatives
- Adds code complexity -- every function needs to be wrapped in a span
- Trace storage can be expensive at scale (many requests = many spans)
- Distributed tracing across microservices adds more setup effort

---

## 3. LangSmith / Phoenix / OpenTelemetry

### What they are

| Tool | What it is |
|------|-----------|
| **LangSmith** | LangChain's hosted tracing platform -- records every LLM call, retrieval, and chain step with a UI to search, replay, and evaluate |
| **Arize Phoenix** | Open-source observability for LLMs -- similar to LangSmith but self-hostable, strong on evaluation |
| **OpenTelemetry** | An open standard (not a product) for emitting traces/metrics/logs -- works with dozens of backends |

### Why we need them / Problem without them
Without these tools, debugging an LLM app means reading raw log files or print statements -- extremely slow and painful. These tools give you a searchable UI, step-by-step timelines, and the ability to replay any past request.

### What problem they solve
- Find exactly which request gave a bad answer
- See cost and latency broken down by step
- Compare different prompt versions side by side
- Evaluate answer quality at scale

### Which is best?
- **Use LangSmith** if you are already using LangChain -- zero-effort integration
- **Use Phoenix** if you want open-source and self-hosted -- more privacy, no vendor lock-in
- **Use OpenTelemetry** as the underlying standard regardless -- then choose your display backend

### Use cases
- Any production LLM app
- Teams that need to share traces with non-engineers (support, QA)
- Apps where you need to prove an answer was correct for compliance

### Negatives
- **LangSmith** is a paid SaaS -- your user queries are sent to a third party
- **Phoenix** requires you to host and maintain the server yourself
- **OpenTelemetry** alone has no UI -- you still need a backend (Jaeger, Honeycomb, etc.)
- All of them add latency overhead to each request (small but nonzero)

---

## 4. The Support Drill

### What it is
A practical skill: given a vague complaint from a customer ("the answer about dairy-free swaps was wrong"), you must find the exact log entry, understand why the bad answer was given, and fix it. This is the real-world use of your logging setup.

### Why we need it / Problem without it
In production, complaints are always vague. Without structured logs and trace IDs, finding the bad answer among thousands is nearly impossible. The support drill trains you to do this confidently.

### What problem it solves
- Bridges the gap between "the app has a bug" and "here is the exact log, the exact retrieved doc, and the exact model output that caused it"
- Forces you to design logs that are actually searchable (not just noise)

### How it works
1. A bad answer is planted in the system (e.g., wrong information given to a specific type of query)
2. You receive only a vague complaint (no request ID, no timestamp)
3. You must search your logs to find the entry, trace it, and confirm the root cause

### Use cases
- Every production LLM app with real users
- Customer-facing chatbots where answer quality matters
- Regulated industries (finance, health, legal) where you must prove what was said

### Negatives
- Only works if your logs are rich and queryable -- useless if you only logged errors
- Time-consuming without good tooling (LangSmith search vs. grepping raw files)
- Privacy risk: logs contain user conversations -- must be secured carefully

---

## 5. Cost Per Query

### What it is
The dollar cost of one user request from end to end -- including retrieval (vector DB calls), LLM token usage (input + output), and any reranker calls. Calculated as:

```
cost = (input_tokens * price_per_input_token) + (output_tokens * price_per_output_token)
```

### Why we need it / Problem without it
LLM costs scale directly with usage. Without measuring cost per request, you have no idea what your app costs to run, and your bill can surprise you enormously as traffic grows. You cannot cut a cost you haven't measured.

**Example:** If one request costs $0.01 and you have 100,000 requests/month, that is $1,000/month. A 50% reduction saves $500/month.

### What problem it solves
- Makes cost visible and actionable
- Lets you set per-user or per-session budgets
- Identifies which request types are expensive (long prompts, many retrieved docs)

### Alternatives
| Option | Description |
|--------|-------------|
| Cloud provider billing dashboard | Shows total cost but not per-request breakdown |
| **Token counting + price lookup** (recommended) | Calculate at runtime, log it with each request |
| LangSmith / Phoenix | Shows cost per trace automatically |

### Use cases
- Any production app calling paid LLM APIs
- B2B apps where cost must be passed on to customers
- Apps with wildly varying query types (some cheap, some expensive)

### Negatives
- Token prices change -- your cost calculations can become stale
- Indirect costs (vector DB, compute) are harder to attribute per-request
- Teams sometimes obsess over cost optimization before measuring actual user value

---

## 6. Prompt Caching

### What it is
Storing the LLM's computed internal state for a long, repeated prefix (like your system prompt or knowledge base text), so future requests that share that prefix do not re-process it from scratch. The model provider charges much less for "cache hits."

**Example:** If your system prompt is 2,000 tokens and every request sends it, caching saves 2,000 * price_per_token on every repeated call.

### Why we need it / Problem without it
Without caching, every request pays full price for tokens that never change (system prompt, static context). This is pure waste -- you are paying to process the same text thousands of times.

### What problem it solves
- Reduces cost on requests with large, stable prompts
- Reduces latency because the model skips re-processing cached text

### Alternatives
| Option | Description |
|--------|-------------|
| Shorten the system prompt | Works but loses quality |
| **Prompt caching (Anthropic / OpenAI)** (recommended) | Native API feature -- near-zero effort |
| Semantic caching (see below) | Different technique, different use case |

### Use cases
- Apps with long system prompts that rarely change
- RAG apps that inject a fixed knowledge base into every prompt
- Multi-turn conversations where the conversation history grows but stabilizes

### Negatives
- Only works if the cached prefix is identical across requests -- any variation breaks the cache
- Cache TTL is short (minutes to hours) -- not useful for rarely-repeated queries
- You must structure your prompts carefully: stable parts first, dynamic parts last
- Only available on specific model providers (Anthropic, OpenAI) -- not all models support it

---

## 7. Semantic Caching

### What it is
Instead of caching the exact prompt string, semantic caching stores previous answers indexed by their meaning (embedding). When a new question arrives, it checks if a semantically similar question was already answered, and returns the cached answer if the similarity is above a threshold.

**Example:** "What is your refund policy?" and "How do I get a refund?" are different strings but mean the same thing -- semantic caching returns the same answer without calling the LLM.

### Why we need it / Problem without it
Exact-match caching only helps for identical queries. In real life, users phrase the same question dozens of different ways. Without semantic caching, every rephrasing hits the LLM even though the answer is already known.

### What problem it solves
- Dramatically reduces LLM calls for FAQ-style questions
- Fastest possible response time (no LLM call at all)
- Saves money on repetitive queries

### Alternatives
| Option | Description |
|--------|-------------|
| Exact-match cache (Redis key-value) | Misses paraphrases |
| **Semantic cache (GPTCache, LangChain cache)** (recommended) | Catches paraphrases -- best for FAQ apps |
| Prompt caching | Different -- reduces cost within a call, not across calls |

**Best:** GPTCache or a custom vector-store-backed cache.

### Use cases
- FAQ chatbots where the same questions repeat constantly
- Customer support bots with a finite set of common intents
- Apps with high traffic and repetitive queries

### Negatives
- Similarity threshold is tricky: too high = cache never hits; too low = wrong answer returned for unrelated questions
- Cache invalidation is hard -- if the answer changes (e.g., new refund policy), you must detect and evict stale entries
- Adds latency for the similarity lookup (small, but nonzero)
- Not suitable for queries that need up-to-date or personalized answers

---

## 8. Model Routing (LiteLLM)

### What it is
Automatically sending each request to the best (or cheapest) model for that specific task, rather than always using the same model. LiteLLM is a proxy library that presents a unified API across OpenAI, Anthropic, Google, Azure, and many others, and can route, load-balance, and fall back between them.

**Example:** Simple yes/no questions go to a cheap, fast model (e.g., Haiku). Complex legal analysis goes to a powerful, expensive model (e.g., Opus).

### Why we need it / Problem without it
Using your most powerful (and expensive) model for every request is wasteful. A question like "what are your business hours?" does not need GPT-4 or Claude Opus. Without routing, you overpay for easy questions.

### What problem it solves
- Cuts cost by matching model capability to task complexity
- Provides a single unified API so your code does not change when you switch models
- Enables fallbacks (if one provider is down, automatically try another)

### Alternatives
| Option | Description |
|--------|-------------|
| Hard-code one model | Simple but wasteful and fragile |
| Manual if/else routing in code | Works but becomes a mess to maintain |
| **LiteLLM** (recommended) | Single API, routing rules, fallbacks, cost tracking |
| OpenRouter | Similar SaaS alternative to LiteLLM |

### Use cases
- Production apps with mixed query types (simple vs. complex)
- Cost-sensitive apps where budget per request matters
- Apps that need resilience across multiple LLM providers

### Negatives
- Routing decisions are hard to get right -- what counts as a "simple" question?
- Adds a network hop (or library overhead) to every request
- Different models have different strengths, formats, and quirks -- output may vary
- LiteLLM is another dependency to maintain and keep updated

---

## 9. Fallbacks & Rate Limits

### What it is
**Fallbacks** are backup plans when your primary LLM call fails (timeout, provider outage, rate limit). Your app automatically retries with a different model or provider instead of crashing.

**Rate limits** are the maximum number of requests a provider allows per minute/hour. Handling them means detecting 429 (too many requests) errors and responding gracefully -- queuing, retrying with backoff, or routing to a fallback.

### Why we need it / Problem without it
LLM APIs are not 100% reliable. Without fallbacks:
- One provider outage = your entire app is down
- A rate limit hit = users get an error message
- A single failed request = a bad user experience

### What problem it solves
- Keeps your app available even when one provider has issues
- Prevents cascading failures under traffic spikes
- Makes your app feel reliable to users even when the backend is struggling

### Alternatives
| Option | Description |
|--------|-------------|
| Retry with exponential backoff | Handles transient errors, not outages |
| **LiteLLM fallbacks + retry config** (recommended) | Handles both, with routing rules |
| Custom middleware | Full control but lots of code to write |

### Use cases
- Any production app where uptime matters
- Apps with unpredictable traffic spikes (marketing campaigns, viral moments)
- Multi-provider setups where you want cost or latency competition

### Negatives
- Fallback models may give different (sometimes worse) answers than your primary model
- Complex fallback chains are hard to test and reason about
- If your fallback also fails, you need a third level -- the chain can become deep
- Rate limit handling adds latency (backoff = waiting)

---

## 10. The Data Flywheel

### What it is
A self-reinforcing loop where real production data makes your app better over time:
1. Users interact with the app
2. You log every interaction (good and bad)
3. You identify bad answers (via user feedback, evals, or the support drill)
4. You use those bad examples to improve prompts, fine-tune, or add to your knowledge base
5. Better app gets more users, generating more data -- cycle repeats

### Why we need it / Problem without it
Without a data flywheel, your app is static. You launch it, it works at some level, and it never improves. Over time, it falls behind as user needs evolve and edge cases accumulate. With the flywheel, the app gets better on its own as it runs.

### What problem it solves
- Turns real failures into training/improvement signals
- Creates a compounding advantage -- the longer you run, the better your data
- Reduces the need for manual expert labeling (real failures are the best training data)

### Use cases
- Any production AI app with a long operational life
- Apps where quality must improve continuously (support, healthcare, legal)
- Consumer apps that accumulate large volumes of user interactions

### Negatives
- Requires good logging from day one -- cannot retroactively build the flywheel
- Bad data going in = bad improvements coming out (garbage in, garbage out)
- Can reinforce existing biases if failures are not carefully curated
- Privacy concerns: using user conversations as training data requires consent and careful handling

---

## 11. The 10x Plan (Scaling)

### What it is
A structured thought exercise (and plan) for what happens when your app's traffic grows 10 times overnight. You identify which component breaks first (the bottleneck), and you prepare a plan to handle it before it becomes a crisis.

**Common bottlenecks at 10x traffic:**
- Vector database slows down under concurrent queries
- LLM API rate limits are hit constantly
- Your logging database cannot handle the write volume
- Your single server runs out of memory

### Why we need it / Problem without it
Most apps are built for current traffic. A sudden 10x surge (from a viral post, a product launch, or a new enterprise customer) will expose every assumption you made. Without a plan, your app goes down exactly when it matters most.

### What problem it solves
- Forces you to think about scalability before the emergency
- Identifies the single most likely failure point (so you fix that, not everything)
- Gives you a prioritized action list: what to fix first, what to defer

### Alternatives
| Option | Description |
|--------|-------------|
| Hope nothing breaks | Common but risky |
| Load testing (Locust, k6) | Actually test with simulated traffic before it hits |
| **10x planning + load testing** (recommended) | Think it through, then verify with tests |

### Use cases
- Any app approaching production launch
- Apps expecting marketing pushes or seasonal spikes
- B2B apps adding a large enterprise customer

### Negatives
- Hard to predict which component breaks -- every system is different
- Planning is only useful if the plan is actually implemented
- 10x is arbitrary -- some apps get 100x spikes; others never reach 2x

---

## 12. Fine-Tuning (Last Resort)

### What it is
Training a model on your own dataset of question-answer pairs so it learns your specific style, vocabulary, or domain knowledge, producing a customized version of the base model. Called "last resort" because it is expensive, slow, and often unnecessary if prompt engineering and RAG are done well.

### Why we need it / Problem without it
When a base model consistently fails on your domain-specific tasks despite good prompts and retrieval -- e.g., it never formats answers the way you need, or it makes domain-specific errors RAG cannot fix -- fine-tuning can close that gap.

**But without a clear need:** fine-tuning is expensive engineering work that often produces only marginal improvements over good prompting.

### What problem it solves
- Teaches the model your domain's specific vocabulary, tone, or format
- Can reduce prompt length (the model "knows" things it used to need reminded of)
- Improves consistency on narrow, repetitive tasks

### Alternatives (try these first)
| Option | Description | Try first? |
|--------|-------------|------------|
| Better prompts | Usually closes 80% of gaps | Yes |
| Few-shot examples in prompt | Shows model the format you want | Yes |
| RAG with better retrieval | Gets the right context into the prompt | Yes |
| **Fine-tuning** | Custom model for your domain | Only after the above fail |

### Use cases
- Highly specialized domains where base models consistently fail (rare medical terminology, proprietary legal frameworks)
- Apps needing a very specific output format the model cannot reliably follow from prompts alone
- Cost optimization: a fine-tuned small model can replace a large expensive model for narrow tasks

### Negatives
- Expensive: requires labeled training data (time-consuming to create) and GPU compute to train
- Can overfit: model becomes worse at general tasks while getting better at your narrow task
- Maintenance burden: when the base model updates, you must re-fine-tune
- Not a fix for bad retrieval -- if the right information is not in context, fine-tuning will not help
- Risk of "hallucination injection": if your training data contains errors, the model learns them

---

## 13. The Failure-to-Test Loop

### What it is
Every real production failure (a wrong answer, a crash, a bad retrieval) is immediately converted into a permanent automated test case. The next time the system is changed, the test runs and confirms the failure cannot come back silently.

**The loop:**
1. Production failure is discovered (via logging, user complaint, support drill)
2. Root cause is identified (wrong doc retrieved, bad prompt, model error)
3. A test is written that captures exactly this case as an assertion
4. The test is added to the test suite -- it now runs on every future code change
5. If the bug ever comes back, the test catches it before it reaches users

### Why we need it / Problem without it
Without this loop, the same bugs come back. A fix is made, time passes, someone changes a prompt or a retrieval strategy, and the old failure quietly returns. Nobody notices until users complain again.

### What problem it solves
- Creates a growing safety net from real failures (not hypothetical ones)
- Makes the app self-improving -- every incident leaves the system stronger
- Provides concrete evidence that a bug was fixed (the test passes where it previously failed)

### Alternatives
| Option | Description |
|--------|-------------|
| Manual regression checks | Easy to forget, does not scale |
| Unit tests written upfront | Good but misses real-world failure modes |
| **Failure-to-test loop** (recommended) | Best of both -- real cases, automated forever |

### Use cases
- Any production LLM app where quality must be maintained over time
- Apps with frequent prompt or retrieval changes where regressions are a risk
- Teams that want to move fast without breaking things

### Negatives
- Requires discipline: every failure must actually be turned into a test (easy to skip under pressure)
- LLM test assertions can be flaky (model output varies slightly each run -- need fuzzy matching or LLM-as-judge)
- Test suite grows large over time and can become slow to run
- Not all failures are easy to reproduce deterministically in a test environment

---

## Summary Table

| Concept | Core Purpose | Use When | Biggest Risk |
|---------|-------------|----------|--------------|
| Per-request logging | Find any past answer | Always -- from day one | Privacy / storage cost |
| Traces & spans | See step-by-step timeline | Multi-step pipelines | Code complexity |
| LangSmith/Phoenix | UI for traces | Team needs searchable logs | Vendor lock-in / cost |
| Support drill | Find bad answers fast | Post-launch debugging | Only works with good logs |
| Cost per query | Control spending | Any paid API app | Indirect costs are hard |
| Prompt caching | Save money on stable prompts | Long, repeated system prompts | Prefix must be identical |
| Semantic caching | Skip LLM for repeated questions | FAQ-style apps | Wrong threshold = wrong answers |
| Model routing | Right model for right task | Mixed complexity workloads | Output inconsistency |
| Fallbacks & rate limits | Stay online under failures | Production apps | Complex to test |
| Data flywheel | Continuous improvement | Long-lived production apps | Bad data = bad improvements |
| 10x plan | Survive traffic spikes | Pre-launch, pre-growth | Hard to predict the bottleneck |
| Fine-tuning | Domain-specific models | Narrow tasks, last resort | Expensive, overfitting |
| Failure-to-test loop | Prevent regressions | Always | Test flakiness with LLMs |

---

## Week 11 Deliverable Checklist

- [ ] Per-request logging added (question, retrieved docs, answer, latency, cost, request ID)
- [ ] Support drill completed: found the planted bad answer from a vague complaint
- [ ] Cost per request measured before and after optimization
- [ ] At least one cost improvement made (caching, model routing, or prompt shortening)
- [ ] At least one real production failure converted into a permanent automated test
