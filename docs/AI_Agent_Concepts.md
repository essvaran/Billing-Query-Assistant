# AI Agent Architecture — Concept Reference

Ten foundational concepts for building autonomous LLM systems, from the loop that keeps agents alive to the memory that makes them useful across sessions.

---

## Table of Contents

1. [The Agent Loop](#1-the-agent-loop)
2. [ReAct (Reasoning + Acting)](#2-react-reasoning--acting)
3. [Tool Design](#3-tool-design)
4. [Stop Conditions & Budgets](#4-stop-conditions--budgets)
5. [Workflows vs. Agents](#5-workflows-vs-agents)
6. [Agent vs. Workflow Race](#6-agent-vs-workflow-race)
7. [Agent Memory: Short & Long Term](#7-agent-memory-short--long-term)
8. [Summarisation & Vector Memory](#8-summarisation--vector-memory)
9. [mem0](#9-mem0)
10. [LangChain & LangGraph](#10-langchain--langgraph)

---

## 1. The Agent Loop

### What it is

The agent loop is the fundamental execution cycle that every autonomous AI agent runs. It is what separates a single LLM call from an agent: the ability to **iterate** — observe, reason, act, and repeat — until the task is complete.

### How it works

Every iteration of the loop follows the same four steps:

```
Observe → Reason → Act → Update → (repeat)
```

| Step | What happens |
|------|-------------|
| **Observe** | Read the current state: messages, previous tool results, system context |
| **Reason** | The LLM decides what to do next given everything it can see |
| **Act** | Execute a tool call, generate an output, or signal completion |
| **Update** | Append the tool result back into state so the next iteration starts informed |

The loop checks a **stop condition** on every iteration. Without one, it runs forever.

### Minimal implementation

```python
def run_agent(query: str) -> str:
    state = {"messages": [{"role": "user", "content": query}]}

    while True:
        response = llm.complete(state["messages"])  # OBSERVE + REASON

        if response.stop_reason == "end_turn":
            return response.text                    # model chose to stop

        tool_result = execute(response.tool_call)   # ACT
        state["messages"].append(tool_result)       # UPDATE
        # loop restarts → OBSERVE again
```

### Concrete example

A billing support agent receives: *"What is my outstanding balance?"*

- **Iteration 1:** Observes the user query → reasons it needs the account balance → calls `get_account_balance(user_id=42)` → observes `{balance: 230.00, overdue: true}` → updates state
- **Iteration 2:** Observes full context including balance → reasons it has enough to answer → produces a response → signals `end_turn`

> **Key insight:** The loop is fundamentally about state management. Everything the agent learns — tool results, intermediate reasoning — must be written back into state before the next iteration, or the model starts the next step blind.

---

## 2. ReAct (Reasoning + Acting)

### What it is

**ReAct** stands for *Reasoning + Acting*. Introduced by Yao et al. (2022), it is a prompting strategy where the model is instructed to interleave explicit reasoning steps with tool calls, rather than jumping straight to an action.

The pattern alternates between three labeled steps:

- **Thought:** The model writes out its current understanding and plan
- **Action:** The model calls a tool
- **Observation:** The result of the tool call is appended

### Why it matters

Without explicit reasoning, models often select wrong tools or hallucinate results. The Thought step forces the model to articulate *why* it is taking an action before committing to it — catching wrong turns before they happen.

### The pattern in practice

```
User: "My invoice INV-2026-08 shows a late fee but I paid on time."

Thought: The user is disputing a late fee on invoice INV-2026-08.
         I need to check the payment records and the invoice due date.

Action: get_invoice(invoice_id="INV-2026-08")

Observation: {id: "INV-2026-08", due_date: "2026-08-01",
              late_fee: 12.50, status: "overdue"}

Thought: The invoice was due 2026-08-01. Now I need to check
         whether a payment was recorded on or before that date.

Action: get_payments(user_id=42, before="2026-08-02")

Observation: [{paid_on: "2026-07-31", amount: 450.00, ref: "PAY-7731"}]

Thought: Payment PAY-7731 was made on 2026-07-31, one day before
         the due date. The late fee is incorrect. I should waive it.

Action: waive_late_fee(invoice_id="INV-2026-08", reason="payment_on_time")

Observation: {success: true, fee_waived: 12.50}

Thought: The fee has been waived. I can now confirm this to the user.

Final Answer: "I've confirmed your payment of $450.00 was received on
              July 31st — one day before the due date. The $12.50 late
              fee on INV-2026-08 has been waived."
```

### Implementation with Claude

```python
SYSTEM = """You are a billing support agent.
For every step, write:
  Thought: <your reasoning>
  Action: <tool name and arguments>
After receiving an Observation, continue until you can write a Final Answer."""

messages = [{"role": "user", "content": user_query}]

while True:
    response = llm.complete(messages, system=SYSTEM, tools=tools)

    if "Final Answer:" in response.text:
        return response.text.split("Final Answer:")[1].strip()

    # Parse and execute the Action
    tool_result = parse_and_run(response.text)
    messages.append({"role": "assistant", "content": response.text})
    messages.append({"role": "user", "content": f"Observation: {tool_result}"})
```

> **Key insight:** Most modern LLM frameworks (LangGraph, Claude's tool use API) implement ReAct implicitly. The model reasons internally before producing a tool call. The explicit Thought/Action/Observation format is most valuable during development and debugging, where you need to see *why* the agent made a choice.

---

## 3. Tool Design

### What it is

Tools are the agent's only interface to the world — the sole mechanism for reading data, writing state, and triggering side effects. A poorly designed tool is a reliability failure: vague descriptions cause wrong tool selection; missing type information causes malformed calls; unhelpful errors make self-correction impossible.

### The four rules

**1. Atomic — one tool, one concern**

A `get_invoice` tool should not also send emails. A `search_knowledge_base` tool should not also log to analytics. When tools do multiple things, the model cannot express intent precisely, and failures become ambiguous.

**2. Typed and described — every parameter has a description**

The tool's JSON schema is the only documentation the model ever sees. Every parameter, return field, and error case must be described as if the model's understanding of your system depends on it — because it does.

**3. Structured output — return dicts, not prose**

The model parses structured output far more reliably than natural language. Return `{"balance": 230.00, "currency": "USD", "overdue": true}` rather than `"Your balance is $230.00 and it is overdue."`.

**4. Actionable errors — explain what went wrong and how to fix it**

```python
# Bad error — the model cannot self-correct
raise Exception("Not found")

# Good error — the model knows what to try next
raise InvoiceNotFoundError(
    "Invoice INV-999 not found. "
    "Valid invoice IDs for user #42 range from INV-001 to INV-847."
)
```

### Bad vs. good tool definition

```python
# ❌ Avoid — vague, multi-purpose, no error contract
def do_billing_stuff(query: str) -> str:
    """Does stuff with billing."""
    ...


# ✅ Prefer — narrow scope, typed, descriptive, structured
def get_invoice(
    user_id: int,        # the account owner's numeric ID
    invoice_id: str,     # format: "INV-XXXXXX" (e.g., "INV-002847")
) -> dict:
    """Retrieve a single invoice by its ID.

    Returns:
        {
            id: str,
            amount_usd: float,
            due_date: str,        # ISO 8601 format
            status: "open" | "paid" | "overdue",
            line_items: list[{description: str, amount_usd: float}]
        }

    Raises:
        InvoiceNotFoundError: if the invoice ID does not exist
        PermissionError: if user_id does not own the invoice
    """
    ...
```

### Additional rules

| Rule | Reason |
|------|--------|
| Idempotent read tools | The model may call read tools speculatively; they must be safe to call multiple times |
| Name reflects action | `send_email` is clear; `process` is not |
| Writes in named tools | `create_refund`, `update_invoice` — never hidden inside a "get" tool |
| Bound parameter ranges | Include valid ranges in descriptions: `"page: int, 1-based, max 100"` |

---

## 4. Stop Conditions & Budgets

### What it is

An agent without explicit stopping logic is a runaway process. Two failure modes occur in production:

1. The model never signals completion (an ambiguous task or a bug keeps it looping)
2. The model loops correctly but exhausts a resource — tokens, time, money — before finishing

Stop conditions and budgets are the kill switches that keep agents predictable and cost-controlled.

### The three budgets

#### Iteration budget
A hard cap on the number of loop iterations. The simplest guard. Set to 2-3x the expected number of steps for a task.

```python
MAX_ITERATIONS = 15
for step in range(MAX_ITERATIONS):
    ...
raise BudgetError("Exceeded maximum iterations")
```

#### Token budget
A rolling count of input + output tokens consumed. Input tokens dominate as the context window grows with each tool result appended to state.

```python
tokens_used = 0
BUDGET = 80_000  # input + output tokens

while True:
    response = llm.complete(messages)
    tokens_used += response.usage.input_tokens + response.usage.output_tokens

    if tokens_used > BUDGET:
        raise BudgetError(f"Token budget exceeded: {tokens_used} > {BUDGET}")
    ...
```

#### Time budget
A wall-clock timeout. Essential when tool calls hit external APIs that may hang.

```python
import asyncio

async def run_with_timeout(coro, timeout_secs=30):
    try:
        return await asyncio.wait_for(coro, timeout=timeout_secs)
    except asyncio.TimeoutError:
        raise TimeoutError("Agent timed out")
```

### Full implementation

```python
from dataclasses import dataclass
import time

@dataclass
class AgentBudget:
    max_iterations: int = 15
    max_tokens: int = 80_000
    timeout_secs: float = 60.0

def run_agent(query: str, budget: AgentBudget) -> str:
    state = AgentState(messages=[{"role": "user", "content": query}])
    start = time.monotonic()

    for step in range(budget.max_iterations):

        if state.tokens_used >= budget.max_tokens:
            raise BudgetError("token budget exceeded")

        if time.monotonic() - start >= budget.timeout_secs:
            raise TimeoutError("agent timed out")

        response = llm.complete(state.messages)
        state.tokens_used += response.usage.total_tokens

        if response.stop_reason == "end_turn":
            return response.text         # model chose to stop

        result = execute_tool(response.tool_call)
        state.messages.append(result)

    raise BudgetError(f"exceeded {budget.max_iterations} iterations")
```

### Stop conditions vs. budgets

| | Stop condition | Budget |
|--|----------------|--------|
| **What triggers it** | Model signals completion | Resource threshold crossed |
| **Who defines it** | Model (or task schema) | Developer |
| **On trigger** | Return result | Raise error or return partial |

> **Graceful degradation:** Rather than raising on budget exhaustion, consider returning a partial answer with a note: *"I completed 3 of 5 steps before hitting the token limit. Here is what I found so far..."* This gives users something usable even when the agent cannot finish.

---

## 5. Workflows vs. Agents

### The core distinction

The most important architectural decision in any AI system is whether **control flow** is defined by a human or by the model at runtime.

- **Workflow:** You define the steps. The LLM executes each step, but the sequence is fixed.
- **Agent:** The LLM decides which tool to call next, and when to stop. The sequence emerges at runtime.

### Workflows

A workflow is a deterministic, human-authored graph of steps. Given the same input, it always follows the same path.

```python
# Workflow — steps defined by you, not the model
def handle_billing_query(query: str) -> str:
    intent = classify_intent(query)          # step 1: always runs
    docs = retrieve_relevant_docs(intent)    # step 2: always runs
    answer = generate_answer(query, docs)    # step 3: always runs
    return answer
```

**Characteristics:**
- Deterministic — same input, same execution path
- Fast — no reasoning overhead per routing decision
- Auditable — easy to trace what happened and why
- Brittle — fails on inputs that don't fit the expected shape
- Cheap — minimal LLM calls for orchestration

### Agents

An agent hands routing to the model. Given the same input, the model may take different paths.

```python
# Agent — model picks the path
def handle_billing_query(query: str) -> str:
    tools = [search_kb, get_invoice, get_payments, escalate, send_email]
    return run_agent(query, tools)  # model decides which tools to call and in what order
```

**Characteristics:**
- Non-deterministic — same input may produce different tool sequences
- Flexible — handles unexpected inputs and edge cases
- Harder to test exhaustively (exponential path space)
- More expensive — token cost for every routing decision
- Capable — can handle tasks whose shape you did not anticipate

### Comparison table

| Dimension | Workflow | Agent |
|-----------|----------|-------|
| Control flow defined by | Developer | LLM at runtime |
| Handles unexpected inputs | No | Yes |
| Deterministic | Yes | No |
| Debugging | Easy | Hard |
| Cost per task | Low | Higher |
| Latency | Low | Higher |
| Best for | Known-shape tasks | Open-ended tasks |

### The hybrid approach

The most pragmatic production pattern: start with a workflow. When it fails too often on edge cases, identify the specific decision points that require flexible reasoning, and replace only those steps with agent calls.

```python
def handle_billing_query(query: str) -> str:
    intent = classify_intent(query)              # workflow step

    if intent == "simple_lookup":
        return simple_lookup_workflow(query)     # fast, deterministic path
    else:
        return run_agent(query, all_tools)       # agent for complex/unknown cases
```

> **Rule of thumb:** Use a workflow when you know the steps. Use an agent when you do not. Use both when you know some steps but not all.

---

## 6. Agent vs. Workflow Race

### What the race is

The "race" describes the architectural competition that plays out for every automation task: a workflow ships first and is reliable for 80% of cases, while an agent-based approach handles 100% but costs more, is slower, and fails unpredictably. In practice, neither wins outright — the race resolves into a spectrum.

### Task entropy: the deciding variable

The key variable is **task entropy** — how variable are the inputs, and how unpredictable is the number of steps required?

```
Low entropy                                    High entropy
     |-------------------------------------------|
  Workflow                                     Agent

Examples:
  Weekly report       Classify email    Debug incident    Answer open question
  ETL pipeline        Route support     Research task     Negotiate refund
```

- **Low entropy** tasks have predictable inputs and a fixed number of steps. Classify an email, send a weekly summary, extract data from a known document format.
- **High entropy** tasks have open-ended inputs and a variable number of steps. Debug a production incident, answer an open billing question, handle an escalation with multiple possible resolutions.

### Decision matrix

| Task shape | Reliability requirement | Right choice |
|------------|------------------------|--------------|
| Known steps, predictable inputs | Any | Workflow |
| Known steps, variable content within steps | High | Workflow with LLM at each step |
| Unknown steps, open-ended inputs | Medium | Agent |
| Unknown steps, open-ended inputs | High | Workflow with agent fallback at specific decision points |
| High volume, simple | Any | Workflow (cost wins) |
| Low volume, complex | Low | Agent |

### The hidden cost of agents

Before defaulting to an agent architecture, calculate the routing tax:

```
Extra reasoning tokens per call:  ~500 tokens
Calls per day:                    10,000
Token price (input):              $0.25 / 1M tokens
Daily routing tax:                10,000 × 500 × $0.00000025 = $1.25/day

At 1M calls/day:                  $125/day = $45,625/year
```

For high-volume, simple tasks, this compounds quickly. Workflows make routing decisions for free.

### The practical resolution

```
1. Ship a workflow.
2. Monitor failure cases.
3. Find the step(s) where the workflow fails.
4. Replace those step(s) with agent calls.
5. The rest stays deterministic.
```

This "hybrid escalation" pattern is what most mature production systems converge on. Pure agents are powerful but expensive; pure workflows are cheap but brittle; the hybrid is where the tradeoffs balance.

---

## 7. Agent Memory: Short & Long Term

### What it is

A model with no memory is stateless — every query arrives cold, with no knowledge of previous interactions. For a support agent that should remember a user prefers PDF invoices, or a coding agent that should know a project's conventions, statelessness is a fundamental limitation.

Memory in AI agents maps onto four types that cognitive scientists identify in human memory.

### Short-term memory: the context window

Everything the model can see right now. Automatically managed by the framework — you do not need to explicitly "retrieve" it.

```
Context window (128k - 1M tokens)
├── System prompt & instructions
├── Current conversation messages
├── Tool results from this session
├── In-flight reasoning (ReAct thoughts)
└── Any injected documents or data
```

**Properties:**
- Fast — always available, no retrieval latency
- Limited — fills up; older content is pushed out
- Ephemeral — lost when the session ends
- Automatic — the framework manages it

### Long-term memory: external storage

Persists across sessions. Must be explicitly stored and retrieved. The agent "remembers" by searching this store and injecting relevant results into the context window before responding.

```
External store (unlimited)
├── Past conversation summaries
├── User preferences and facts
├── Domain knowledge and documents
├── Learned corrections and procedures
└── Episodic records (what happened, when)
```

**Properties:**
- Persistent — survives session restarts
- Unlimited — bounded only by storage cost
- Requires retrieval — the agent must explicitly search for relevant memory
- Requires management — stale or contradictory memories can mislead

### The four memory types (cognitive science mapping)

#### Working memory
Everything in the context window right now. No retrieval needed — it is simply what the model can see.

```python
# Working memory is implicit — it is state["messages"]
state = {
    "messages": [
        {"role": "user", "content": "What is my balance?"},
        {"role": "assistant", "content": "...", "tool_calls": [...]},
        {"role": "tool", "content": "{balance: 230.00}"},
    ]
}
```

#### Episodic memory
Records of past events. *"On 2026-08-01, user #42 disputed a late fee and was given a refund."*

```python
# Store an episode
memory.add_episode(
    user_id=42,
    event="late_fee_dispute",
    resolution="fee_waived",
    timestamp="2026-08-01"
)

# Retrieve relevant episodes
episodes = memory.search_episodes(user_id=42, query="late fee")
```

#### Semantic memory
Facts and knowledge. *"The late fee policy is 2% per month after a 5-day grace period."*

```python
# Usually stored in a vector DB and retrieved by semantic search
docs = vector_store.search("late fee policy", top_k=3)
```

#### Procedural memory
How to do things. *"To escalate a billing dispute: first check account age, then verify payment history, then call the escalation tool with a reason."*

```python
# Often encoded as few-shot examples in the system prompt
# or as detailed tool docstrings
SYSTEM = """
When handling a billing dispute:
1. call get_invoice() to retrieve the invoice details
2. call get_payments() to verify payment history
3. if payment was on time, call waive_late_fee()
4. if escalation is needed, call escalate_to_human()
"""
```

### Choosing what to remember

Not everything deserves long-term storage. A useful heuristic:

| Type of information | Store? | Why |
|---------------------|--------|-----|
| User's billing preference | Yes | Recurs across sessions |
| Current session messages | No | Already in working memory |
| One-time query content | No | Unlikely to recur |
| Correction to a mistake | Yes | Should not recur |
| User's account balance | No | Stale quickly; fetch fresh |
| Domain policy text | Yes | Stable; expensive to re-fetch |

> **Key insight:** Retrieving irrelevant memories can mislead the model more than having no memory at all. Be selective about what goes into long-term storage and how it is retrieved.

---

## 8. Summarisation & Vector Memory

### The context overflow problem

As an agent accumulates tool results over a long session, the context window fills. Older content is pushed out in "sliding window" implementations, or the call fails entirely with a context-length error. Two complementary strategies handle this:

1. **Summarisation** — compress old content to free space
2. **Vector memory** — retrieve only what is relevant, rather than loading everything

### Summarisation strategies

#### Rolling summary
Each time the context nears its limit, summarise the oldest N messages into a paragraph and replace them.

```python
def compress_context(messages: list, threshold: int = 0.8) -> list:
    """Replace oldest messages with a summary when context is 80% full."""
    token_count = count_tokens(messages)

    if token_count / MAX_TOKENS < threshold:
        return messages

    # Summarise the oldest half of messages
    old = messages[:len(messages) // 2]
    recent = messages[len(messages) // 2:]

    summary = llm.complete(
        [{"role": "user", "content":
          f"Summarise these conversation events in 3-5 sentences:\n{old}"}]
    ).text

    return [{"role": "system", "content": f"[Earlier context]: {summary}"}] + recent
```

**Trade-off:** Fast and cheap, but loses detail. Good when exact past wording does not matter.

#### Key-fact extraction
Instead of prose summaries, extract structured facts.

```python
facts = llm.complete(
    f"Extract key facts from this conversation as JSON:\n{old_messages}"
).json()
# → {"user_id": 42, "dispute": "INV-2026-08", "resolution": "fee_waived", "date": "2026-08-01"}
```

**Trade-off:** Compact and precise, but requires a schema and may miss nuance.

### Vector memory (RAG)

Rather than compressing all past content into the context, vector memory stores it externally and retrieves only the semantically relevant pieces when needed.

#### The RAG pipeline

```
1. EMBED    text → float vector (e.g., 1536 dimensions)
2. STORE    vector + metadata in a vector database
3. QUERY    embed the user's question → find nearest vectors
4. INJECT   top-k retrieved chunks → prepend to context
5. GENERATE LLM answers using retrieved context
```

#### Implementation

```python
import anthropic
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct

client = QdrantClient(url="http://localhost:6333")
anthropic_client = anthropic.Anthropic()

# 1. Embed a document chunk
def embed(text: str) -> list[float]:
    response = anthropic_client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1,
        messages=[{"role": "user", "content": text}]
    )
    # In practice: use a dedicated embedding model
    # e.g. openai.embeddings.create(model="text-embedding-3-small", input=text)
    ...

# 2. Store in vector DB
def store_chunk(text: str, doc_id: str, metadata: dict):
    vector = embed(text)
    client.upsert(
        collection_name="knowledge_base",
        points=[PointStruct(id=doc_id, vector=vector, payload={"text": text, **metadata})]
    )

# 3. Retrieve relevant chunks
def retrieve(query: str, top_k: int = 5) -> list[str]:
    q_vector = embed(query)
    hits = client.search(
        collection_name="knowledge_base",
        query_vector=q_vector,
        limit=top_k
    )
    return [hit.payload["text"] for hit in hits]

# 4. Use in RAG
def answer_with_rag(question: str) -> str:
    chunks = retrieve(question, top_k=5)
    context = "\n\n".join(chunks)

    return llm.complete(f"""Answer using only the context below.
Context:
{context}

Question: {question}""")
```

### Chunking strategy

How you split documents into chunks significantly affects retrieval quality.

| Parameter | Typical value | Trade-off |
|-----------|--------------|-----------|
| Chunk size | 256–512 tokens | Larger = more context per hit; smaller = more precise retrieval |
| Overlap | 50–100 tokens | Prevents key info from being split across chunks |
| Splitting | Sentence or paragraph boundaries | Never split mid-sentence |

### Hybrid retrieval

Combining vector (semantic) search with keyword (BM25) search consistently outperforms either alone.

```python
def hybrid_retrieve(query: str, top_k: int = 5) -> list[str]:
    vector_hits = vector_search(query, top_k=10)    # semantic similarity
    keyword_hits = bm25_search(query, top_k=10)    # exact term matching
    combined = reciprocal_rank_fusion(vector_hits, keyword_hits)
    return combined[:top_k]
```

> **Retrieval quality ceiling:** Generation quality is bounded by retrieval quality. If the right chunk is not returned, the model hallucinates regardless of its capability. Measure recall@k on real queries before shipping.

---

## 9. mem0

### What it is

**mem0** (pronounced "mem-zero") is an open-source Python library that provides a managed intelligent memory layer for AI agents. Rather than building your own embedding, storage, deduplication, and retrieval pipeline, mem0 wraps this into a simple three-method API: `add`, `search`, and `get_all`.

Its key differentiator is **smart memory management**: when you add a new memory, mem0 checks whether an existing memory should be updated rather than creating a duplicate. It uses an LLM internally to decide whether to create, update, or discard each incoming piece of information.

### Installation

```bash
pip install mem0ai
```

### Basic usage

```python
from mem0 import Memory

m = Memory()  # uses local vector store by default

# Store a fact about a user
m.add(
    "User prefers PDF invoices and monthly billing cycles",
    user_id="alice"
)

# Retrieve relevant memories at query time
results = m.search("how should I send the invoice?", user_id="alice")
for r in results:
    print(r["memory"])
# → "User prefers PDF invoices and monthly billing cycles"

# mem0 merges rather than duplicates
m.add("User switched to annual billing in September 2026", user_id="alice")
# The existing billing-cycle memory is updated, not duplicated

# Retrieve all memories for a user
all_memories = m.get_all(user_id="alice")
```

### Production configuration

```python
config = {
    "vector_store": {
        "provider": "qdrant",
        "config": {
            "url": "http://localhost:6333",
            "collection_name": "agent_memory"
        }
    },
    "embedder": {
        "provider": "openai",
        "config": {
            "model": "text-embedding-3-small"
        }
    },
    "llm": {
        # used for smart deduplication decisions
        "provider": "anthropic",
        "config": {
            "model": "claude-haiku-4-5-20251001"
        }
    }
}

m = Memory.from_config(config)
```

### Integrating mem0 into an agent

```python
def run_support_agent(user_id: str, query: str) -> str:
    # 1. Retrieve relevant memories before responding
    past_memories = m.search(query, user_id=user_id, limit=5)
    memory_context = "\n".join([r["memory"] for r in past_memories])

    # 2. Inject memories into the context
    messages = [
        {"role": "system", "content": f"Relevant user history:\n{memory_context}"},
        {"role": "user", "content": query}
    ]

    # 3. Run the agent
    response = run_agent(messages)

    # 4. Store new information learned during this session
    m.add(f"User asked: {query}. Resolved: {response}", user_id=user_id)

    return response
```

### Supported backends

| Component | Supported providers |
|-----------|-------------------|
| Vector store | Qdrant, Pinecone, Weaviate, ChromaDB, pgvector, Redis, FAISS |
| Embedder | OpenAI, Anthropic, HuggingFace, Ollama |
| LLM (for deduplication) | OpenAI, Anthropic, Groq, Together AI, Ollama |

### Key features

- **Automatic deduplication:** mem0 uses an LLM to decide whether to add, update, or discard each incoming fact — preventing memory bloat
- **Namespacing:** pass `user_id`, `agent_id`, and `session_id` to partition memory spaces without extra schema design
- **Memory history:** each memory stores its full update history, so you can see how it evolved
- **Graph memory:** optional knowledge graph layer for storing relationships between entities (e.g., user → company → contract)

---

## 10. LangChain & LangGraph

### LangChain

**LangChain** is a Python and JavaScript framework that provides composable building blocks for LLM applications: model clients, prompt templates, output parsers, retrievers, and "chains" — sequences of these components linked together.

It excels at **linear workflows** where data flows through a defined sequence of steps.

#### Core components

| Component | Role |
|-----------|------|
| `ChatModel` | Wraps an LLM API (Anthropic, OpenAI, etc.) |
| `PromptTemplate` | Parameterised prompt with variable injection |
| `OutputParser` | Parses raw LLM text into structured Python objects |
| `Retriever` | Fetches relevant documents from a vector store |
| `Chain` | Links components with `|` (pipe) operator |

#### A simple RAG chain

```python
from langchain_anthropic import ChatAnthropic
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough

llm = ChatAnthropic(model="claude-sonnet-4-6")

prompt = ChatPromptTemplate.from_template("""
Answer using only the context below. If the answer is not in the context, say so.

Context:
{context}

Question: {question}
""")

# Chain: retriever feeds context, question passes through
chain = (
    {"context": retriever, "question": RunnablePassthrough()}
    | prompt
    | llm
    | StrOutputParser()
)

answer = chain.invoke("What is the late fee policy?")
```

#### Streaming

```python
for chunk in chain.stream("What is the late fee policy?"):
    print(chunk, end="", flush=True)
```

---

### LangGraph

**LangGraph** is built on LangChain and raises the abstraction from chains to graphs. Where a chain is a line, a graph has **nodes** (arbitrary Python functions), **edges** (transitions), and — crucially — **cycles**. Cycles are what make LangGraph the right tool for agent loops: the same `think` and `act` nodes can be traversed multiple times per run.

#### Core concepts

| Concept | What it is |
|---------|-----------|
| `StateGraph` | The graph object. Holds nodes and edges. |
| `State` | A `TypedDict` passed between nodes. Every node reads and writes it. |
| `Node` | A Python function `(state) -> state`. Does the work. |
| `Edge` | A transition between nodes. Can be conditional. |
| `Checkpointer` | Persists state after every node for resumability. |
| `END` | A sentinel node that terminates the graph. |

#### A ReAct agent in LangGraph

```python
from langgraph.graph import StateGraph, END
from typing import TypedDict, Annotated
import operator

# State is shared across all nodes
class AgentState(TypedDict):
    messages: Annotated[list, operator.add]  # auto-appended on each node return

# Node 1: call the LLM
def think(state: AgentState) -> AgentState:
    """Call the LLM with tools bound. Returns a tool call or a final answer."""
    response = llm_with_tools.invoke(state["messages"])
    return {"messages": [response]}

# Node 2: execute the tool call
def act(state: AgentState) -> AgentState:
    """Execute the tool call in the last message."""
    last_message = state["messages"][-1]
    tool_call = last_message.tool_calls[0]
    result = tool_executor.invoke(tool_call)
    return {"messages": [result]}

# Conditional edge: should we keep looping or stop?
def should_continue(state: AgentState) -> str:
    last_message = state["messages"][-1]
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "act"     # model wants to call a tool -> continue loop
    return END           # model produced a final answer -> stop

# Build the graph
graph = StateGraph(AgentState)
graph.add_node("think", think)
graph.add_node("act", act)

graph.set_entry_point("think")
graph.add_conditional_edges("think", should_continue)
graph.add_edge("act", "think")   # the cycle: after acting, always think again

agent = graph.compile()

# Run it
result = agent.invoke({
    "messages": [{"role": "user", "content": "What is Alice's outstanding balance?"}]
})
print(result["messages"][-1].content)
```

#### Persistence (resumable agents)

```python
from langgraph.checkpoint.sqlite import SqliteSaver

# State is saved after every node
checkpointer = SqliteSaver.from_conn_string("agent_state.db")
agent = graph.compile(checkpointer=checkpointer)

config = {"configurable": {"thread_id": "session-42"}}

# First run
agent.invoke({"messages": [...]}, config=config)

# Resume from where it left off (e.g., after a crash)
agent.invoke({"messages": [...]}, config=config)
```

#### Human-in-the-loop

```python
# Pause before any tool execution for human approval
agent = graph.compile(
    checkpointer=checkpointer,
    interrupt_before=["act"]
)

# Agent runs, then stops before calling a tool
snapshot = agent.invoke(...)

# Human reviews and approves
human_approved = True
if human_approved:
    # Resume from the interruption point
    agent.invoke(None, config=config)
```

#### Subgraphs (multi-agent systems)

```python
# A specialist agent can itself be a node in an orchestrator graph
specialist_agent = specialist_graph.compile()

def run_specialist(state: OrchestratorState) -> OrchestratorState:
    result = specialist_agent.invoke({"task": state["subtask"]})
    return {"specialist_result": result["output"]}

orchestrator = StateGraph(OrchestratorState)
orchestrator.add_node("specialist", run_specialist)
```

### LangChain vs. LangGraph: when to use which

| Scenario | Use |
|----------|-----|
| Fixed pipeline: embed → retrieve → answer | LangChain chain |
| Multi-step agent with tool calls | LangGraph |
| State that persists across steps | LangGraph + checkpointer |
| Human approval before actions | LangGraph + `interrupt_before` |
| Streaming responses to a UI | Both support `.stream()` |
| Multiple agents collaborating | LangGraph subgraphs |
| Simple prompt + parse | LangChain (no graph needed) |

> **Bottom line:** Use LangChain for a fixed pipeline. Use LangGraph when your logic needs cycles, conditional branching, state that persists across steps, or human-in-the-loop checkpoints. For anything agent-shaped, LangGraph is the right abstraction.

---

## Quick Reference

| Concept | One-line summary |
|---------|-----------------|
| **Agent Loop** | Observe → Reason → Act → Update → repeat until stop condition |
| **ReAct** | Force the model to write a Thought before every Action |
| **Tool Design** | Atomic, typed, structured output, actionable errors |
| **Stop Conditions** | Iteration + token + time budgets on every agent run |
| **Workflows** | Human-defined steps; fast, deterministic, brittle |
| **Agents** | LLM-defined steps; flexible, non-deterministic, expensive |
| **The Race** | Match architecture to task entropy; hybrid usually wins |
| **Short-term Memory** | Context window; automatic, ephemeral, limited |
| **Long-term Memory** | External store; persistent, retrieved, requires management |
| **Summarisation** | Compress old context; loses detail, frees space |
| **Vector Memory** | Embed-store-retrieve; retrieves only what is relevant |
| **mem0** | Managed memory layer with smart deduplication |
| **LangChain** | Building blocks for linear LLM pipelines |
| **LangGraph** | Graph-based agent orchestration with cycles and persistence |
