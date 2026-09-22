# Week 9 · Module 5 — MCP: The Standard Way Agents Reach Tools & Data

> **Domain:** Customer Support Tickets · **Evaluated:** Week 10 · Monday

---

## Table of Contents

1. [What is MCP?](#1-what-is-mcp)
2. [The Three Roles: Host, Client, Server](#2-the-three-roles-host-client-server)
3. [Where the AI Actually Runs](#3-where-the-ai-actually-runs)
4. [Tools, Resources, and Prompts](#4-tools-resources-and-prompts)
5. [Transports: stdio vs HTTP](#5-transports-stdio-vs-http)
6. [The JSON-RPC Handshake](#6-the-json-rpc-handshake)
7. [Tool Discovery](#7-tool-discovery)
8. [Building Your Own MCP Server (fastmcp)](#8-building-your-own-mcp-server-fastmcp)
9. [Recoverable Errors — Writing Tool Docstrings as Prompts](#9-recoverable-errors--writing-tool-docstrings-as-prompts)
10. [Remote MCP & Auth](#10-remote-mcp--auth)
11. [Config-Only Server Addition (Zero Agent Code Changes)](#11-config-only-server-addition-zero-agent-code-changes)
12. [Supply-Chain Risk for Third-Party Servers](#12-supply-chain-risk-for-third-party-servers)
13. [Week 9 Task A — Deliverables Checklist](#13-week-9-task-a--deliverables-checklist)
14. [Common Mistakes to Avoid](#14-common-mistakes-to-avoid)

---

## 1. What is MCP?

**MCP (Model Context Protocol)** is an open industry standard that defines a single "socket" interface for connecting AI agents to external tools, data, and capabilities.

### The Problem It Solves

Before MCP, every tool had to be hand-wired into a specific app:

```
Agent A  ──(custom code)──>  Ticket API
Agent B  ──(custom code)──>  Ticket API   ← duplicate glue code
Agent C  ──(custom code)──>  Ticket API
```

With MCP, the Ticket API publishes *one server* and every agent that speaks MCP can use it:

```
Agent A  ──┐
Agent B  ──┼──(MCP)──>  Ticket MCP Server  ──>  Ticket API
Agent C  ──┘
```

### The Honest Client Framing

> "Does MCP make my AI smarter?" — **No.** It's plumbing. It wins on **reuse** and **easy swapping**, not on answer quality. The AI still runs on your side; the server is just offering capabilities.

---

## 2. The Three Roles: Host, Client, Server

| Role | Who/What | Responsibility |
|---|---|---|
| **Host** | Your application (Python script, web app) | Runs the model, orchestrates the agent loop |
| **Client** | Library inside the host (e.g. `mcp` SDK) | Speaks the MCP wire protocol to the server |
| **Server** | A separate process you or a third party wrote | Exposes tools/resources/prompts over MCP |

### Example: Ticket-history system

```
┌─────────────────────────────────────┐
│  HOST (your Python agent)           │
│                                     │
│  ┌───────────┐   JSON-RPC   ┌────────────────────┐
│  │ MCP Client├─────────────►│ Ticket-History MCP │
│  └─────┬─────┘              │ Server             │
│        │                    └────────┬───────────┘
│   Claude API                         │
│   (model call)                  Ticket DB / API
└─────────────────────────────────────┘
```

The **server never calls the model**. It just waits for tool-call requests, executes them, and returns results.

---

## 3. Where the AI Actually Runs

This is the single most important architectural fact:

```
┌──────────────────────┐        ┌──────────────────────┐
│   MCP SERVER         │        │   HOST / CLIENT      │
│                      │        │                      │
│  exposes tools       │        │  ← AI runs HERE      │
│  runs tool logic     │        │  calls Claude API    │
│  returns results     │        │  receives tool result│
│                      │        │  feeds result back   │
│  NO AI HERE ✗        │        │  to the model        │
└──────────────────────┘        └──────────────────────┘
```

**Common mistake:** Putting an LLM call *inside* your MCP server so it "answers the ticket". The server should only expose a raw capability; the host feeds the result back to the model.

---

## 4. Tools, Resources, and Prompts

MCP servers can expose three kinds of things:

### Tools — model-invoked

The model decides to call a tool. Each call costs a turn. Use for actions and lookups that depend on runtime user input.

```python
@mcp.tool()
def lookup_ticket(ticket_id: str) -> dict:
    """
    Look up a support ticket by ID.
    ticket_id must look like TCK-nnnn (e.g. TCK-1234).
    If not found, returns a helpful message — not a raw error.
    """
    ...
```

### Resources — app-attached context

The *host application* attaches resources to the prompt before the model sees it. The model does NOT invoke resources; they are passive context. Use for documents, configuration, background data that every request needs.

```python
@mcp.resource("ticket://escalation/{ticket_id}")
def escalation_history(ticket_id: str) -> str:
    """Returns the full escalation trail as plain text."""
    ...
```

> **Decision rule:** If the data should always be in the prompt → Resource. If the model should decide whether to fetch it → Tool.

### Prompts — reusable templates

Pre-built message templates the host can load and inject.

```python
@mcp.prompt()
def triage_prompt(ticket_id: str) -> str:
    return f"You are a support agent. Ticket {ticket_id} has been escalated. Summarise..."
```

---

## 5. Transports: stdio vs HTTP

MCP defines the protocol; the transport carries the bytes.

| Transport | How it works | Use case |
|---|---|---|
| **stdio** | Host spawns server as a child process; messages over stdin/stdout | Local servers, development, CLI tools |
| **HTTP (SSE)** | Server runs as a web service; client connects over HTTP | Remote/shared servers, multi-agent setups, production |

### stdio example (local server)

```json
// mcp_config.json
{
  "mcpServers": {
    "rag-server": {
      "command": "python",
      "args": ["-m", "mcp_server.main"],
      "transport": "stdio"
    }
  }
}
```

The host process spawns `python -m mcp_server.main` and pipes JSON-RPC messages through its stdin/stdout.

### HTTP/SSE example (remote server)

```json
{
  "mcpServers": {
    "ticket-history": {
      "url": "https://support-ops.internal/mcp",
      "transport": "sse",
      "headers": { "Authorization": "Bearer ${TICKET_TOKEN}" }
    }
  }
}
```

---

## 6. The JSON-RPC Handshake

Every MCP session follows this three-step sequence. Understanding it is what makes MCP "not a mystery".

### Step 1 — `initialize`

Client sends its capabilities; server replies with its own and the protocol version:

```json
// → client sends
{
  "jsonrpc": "2.0",        // always "2.0" — this is JSON-RPC 2.0
  "id": 1,                 // request id — matched in the response
  "method": "initialize",  // the RPC method name
  "params": {
    "protocolVersion": "2024-11-05",   // MCP version the client speaks
    "capabilities": {
      "tools": {}          // client can handle tool_call messages
    },
    "clientInfo": {
      "name": "billing-agent",
      "version": "1.0.0"
    }
  }
}

// ← server replies
{
  "jsonrpc": "2.0",
  "id": 1,                 // same id as the request
  "result": {
    "protocolVersion": "2024-11-05",
    "capabilities": {
      "tools": { "listChanged": true }  // server can push tool-list updates
    },
    "serverInfo": { "name": "ticket-history-server", "version": "0.2.0" }
  }
}
```

> **Model call happens:** NEVER during initialize. This is pure protocol negotiation.

### Step 2 — `tools/list`

Client asks what tools the server offers:

```json
// → request
{
  "jsonrpc": "2.0",
  "id": 2,
  "method": "tools/list",
  "params": {}
}

// ← response
{
  "jsonrpc": "2.0",
  "id": 2,
  "result": {
    "tools": [
      {
        "name": "lookup_ticket",          // tool name the model will use
        "description": "Look up a support ticket by ID (e.g. TCK-1234). Returns status, owner, and last update.",
        "inputSchema": {                  // JSON Schema for the tool's arguments
          "type": "object",
          "properties": {
            "ticket_id": {
              "type": "string",
              "description": "Ticket id — must match TCK-nnnn"
            }
          },
          "required": ["ticket_id"]
        }
      },
      {
        "name": "get_escalation_history",
        "description": "Returns the full escalation trail for a ticket.",
        "inputSchema": { ... }
      }
    ]
  }
}
```

> **Model call happens:** NEVER. This is discovery — the host reads the tool list and will pass it to the model in the next system prompt.

### Step 3 — `tools/call`

After the model decides to call a tool (the model call happens in the HOST before this step):

```json
// → request  (host sends after model outputs a tool_use block)
{
  "jsonrpc": "2.0",
  "id": 3,
  "method": "tools/call",   // the call method
  "params": {
    "name": "lookup_ticket", // which tool to invoke
    "arguments": {
      "ticket_id": "TCK-4471"
    }
  }
}

// ← response
{
  "jsonrpc": "2.0",
  "id": 3,
  "result": {
    "content": [
      {
        "type": "text",
        "text": "Ticket TCK-4471 not found. Ticket IDs look like TCK-nnnn — please verify the number."
      }
    ],
    "isError": false    // false = recoverable message; true = hard error
  }
}
```

> **Model call happens:** BEFORE this step (the model outputs the tool_use block). The host then sends this JSON-RPC request to the server. Another model call happens AFTER, to process the result.

### Annotated field reference

| Field | Meaning |
|---|---|
| `jsonrpc` | Always `"2.0"` — identifies JSON-RPC version |
| `id` | Correlation id — response `id` must match request `id` |
| `method` | What to do: `initialize`, `tools/list`, `tools/call` |
| `params` | Method-specific arguments |
| `result` | Successful response payload |
| `error` | Present instead of `result` on hard failure |
| `isError` | Inside `tools/call` result — `false` = model can recover |

---

## 7. Tool Discovery

**Discovery is the whole point of MCP.** Instead of hard-coding tool definitions in the agent, the agent calls `tools/list` at startup and builds the list dynamically.

### Without discovery (bad — defeats MCP's purpose)

```python
# agent.py — WRONG: tool list hard-coded
TOOLS = [
    {"name": "lookup_ticket", "description": "...", "inputSchema": {...}},
]
# Adding a second server requires changing agent.py ← this is what the task catches
```

### With discovery (correct)

```python
# agent.py — correct: discover at runtime
async def run(config: dict):
    async with MultiServerMCPClient(config["mcpServers"]) as client:
        tools = await client.list_tools()   # ← dynamic, from the server
        response = await anthropic.messages.create(
            model="claude-opus-5",
            tools=tools,                    # pass discovered tools to the model
            messages=[{"role": "user", "content": user_query}]
        )
        # handle tool calls ...
```

Adding a second server is now **config-only** — `agent.py` never changes.

---

## 8. Building Your Own MCP Server (fastmcp)

`fastmcp` is the fastest way to write an MCP server in Python.

### Install

```bash
pip install fastmcp
```

### Minimal server

```python
# mcp_server/main.py
from fastmcp import FastMCP

mcp = FastMCP("billing-support-server")

@mcp.tool()
def lookup_ticket(ticket_id: str) -> dict:
    """
    Look up a support ticket.

    Args:
        ticket_id: Ticket id in the format TCK-nnnn (e.g. TCK-1234).

    Returns a dict with status, owner, priority, and last_updated.
    If the ticket does not exist, returns a friendly message the model
    can act on: "Ticket TCK-9999 not found — IDs look like TCK-nnnn."
    """
    ticket = db.get(ticket_id)
    if not ticket:
        return {"message": f"Ticket {ticket_id} not found — IDs look like TCK-nnnn."}
    return ticket

@mcp.tool()
def get_escalation_history(ticket_id: str) -> list[dict]:
    """Return the escalation trail for a ticket."""
    return db.get_escalations(ticket_id)

if __name__ == "__main__":
    mcp.run()   # stdio transport by default
```

### Running with HTTP transport

```python
mcp.run(transport="sse", host="0.0.0.0", port=8001)
```

---

## 9. Recoverable Errors — Writing Tool Docstrings as Prompts

The docstring IS the prompt the model reads before deciding to call your tool. Treat it like a system prompt.

### Before — opaque error (bad)

```python
@mcp.tool()
def lookup_ticket(ticket_id: str) -> dict:
    """Look up a ticket."""
    ticket = db.get(ticket_id)
    if not ticket:
        raise ValueError("Error 3")   # model sees: Error: request failed
    return ticket
```

**Model transcript (before):**

```
User:      What's the status of TCK-4471?
Assistant: [calls lookup_ticket(ticket_id="TCK-4471")]
Tool:      Error: request failed
Assistant: [calls lookup_ticket(ticket_id="TCK-4471")]   ← retries same broken call
Tool:      Error: request failed
Assistant: [calls lookup_ticket(ticket_id="TCK-4471")]   ← retries again
Tool:      Error: request failed
Assistant: I'm sorry, I couldn't retrieve that ticket.   ← gives up, tells user nothing useful
```

The model cannot distinguish a bad ticket id from a dead server — it just retries blindly.

### After — recoverable error (correct)

```python
@mcp.tool()
def lookup_ticket(ticket_id: str) -> dict:
    """
    Look up a support ticket by its unique ID.

    ticket_id format: TCK-nnnn where nnnn is a 4-digit number (e.g. TCK-1234, TCK-0042).
    If the ticket does not exist, this tool returns a descriptive message so you can
    tell the user to double-check the ID rather than retrying the same call.

    Returns: dict with keys: status, owner, priority, last_updated.
    """
    ticket = db.get(ticket_id)
    if not ticket:
        # Return a message, not an exception — isError stays false
        return {"message": f"Ticket {ticket_id} not found: IDs look like TCK-nnnn — please verify."}
    return ticket
```

**Model transcript (after):**

```
User:      What's the status of TCK-4471?
Assistant: [calls lookup_ticket(ticket_id="TCK-4471")]
Tool:      {"message": "Ticket TCK-4471 not found: IDs look like TCK-nnnn — please verify."}
Assistant: I couldn't find ticket TCK-4471. Ticket IDs should look like TCK-1234
           (four digits after the dash). Could you double-check the number?
```

The model recovers in one turn and gives the user actionable feedback.

---

## 10. Remote MCP & Auth

### Why auth matters for remote servers

When your server is remote (HTTP/SSE), any caller with the URL can discover and invoke your tools. You need to gate access.

### Bearer token (simplest)

```python
# server side — fastmcp with auth middleware
from fastmcp import FastMCP
from fastmcp.auth import BearerAuthMiddleware

mcp = FastMCP("ticket-history-server")
mcp.add_middleware(BearerAuthMiddleware(valid_tokens={"tkn_abc123"}))
```

```json
// client config — token in header
{
  "mcpServers": {
    "ticket-history": {
      "url": "https://support-ops.internal/mcp",
      "transport": "sse",
      "headers": { "Authorization": "Bearer ${TICKET_TOKEN}" }
    }
  }
}
```

Set `TICKET_TOKEN` as an environment variable — never hard-code it in config files.

### Scoped tokens — denying specific tools

You can scope a token so it can call some tools but not others:

```python
@mcp.tool()
def get_escalation_history(ticket_id: str) -> list:
    """Return escalation trail."""
    token = get_current_token()
    if "escalation:read" not in token.scopes:
        # Return a recoverable denial — model sees it and stops
        return {"error": "Access denied: your token does not have escalation:read scope."}
    return db.get_escalations(ticket_id)
```

**Denial reaching the model:**

```
Assistant: [calls get_escalation_history(ticket_id="TCK-1234")]
Tool:      {"error": "Access denied: your token does not have escalation:read scope."}
Assistant: I don't have permission to retrieve the escalation history for that ticket.
           A higher-access token is required.
```

---

## 11. Config-Only Server Addition (Zero Agent Code Changes)

This is what Week 9 Task A is testing: **the agent code must not change when you add a second server**.

### mcp_config.json — before (one server)

```json
{
  "mcpServers": {
    "rag-server": {
      "command": "python",
      "args": ["-m", "mcp_server.main"],
      "transport": "stdio"
    }
  }
}
```

### mcp_config.json — after (two servers, config only)

```json
{
  "mcpServers": {
    "rag-server": {
      "command": "python",
      "args": ["-m", "mcp_server.main"],
      "transport": "stdio"
    },
    "ticket-history": {
      "url": "https://support-ops.internal/mcp",
      "transport": "sse",
      "headers": { "Authorization": "Bearer ${TICKET_TOKEN}" }
    }
  }
}
```

### Proving zero agent changes

```bash
git diff HEAD -- agent/agent_loop.py > agent_diff.txt
# agent_diff.txt should be empty (0 changed lines)
```

### Tool count before → after

```
Before (rag-server only):
  tools/list → 2 tools
    - search_knowledge_base
    - get_billing_policy

After (rag-server + ticket-history):
  tools/list → 4 tools
    - search_knowledge_base
    - get_billing_policy
    - lookup_ticket          ← new, from ticket-history server
    - get_escalation_history ← new, from ticket-history server
```

The agent loop is identical. Discovery handles the rest.

---

## 12. Supply-Chain Risk for Third-Party Servers

When you add someone else's MCP server, it runs inside your agent's trust boundary. It can see every request the agent makes that flows through it.

### Five-line risk note template (required deliverable)

```
1. AUTHOR:  Support Ops team (internal) — review their repo and deployment pipeline before trusting.
2. REACH:   The server token grants read access to every ticket visible to the service account — not just the ones your agent asks about.
3. LOGGING: The server logs ticket_id and caller IP on every tools/call — treat those logs as PII.
4. STOLEN TOKEN: An attacker with the bearer token can enumerate all tickets, read escalation history, and pivot to customer PII without touching your agent.
5. SHIP?:   Only if the server is owned by a known internal team, has a bug-bounty contact, runs in your VPC, and the token is scoped to read-only with a short TTL.
```

---

## 13. Week 9 Task A — Deliverables Checklist

| # | Deliverable | What it proves |
|---|---|---|
| 1 | `agent_diff.txt` — 0 changed lines in agent module | Config-only extension works |
| 2 | Config diff adding the second server | Which lines actually changed |
| 3 | `wire.json` — raw `initialize` → `tools/list` → `tools/call`, annotated | You read the actual wire |
| 4 | Tool count line: N before → M after, with names, from `tools/list` | Discovery is real, not hard-coded |
| 5 | `error_before_after.md` — same failing call, old vs new docstring/error | Recoverable error rewrite works |
| 6 | `risk_note.md` — exactly 5 lines | Supply-chain awareness |

### Points breakdown

| Criterion | Points |
|---|---|
| Config-only swap proven by diff (0 changed lines in agent module) | 30 |
| Raw initialize/tools-list/tools-call captured and annotated, model-call location stated | 25 |
| Docstring-as-prompt + recoverable-error rewrite, before/after transcript | 20 |
| Tool count before → after with names from `tools/list` | 15 |
| Five-line third-party risk note | 10 |
| **Total** | **100** |

---

## 14. Common Mistakes to Avoid

| Mistake | Why it's wrong |
|---|---|
| Hard-coding the tool list after connecting | Defeats discovery — diff will show agent changes |
| Putting an LLM call inside your MCP server | The server exposes capabilities; the host runs the model |
| Exposing escalation history as a tool instead of a resource | Tools are model-invoked (burn turns); escalation context should be app-attached |
| Swallowing not-found into `"Error: request failed"` | Model can't distinguish bad id from dead server; retries forever |
| Adding the third-party server without a risk assessment | It now runs in your trust boundary and sees every ticket your token can see |

---

## Quick Reference

```
MCP = JSON-RPC 2.0 over stdio or HTTP/SSE
Roles: Host (runs AI) · Client (speaks protocol) · Server (exposes tools)
AI runs: HOST only — never on the server
Three primitives: Tools (model-invoked) · Resources (app-attached) · Prompts (templates)
Handshake: initialize → tools/list → [model decides] → tools/call
Discovery: host calls tools/list; agent code never changes when you add a server
Recoverable error: return a message dict, not raise an exception (isError=false)
Auth: Bearer token in header; scope tokens to limit tool access
Risk: third-party server runs in your trust boundary — audit before adding
```
