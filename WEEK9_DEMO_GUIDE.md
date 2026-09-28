# Week 9 Demo Guide -- MCP Integration

This document covers how to set up, run, and explain the Week 9 MCP implementation during a demo.

---

## Prerequisites

- Python 3.10+ installed
- A valid Groq API key (free at https://console.groq.com)
- The project cloned and virtual environment set up

---

## Setup Steps

### Step 1: Create and activate the virtual environment

```bash
python -m venv .venv
```

On Windows:
```bash
.venv\Scripts\activate
```

On Mac/Linux:
```bash
source .venv/bin/activate
```

### Step 2: Install dependencies

```bash
pip install -r requirements.txt
```

This installs everything including `mcp[cli]>=1.0.0` which provides both the MCP server SDK (`MCPServer`) and the client SDK (`ClientSession`, `stdio_client`).

### Step 3: Configure environment variables

Copy the example env file and fill in your keys:

```bash
cp .env.example .env
```

Edit `.env` and set at minimum:

```
LLM_PROVIDER=groq
GROQ_API_KEY=your_actual_groq_key
LLM_MODEL=llama-3.3-70b-versatile
```

Langfuse keys are optional. If left blank, tracing is disabled but the agent still runs.

### Step 4: Verify the MCP config

Open `mcp_config.json` at the project root. It should list both servers:

```json
{
  "mcpServers": {
    "billing-tools": {
      "command": "python",
      "args": ["mcp_servers/billing_tools_server.py"]
    },
    "ticket-history": {
      "command": "python",
      "args": ["mcp_servers/ticket_history_server.py"]
    }
  }
}
```

No other setup is needed. The agent reads this file at startup and connects to each server automatically.

---

## Running the Application

### Run the agent on a specific ticket

```bash
python -m agent.agent_loop T002
```

You should see output like:

```
[mcp] Connected to 'billing-tools': 4 tools discovered (get_ticket, get_order, get_customer_tier, search_knowledge_base)
[mcp] Connected to 'ticket-history': 2 tools discovered (lookup_ticket_history, get_escalation_history)

=== Agent run: T002  ===
  [lap 1] finish_reason=tool_calls lap_tokens=975 cumulative=975
    tool: get_ticket({"ticket_id":"T002"}) -> {"ticket_id": "T002", ...}
  [lap 2] finish_reason=tool_calls lap_tokens=1025 cumulative=2000
    tool: get_order({"order_id":"O202"}) -> {"order_id": "O202", ...}
  [lap 3] finish_reason=tool_calls lap_tokens=1136 cumulative=3136
    tool: get_customer_tier({"customer_id":"C102"}) -> {"customer_id": "C102", ...}
  [lap 4] finish_reason=stop lap_tokens=1352 cumulative=4488

Reply:
I've reviewed your request regarding the duplicate charge...

Laps: 4 | Tokens: 4488 | Cost: $0.004039 | Latency: 5.21s | Pass: True
```

### Try different tickets

```bash
python -m agent.agent_loop T003    # escalated ticket (has escalation history)
python -m agent.agent_loop T008    # order not found, triggers escalation
python -m agent.agent_loop T999    # invalid ticket -- shows recoverable error
```

### Run the FastAPI backend (optional, for frontend demo)

```bash
uvicorn api.main:app --reload --port 8000
```

### Run the Angular frontend (optional)

```bash
cd frontend
npm install
ng serve
```

Open http://localhost:4200 in your browser.

---

## What to Explain During the Demo

### 1. What is MCP and why do we need it? (2 minutes)

**Show:** `mcp_config.json`

**Say:**
> "MCP stands for Model Context Protocol. It is a standard for connecting AI agents to tools and data. Think of it like USB -- one standard socket that lets any tool plug into any agent."
>
> "Before MCP, every tool was hard-coded into the agent. If another team built a new tool, we had to change our agent code. With MCP, tools are discovered automatically at startup. Adding a new tool is just a config change -- zero agent code changes."
>
> "This config file lists two MCP servers. The agent reads it at startup, connects to each, and asks them what tools they have. That is it."

---

### 2. The three roles: Host, Client, Server (2 minutes)

**Show:** `agent/agent_loop.py` (lines 28, 36-37) and `mcp_servers/billing_tools_server.py`

**Say:**
> "There are three roles in MCP:
> - The **Host** is our agent script. It runs the AI model.
> - The **Client** is the MCP SDK built into our script. It talks to the servers.
> - The **Server** is a separate process that exposes tools. It does NOT run any AI."
>
> "This is the most important thing: the AI only runs in the host. The server just does lookups and returns raw data. If you put an AI call inside the MCP server, you have misunderstood the architecture."

---

### 3. Tool Discovery (3 minutes)

**Show:** Run `python -m agent.agent_loop T002` and point to the first two lines of output

**Say:**
> "Watch the startup. The agent connects to both servers and prints what it found:
> - billing-tools: 4 tools
> - ticket-history: 2 tools
>
> That is 6 tools total, discovered automatically. The agent did not have those names written in its code. It asked each server 'what tools do you have?' and the servers told it."
>
> "This is called **tool discovery** via the `tools/list` JSON-RPC call."

**Then show the proof:** Open `deliverables/agent_diff.txt`

> "This diff proves that when we added the second server (ticket-history), zero lines changed in agent_loop.py. Only the config file changed. That is the entire point of MCP -- config-only extension."

---

### 4. The JSON-RPC Wire Protocol (3 minutes)

**Show:** `deliverables/wire_annotated.json`

**Say:**
> "Under the hood, MCP uses JSON-RPC 2.0. There are three steps:
>
> 1. **initialize** -- the client and server say hello and agree on the protocol version. No AI runs here.
>
> 2. **tools/list** -- the client asks the server to list its tools. The server sends back the names, descriptions, and parameter schemas. No AI runs here either.
>
> 3. **tools/call** -- after the AI model has seen the tool list and decided to call one, the host sends the call to the server. The server executes it and returns the result. The AI runs BEFORE this step (to decide which tool to call) and AFTER (to process the result)."
>
> "The key question is: where does the model call happen? It happens between steps 2 and 3. The host takes the tool list, sends it to the LLM along with the user's question, and the LLM decides which tool to call."

---

### 5. Recoverable Errors and Docstrings as Prompts (3 minutes)

**Show:** `deliverables/error_before_after.md`

**Say:**
> "The tool description -- the docstring -- is literally what the AI reads before deciding to call a tool. It is a prompt, not a code comment."

**Run the bad ticket to show the improved error:**

```bash
python -m agent.agent_loop T999
```

> "Watch what happens when the ticket does not exist.
>
> **Before** our change, the error was just `{"error": "not_found"}`. The AI had no idea why it failed. It would retry the same call three times and then give up.
>
> **After** our change, the error says: `Ticket T999 not found -- IDs look like Tnnn (e.g. T002, T003, T004). Ask the user to verify.`
>
> The AI reads that message, understands the problem, and tells the user to check the ticket number. One turn instead of three."

---

### 6. Supply-Chain Risk (1 minute)

**Show:** `deliverables/risk_note.md`

**Say:**
> "When you add someone else's MCP server, it runs inside your agent's trust boundary. You need to ask five questions before you trust it:
>
> 1. **Who wrote it?** Is it an internal team or unknown third party?
> 2. **What can it reach?** The token may grant broader access than you think.
> 3. **What does it log?** Ticket IDs and customer data may end up in their logs.
> 4. **What if the token is stolen?** An attacker can call every tool directly.
> 5. **Ship or not?** Only if the answers above are acceptable."

---

### 7. Tool Count Before vs After (1 minute)

**Show:** `deliverables/tool_count.md`

**Say:**
> "Before adding the second server: 4 tools from billing-tools.
> After adding the second server: 6 tools -- the same 4 plus 2 new ones (lookup_ticket_history, get_escalation_history) discovered automatically from the ticket-history server.
>
> These counts come from the `tools/list` response, not from our notes."

---

## Project Structure (for reference)

```
rag-billing-support/
  mcp_config.json                         <-- server registry (the only file you change to add a server)
  mcp_servers/
    billing_tools_server.py               <-- MCP Server #1: wraps existing 4 tools
    ticket_history_server.py              <-- MCP Server #2: ticket lifecycle + escalation history
  agent/
    mcp_client.py                         <-- MCPManager: connects to servers, discovers tools, routes calls
    agent_loop.py                         <-- Agent loop: imports MCPManager, discovers tools dynamically
    tools.py                              <-- Tool implementations (get_ticket, get_order, etc.)
    tickets.py                            <-- Synthetic ticket data and scoring
  deliverables/
    agent_diff.txt                        <-- Proof: zero agent code changes when adding server 2
    wire_annotated.json                   <-- Annotated JSON-RPC exchange (initialize, tools/list, tools/call)
    error_before_after.md                 <-- Before/after transcript for recoverable error
    tool_count.md                         <-- 4 tools before, 6 tools after, with names
    risk_note.md                          <-- 5-line supply-chain risk assessment
  wire.json                               <-- Raw captured JSON-RPC messages
```

---

## Quick Demo Script (5-minute version)

If you only have 5 minutes, do this:

1. **Open** `mcp_config.json` -- show two servers listed
2. **Run** `python -m agent.agent_loop T008` -- point to the MCP connection lines showing 6 tools discovered
3. **Run** `python -m agent.agent_loop T999` -- show the recoverable error message
4. **Open** `deliverables/agent_diff.txt` -- show zero lines changed
5. **Open** `deliverables/wire_annotated.json` -- explain the three steps and where the model call happens

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `ModuleNotFoundError: No module named 'mcp'` | Run `pip install mcp[cli]>=1.0.0` inside the venv |
| `GROQ_API_KEY not set` | Check your `.env` file has a valid key |
| `Connection closed` during MCP init | The server subprocess is using system Python instead of venv Python. The MCPManager maps `"python"` to `sys.executable` automatically, but verify your venv is activated |
| Agent hangs at startup | Check if both server scripts run standalone: `python mcp_servers/billing_tools_server.py` should start without errors |
| `Groq 429 rate-limit` | Wait a few seconds and retry. The agent has built-in retry logic for rate limits |
