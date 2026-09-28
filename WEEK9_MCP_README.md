# Week 9 - Module 5 - MCP: How AI Agents Talk to Tools and Data

> **Domain:** Customer Support Tickets | **Evaluated:** Week 10, Monday

---

## Table of Contents

1. [What is MCP? (The Big Picture)](#1-what-is-mcp-the-big-picture)
2. [The Three Roles - Host, Client, Server](#2-the-three-roles---host-client-server)
3. [Where Does the AI Actually Run?](#3-where-does-the-ai-actually-run)
4. [Tools, Resources, and Prompts - The Three Things a Server Can Offer](#4-tools-resources-and-prompts---the-three-things-a-server-can-offer)
5. [Transports - How Messages Travel (stdio vs HTTP)](#5-transports---how-messages-travel-stdio-vs-http)
6. [The JSON-RPC Handshake - The Conversation Protocol](#6-the-json-rpc-handshake---the-conversation-protocol)
7. [Tool Discovery - Finding Tools Automatically](#7-tool-discovery---finding-tools-automatically)
8. [Building Your Own MCP Server with fastmcp](#8-building-your-own-mcp-server-with-fastmcp)
9. [Recoverable Errors - Writing Helpful Error Messages](#9-recoverable-errors---writing-helpful-error-messages)
10. [Remote MCP and Auth - Keeping Things Secure](#10-remote-mcp-and-auth---keeping-things-secure)
11. [Adding a Second Server Without Touching Agent Code](#11-adding-a-second-server-without-touching-agent-code)
12. [Supply-Chain Risk - Should You Trust That Server?](#12-supply-chain-risk---should-you-trust-that-server)
13. [Week 9 Task A - What You Need to Submit](#13-week-9-task-a---what-you-need-to-submit)
14. [Common Mistakes and Why They Are Wrong](#14-common-mistakes-and-why-they-are-wrong)

---

## 1. What is MCP? (The Big Picture)

### The problem without MCP

Imagine you have three different AI assistants and all three need to look up customer support tickets. Without a shared standard, each AI team has to write their own custom connection code to the ticket system. That is a lot of repeated work, and if the ticket system changes, everyone has to update their own code separately.

```
AI Agent A  -- (custom glue code written by Team A) -->  Ticket System
AI Agent B  -- (custom glue code written by Team B) -->  Ticket System
AI Agent C  -- (custom glue code written by Team C) -->  Ticket System
```

### The solution: MCP

MCP (Model Context Protocol) is like a universal power socket. Once the ticket system plugs into MCP, ANY AI agent that also speaks MCP can use it -- no custom code needed on either side.

```
AI Agent A  --+
AI Agent B  --+-- (MCP, one shared standard) -->  Ticket MCP Server --> Ticket System
AI Agent C  --+
```

Think of it like USB. Once a device has a USB port, any computer can talk to it. You do not need a special cable for every combination.

### The honest answer clients want

> "Does MCP make my AI smarter?"

**No.** MCP is just plumbing -- like the pipes in a building. The pipes do not make the water taste better; they just make it easy to move water anywhere. MCP makes tools easy to share and swap, but the quality of the AI's answers depends on the AI model itself, not MCP.

---

## 2. The Three Roles - Host, Client, Server

Every MCP setup has three players. Think of it like a restaurant:

| MCP Role | Restaurant Equivalent | What it Does |
|---|---|---|
| **Host** | The restaurant owner | Runs the whole operation, decides what to order |
| **Client** | The waiter | Carries messages between the kitchen and the owner |
| **Server** | The kitchen | Does the actual work and sends back results |

### In technical terms

| Role | In Your Project | Job |
|---|---|---|
| **Host** | Your Python agent script | Runs the AI model, receives user questions, decides what to do |
| **Client** | The MCP SDK library inside your script | Sends requests to MCP servers and gets back results |
| **Server** | A separate program (e.g. the ticket-history server) | Exposes tools the agent can use |

### A visual picture

```
Your Python Script (the HOST)
|
|-- loads the AI model (Claude, GPT, etc.)
|-- has an MCP Client built in
|       |
|       |-- talks to --> RAG Server (MCP Server #1)
|       |-- talks to --> Ticket-History Server (MCP Server #2)
|
|-- user asks a question
|-- AI decides which tools to use
|-- client calls the right server
|-- result comes back to AI
|-- AI gives the final answer
```

---

## 3. Where Does the AI Actually Run?

This is the most important thing to understand. Many beginners get this wrong.

### Simple answer: the AI ONLY runs in the Host

The MCP Server is just a helper. It does not think, it does not use AI, it just does what it is told.

```
MCP SERVER                    YOUR HOST (agent script)
-----------                   ------------------------
- Looks up tickets            - THIS is where the AI lives
- Returns raw data            - Claude / GPT runs here
- Has NO brain of its own     - The AI reads the data and thinks
- Like a librarian who        - Like the researcher who reads
  hands you the book            the book and understands it
```

### Why does this matter?

If you put an AI model INSIDE your MCP server, you have made a big architectural mistake. The server is supposed to hand over raw information. The host is supposed to process it with the AI. Mixing them up means:

- You are paying for two AI calls instead of one
- The architecture becomes confusing and hard to debug
- You have misunderstood what MCP is for

---

## 4. Tools, Resources, and Prompts - The Three Things a Server Can Offer

An MCP server can offer three types of things. Choosing the right type matters.

---

### Tools - Things the AI Decides to Call

A **Tool** is like a button the AI can press whenever it wants. The AI reads your user's question and thinks "I need to press the 'lookup ticket' button to answer this."

**Use tools when:** The AI needs to decide at runtime whether to fetch something, based on the user's question.

```python
@mcp.tool()
def lookup_ticket(ticket_id: str) -> dict:
    """
    Find a support ticket using its ID.
    ticket_id should look like TCK-1234 (the letters TCK, a dash, then numbers).
    """
    return database.find_ticket(ticket_id)
```

When the user asks "What is the status of ticket TCK-1234?" the AI reads the tool description, realises this is the right tool, and calls it.

---

### Resources - Background Information Attached by the App

A **Resource** is like the briefing notes you hand to someone before a meeting. The app (host) attaches resources to the conversation automatically. The AI does NOT call resources -- they are just there in the background.

**Use resources when:** The information should always be available in every conversation, not fetched on demand.

```python
@mcp.resource("ticket://escalation/{ticket_id}")
def escalation_history(ticket_id: str) -> str:
    """The full timeline of who escalated this ticket and when."""
    return database.get_escalation_trail(ticket_id)
```

The app attaches this to the context at the start of every conversation so the AI always knows the escalation history without having to ask.

**Simple decision rule:**

```
"Should the AI always have this information?" --> Resource
"Should the AI fetch this only when it needs it?" --> Tool
```

**Common mistake:** Making escalation history a Tool when it should be a Resource. Every time the AI wants it, it burns a full round trip. If it is always needed, just attach it as a Resource.

---

### Prompts - Ready-Made Message Templates

A **Prompt** is a pre-written starting message that the app can load and use. Think of it as a saved script.

```python
@mcp.prompt()
def triage_prompt(ticket_id: str) -> str:
    return f"You are a support agent. Ticket {ticket_id} has been escalated. Please summarise the issue and suggest the next step."
```

The host can load this prompt template and use it instead of writing the same instructions every time.

---

## 5. Transports - How Messages Travel (stdio vs HTTP)

MCP defines WHAT messages look like. The transport defines HOW they travel.

### stdio (Standard Input/Output)

This is the simplest option. The host program starts the server as a child process (like launching a sub-program) and they talk through text piped between them.

Think of it like two people passing notes under a door.

```
Host program
    |
    | (starts the server as a child process)
    v
Server process
    |
    | stdin  <-- host sends messages here
    | stdout --> server replies here
```

**When to use stdio:** Local development, tools you run on your own machine.

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

This tells your agent: "Start the server by running `python -m mcp_server.main` and talk to it through stdin/stdout."

---

### HTTP / SSE (Hypertext Transfer Protocol / Server-Sent Events)

This is for servers running on the internet or a different machine. Your agent connects to a URL, just like a web browser connects to a website.

Think of it like making a phone call instead of passing notes.

```
Host (your machine)
    |
    | (HTTP requests over the internet)
    v
Server (running on a cloud machine at some URL)
```

**When to use HTTP:** Shared servers used by multiple agents, production systems, third-party services.

```json
{
  "mcpServers": {
    "ticket-history": {
      "url": "https://support-ops.internal/mcp",
      "transport": "sse",
      "headers": { "Authorization": "Bearer your-secret-token-here" }
    }
  }
}
```

---

## 6. The JSON-RPC Handshake - The Conversation Protocol

When your agent connects to an MCP server, they have a fixed three-step conversation. This is called the handshake. Understanding it removes all the mystery.

**JSON-RPC** means the messages are written in JSON (a simple text format) and follow the RPC (Remote Procedure Call) style -- you send a request, you get a response.

---

### Step 1: initialize - "Hello, what can you do?"

The client and server introduce themselves and agree on the version of the protocol to use.

```json
Client sends:
{
  "jsonrpc": "2.0",           <-- always this, means "we are using JSON-RPC version 2"
  "id": 1,                    <-- a unique number for this message (used to match reply)
  "method": "initialize",     <-- the action we want: introduce ourselves
  "params": {
    "protocolVersion": "2024-11-05",   <-- which version of MCP we speak
    "capabilities": {
      "tools": {}             <-- we can handle tool calls
    },
    "clientInfo": {
      "name": "billing-agent",
      "version": "1.0.0"
    }
  }
}

Server replies:
{
  "jsonrpc": "2.0",
  "id": 1,                    <-- same id as the request (shows this is the reply)
  "result": {
    "protocolVersion": "2024-11-05",
    "capabilities": {
      "tools": { "listChanged": true }   <-- server can notify us if tools change
    },
    "serverInfo": { "name": "ticket-history-server", "version": "0.2.0" }
  }
}
```

**Does the AI model run here?** No. This is just two programs saying hello.

---

### Step 2: tools/list - "Show me your menu"

The client asks the server to list all its tools, like asking a waiter for the menu.

```json
Client sends:
{
  "jsonrpc": "2.0",
  "id": 2,
  "method": "tools/list",     <-- we want the list of tools
  "params": {}
}

Server replies:
{
  "jsonrpc": "2.0",
  "id": 2,
  "result": {
    "tools": [
      {
        "name": "lookup_ticket",    <-- the tool's name (AI will use this name when calling it)
        "description": "Find a support ticket by its ID. ID format: TCK-nnnn",
        "inputSchema": {            <-- what arguments the tool expects
          "type": "object",
          "properties": {
            "ticket_id": {
              "type": "string",
              "description": "The ticket ID, like TCK-1234"
            }
          },
          "required": ["ticket_id"]
        }
      },
      {
        "name": "get_escalation_history",
        "description": "Returns the escalation trail for a ticket.",
        "inputSchema": { ... }
      }
    ]
  }
}
```

**Does the AI model run here?** No. The host is just collecting the menu. It will pass this list to the AI in the next step.

---

### Step 3: tools/call - "I'll have the lookup_ticket please"

After the AI has seen the tools list and decided which tool to use (THIS is when the AI model runs), the host sends a request to call that tool.

```
Timeline:
1. Host sends tool list to the AI model        <-- AI MODEL RUNS HERE
2. AI model outputs: "call lookup_ticket with ticket_id=TCK-4471"
3. Host sends tools/call to the server         <-- no AI here
4. Server looks up the ticket and replies
5. Host sends the result back to the AI model  <-- AI MODEL RUNS HERE AGAIN
6. AI model reads the result and writes the answer
```

```json
Host sends to server:
{
  "jsonrpc": "2.0",
  "id": 3,
  "method": "tools/call",       <-- we want to run a tool
  "params": {
    "name": "lookup_ticket",    <-- which tool to run
    "arguments": {
      "ticket_id": "TCK-4471"  <-- what to pass to the tool
    }
  }
}

Server replies:
{
  "jsonrpc": "2.0",
  "id": 3,
  "result": {
    "content": [
      {
        "type": "text",
        "text": "Ticket TCK-4471 not found. IDs look like TCK-nnnn -- please check the number."
      }
    ],
    "isError": false   <-- false means the AI can recover; true means something broke hard
  }
}
```

### Quick field glossary

| Field | Plain English meaning |
|---|---|
| `jsonrpc` | The version of the messaging format ("2.0" always) |
| `id` | A tracking number so we can match replies to requests |
| `method` | What we want to do (initialize, tools/list, tools/call) |
| `params` | The details for that action |
| `result` | The successful answer |
| `error` | Present instead of result when something went badly wrong |
| `isError` | Inside tools/call result -- false means the AI can handle it, true means hard crash |

---

## 7. Tool Discovery - Finding Tools Automatically

**Discovery is the main point of MCP.** Instead of you writing every tool name into your agent code by hand, the agent asks the server "what tools do you have?" every time it starts. The server tells it. The agent uses whatever it finds.

### Without discovery (BAD - defeats the whole purpose)

```python
# agent_loop.py - WRONG WAY
# You typed the tools in by hand
TOOLS = [
    {"name": "lookup_ticket", "description": "...", "inputSchema": {...}},
    {"name": "search_knowledge_base", "description": "...", "inputSchema": {...}},
]
# Problem: if you add a second server, you have to change this file
# The diff will show agent_loop.py changed -- FAIL on the rubric
```

### With discovery (CORRECT)

```python
# agent_loop.py - CORRECT WAY
# Tools are fetched from the server at startup -- nothing is typed in by hand
async def run(config: dict):
    async with MultiServerMCPClient(config["mcpServers"]) as client:
        tools = await client.list_tools()   # ask the server for the list
        
        response = await anthropic.messages.create(
            model="claude-opus-5",
            tools=tools,            # pass whatever the server told us
            messages=[{"role": "user", "content": user_question}]
        )
        # handle tool calls ...
```

Now when you add a second server in the config file, `agent_loop.py` does not change at all. The agent discovers both servers' tools automatically.

---

## 8. Building Your Own MCP Server with fastmcp

`fastmcp` is a Python library that makes building an MCP server simple.

### Install it

```bash
pip install fastmcp
```

### A complete working server

```python
# mcp_server/main.py

from fastmcp import FastMCP

# Give your server a name
mcp = FastMCP("billing-support-server")

# Define a tool using the @mcp.tool() decorator
# The function name becomes the tool name
# The docstring becomes the tool description the AI reads
@mcp.tool()
def lookup_ticket(ticket_id: str) -> dict:
    """
    Find a support ticket by its ID.

    ticket_id must be in the format TCK-nnnn, for example TCK-1234 or TCK-0042.

    Returns: the ticket's status, owner, priority, and when it was last updated.

    If the ticket does not exist, this tool will tell you clearly so you
    can ask the user to check the number -- it will NOT crash.
    """
    ticket = database.find(ticket_id)

    if not ticket:
        # Return a helpful message instead of crashing
        # This lets the AI tell the user something useful
        return {"message": f"Ticket {ticket_id} not found -- IDs look like TCK-nnnn. Please double-check."}

    return ticket


@mcp.tool()
def get_escalation_history(ticket_id: str) -> list:
    """Return the list of escalation events for a ticket."""
    return database.get_escalations(ticket_id)


# Start the server
if __name__ == "__main__":
    mcp.run()   # uses stdio transport by default
```

### To run it with HTTP instead

```python
if __name__ == "__main__":
    mcp.run(transport="sse", host="0.0.0.0", port=8001)
```

---

## 9. Recoverable Errors - Writing Helpful Error Messages

The tool description (docstring) is literally what the AI reads before deciding to use your tool. Treat it like a note you are writing to the AI, not a comment for other programmers.

### What is a "recoverable" error?

A **recoverable error** means the AI gets enough information to tell the user something useful and try a different approach. A **non-recoverable error** means the AI gets a useless crash message and has no idea what went wrong.

---

### Before -- the bad way

```python
@mcp.tool()
def lookup_ticket(ticket_id: str) -> dict:
    """Look up a ticket."""           # too vague -- AI does not know the ID format
    ticket = database.find(ticket_id)
    if not ticket:
        raise ValueError("Error 3")  # completely unhelpful message
```

**What the AI sees and does:**

```
User:      What is the status of ticket TCK-4471?
Assistant: [calls lookup_ticket(ticket_id="TCK-4471")]
Tool:      Error: request failed
Assistant: [calls lookup_ticket again -- it cannot tell if the ticket is missing or the server is broken]
Tool:      Error: request failed
Assistant: [calls a third time]
Tool:      Error: request failed
Assistant: I am sorry, I could not retrieve that ticket.
```

The AI wasted three turns and still could not help the user.

---

### After -- the correct way

```python
@mcp.tool()
def lookup_ticket(ticket_id: str) -> dict:
    """
    Find a support ticket by its unique ID.

    IMPORTANT: ticket_id must match the format TCK-nnnn
    where nnnn is a 4-digit number. Examples: TCK-1234, TCK-0042.

    If the ticket is not found, this tool returns a clear message
    explaining the problem so you can tell the user to verify
    the ID rather than retrying the same broken call.

    Returns: dict with status, owner, priority, last_updated.
    """
    ticket = database.find(ticket_id)
    if not ticket:
        # Return a message dict, NOT raise an exception
        # isError stays false -- the AI can handle this gracefully
        return {"message": f"Ticket {ticket_id} not found -- IDs look like TCK-nnnn. Please verify the number."}
    return ticket
```

**What the AI sees and does:**

```
User:      What is the status of ticket TCK-4471?
Assistant: [calls lookup_ticket(ticket_id="TCK-4471")]
Tool:      {"message": "Ticket TCK-4471 not found -- IDs look like TCK-nnnn. Please verify."}
Assistant: I could not find ticket TCK-4471. Support ticket IDs look like TCK-1234
           (four digits after the dash). Could you double-check the number?
```

One turn. Useful answer. User knows what to do next.

---

### The key rule

> Raise an exception only when something is truly broken (network down, database crashed).
> Return a friendly message dict when the data simply does not exist.

---

## 10. Remote MCP and Auth - Keeping Things Secure

When your MCP server is on the internet, you need to control who can call it. This is called authentication (auth for short).

### Bearer Token - The Simplest Method

A bearer token is like a key card. If you have the card, you get in. If you do not, the door stays shut.

**Server side -- checking the token**

```python
from fastmcp import FastMCP
from fastmcp.auth import BearerAuthMiddleware

mcp = FastMCP("ticket-history-server")

# Only let callers with a valid token through
mcp.add_middleware(BearerAuthMiddleware(valid_tokens={"secret-token-abc123"}))
```

**Client side -- sending the token**

```json
{
  "mcpServers": {
    "ticket-history": {
      "url": "https://support-ops.internal/mcp",
      "transport": "sse",
      "headers": {
        "Authorization": "Bearer secret-token-abc123"
      }
    }
  }
}
```

Never write the actual token in the config file. Use an environment variable:

```json
"headers": { "Authorization": "Bearer ${TICKET_TOKEN}" }
```

Then set the variable in your terminal before running the agent:

```bash
export TICKET_TOKEN=secret-token-abc123
```

---

### Scoped Tokens - Limiting What a Token Can Do

A scoped token is like a key card that only opens certain rooms. For example, a token might be allowed to look up tickets but NOT allowed to read escalation history.

```python
@mcp.tool()
def get_escalation_history(ticket_id: str) -> list:
    """Return the escalation history for a ticket."""
    current_token = get_current_token()

    # Check if this token has the right permission
    if "escalation:read" not in current_token.scopes:
        return {"error": "Access denied -- your token does not have escalation:read permission."}

    return database.get_escalations(ticket_id)
```

**What the AI sees when the token is denied:**

```
Assistant: [calls get_escalation_history(ticket_id="TCK-1234")]
Tool:      {"error": "Access denied -- your token does not have escalation:read permission."}
Assistant: I do not have permission to view the escalation history for this ticket.
           A higher-access token would be needed for that.
```

The AI handles the denial gracefully and tells the user clearly what happened.

---

## 11. Adding a Second Server Without Touching Agent Code

This is the core skill Week 9 is testing. The idea is simple: because your agent uses tool discovery, adding a new server requires changing ONLY the config file -- not the agent code.

### mcp_config.json before (one server)

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

### mcp_config.json after (two servers -- only the config changed)

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

The agent file (`agent_loop.py`) did not change at all. To prove this:

```bash
git diff HEAD -- agent/agent_loop.py > agent_diff.txt
# The file should have 0 lines of difference
```

### Tool count before and after

When you add the second server, the agent discovers more tools automatically:

```
Before (only rag-server connected):
  - search_knowledge_base
  - get_billing_policy
  Total: 2 tools

After (both servers connected):
  - search_knowledge_base       <-- from rag-server (same as before)
  - get_billing_policy          <-- from rag-server (same as before)
  - lookup_ticket               <-- NEW, discovered from ticket-history
  - get_escalation_history      <-- NEW, discovered from ticket-history
  Total: 4 tools
```

The agent code is the same. Discovery did the rest.

---

## 12. Supply-Chain Risk - Should You Trust That Server?

When you add someone else's MCP server to your agent, that server becomes part of your system. It runs with your credentials and can see everything your agent touches.

Think of it like hiring a contractor. They come into your office, they can see your files, they hear your conversations. You need to know who they are before you let them in.

### Five questions to ask before adding any third-party server

**1. Who wrote it?**
Is it from a known team inside your company, or a random open-source repo? Knowing the author tells you how much to trust it.

**2. What can it reach?**
Your token grants the server access to data. What data can it read? If your token can see all 100,000 customer tickets, the server can too -- even if you only asked it to look at one.

**3. What does it log?**
Every tool call might be written to a log file on their server. Ticket IDs, customer names, and other personal data could end up in someone else's logs.

**4. What happens if the token is stolen?**
If an attacker gets hold of the bearer token, they can call every tool the token allows -- directly, without going through your agent, from anywhere in the world.

**5. Ship it or not?**
Based on the answers above, is the risk acceptable? If the server is internal, well-maintained, logs only what it needs to, and uses a short-lived read-only token -- probably yes. If it is an unknown third party with broad access and permanent tokens -- probably no.

### Five-line risk note template (required deliverable)

```
1. AUTHOR:  Support Ops team (internal) -- verify by checking their repo and deployment pipeline.
2. REACH:   The token grants read access to every ticket the service account can see, not just the ones asked about.
3. LOGGING: The server logs ticket_id and caller IP on every tools/call -- these logs contain personal data.
4. STOLEN TOKEN: An attacker with the token can enumerate all tickets and read escalation history without your agent.
5. SHIP?:   Yes -- if owned by a known internal team, running in the company VPC, and token is read-only with a short expiry.
```

---

## 13. Week 9 Task A - What You Need to Submit

| # | File to submit | What it shows |
|---|---|---|
| 1 | `agent_diff.txt` | Zero lines changed in the agent file -- proves config-only extension |
| 2 | Config diff (the changed JSON) | Shows exactly which lines were added to connect the second server |
| 3 | `wire.json` | The raw initialize, tools/list, and tools/call messages with your annotations |
| 4 | Tool count line | "2 tools before, 4 tools after" with the tool names listed |
| 5 | `error_before_after.md` | Same failing call -- old error message vs new helpful message |
| 6 | `risk_note.md` | Exactly 5 lines answering the five supply-chain questions |

### How each item is marked

| What is being checked | Points |
|---|---|
| Agent file shows zero changed lines (diff proves it) | 30 |
| Raw wire messages captured and annotated, model-call location correctly identified | 25 |
| Docstring rewritten as prompt, error made recoverable, before/after transcript shown | 20 |
| Tool count with names taken from tools/list (not made up from your notes) | 15 |
| Five-line risk note answering all five questions | 10 |
| **Total** | **100** |

---

## 14. Common Mistakes and Why They Are Wrong

### Mistake 1: Hard-coding the tool list

```python
# WRONG
TOOLS = [{"name": "lookup_ticket", ...}]
```

**Why wrong:** If you type the tool names in by hand, adding a second server will require changing your agent file. That breaks the whole point of discovery. Your diff will show changes -- and that is 30 points lost.

---

### Mistake 2: Running an AI model inside your MCP server

```python
# WRONG -- inside the server
def lookup_ticket(ticket_id: str):
    result = database.find(ticket_id)
    # DO NOT DO THIS:
    ai_response = call_openai("Summarise this ticket: " + str(result))
    return ai_response
```

**Why wrong:** The server's job is to return raw data. The host's job is to pass that data to the AI. If the server also calls an AI, the architecture is broken -- you now have two AI systems talking to each other unnecessarily, doubling cost and confusion.

---

### Mistake 3: Making escalation history a Tool when it should be a Resource

**Why wrong:** If the escalation history is needed for every conversation, making it a Tool means the AI wastes a full turn fetching it every single time. Resources are attached to the conversation automatically -- no turn needed.

---

### Mistake 4: Swallowing errors into useless messages

```python
# WRONG
except Exception:
    raise ValueError("Error: request failed")
```

**Why wrong:** The AI cannot tell if the ticket ID is wrong, if the server is down, or if there is a permissions problem. It just sees "request failed" and retries the same call over and over. Three wasted turns, zero useful information for the user.

---

### Mistake 5: Adding a third-party server without checking what it can access

**Why wrong:** The server runs inside your agent's trust boundary. It can see every ticket your token can see. If the server is compromised, or if it logs your data irresponsibly, you have a data breach -- and you invited it in yourself.

---

## Quick Reference Card

```
What is MCP?        A shared standard (like USB) so any AI can use any tool
Three roles:        Host (runs the AI) -- Client (carries messages) -- Server (does the work)
Where AI runs:      HOST ONLY -- never inside the MCP server
Three primitives:   Tools (AI decides to call) -- Resources (app attaches) -- Prompts (templates)
Transports:         stdio (local, child process) -- HTTP/SSE (remote, over internet)
Handshake order:    initialize --> tools/list --> [AI model runs] --> tools/call --> [AI model runs]
Discovery:          Agent calls tools/list at startup -- never hard-code tool names
Recoverable error:  Return a message dict -- do not raise an exception for missing data
Auth:               Bearer token in config header -- use environment variables, not plain text
Risk check:         Ask who wrote it, what it can reach, what it logs, what a stolen token buys
Config-only change: Adding a server changes only the config file -- agent code stays identical
```
