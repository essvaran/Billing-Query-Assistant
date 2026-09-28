# How MCP Starts, Runs, and Works in This Project

This document walks through exactly how MCP is configured, how it starts up, how every piece connects, and how you can reuse these same MCP servers in a completely different application.

---

## Part 1: How MCP is Configured in This Project

There are three pieces that make MCP work here:

```
mcp_config.json          -- "which servers should the agent connect to?"
mcp_servers/*.py         -- the actual server programs that expose tools
agent/mcp_client.py      -- the client code inside the agent that talks to the servers
```

### The Config File: mcp_config.json

This is the starting point. It is a simple JSON file at the project root:

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

What each field means:

- `"mcpServers"` -- a dictionary of all servers the agent should connect to
- `"billing-tools"` / `"ticket-history"` -- a name you give each server (can be anything)
- `"command"` -- what program to run (here it is `python`)
- `"args"` -- what arguments to pass to that program (the path to the server script)

When the agent starts, it reads this file and says: "I need to start two programs, connect to each one, and ask them what tools they have."

To add a third server, you just add another entry here. No code changes anywhere else.

---

## Part 2: How MCP Starts Up (Step by Step)

When you run the agent:

```bash
python -m agent.agent_loop T002
```

Here is exactly what happens, in order:

### Step 1: Agent imports the MCPManager

In `agent/agent_loop.py`, line 28:

```python
from agent.mcp_client import MCPManager
```

This loads the MCPManager class but does not connect yet.

### Step 2: Agent creates the MCPManager and calls connect()

Lines 36-37:

```python
_mcp = MCPManager("mcp_config.json", log_wire=True)
_mcp.connect()
```

`MCPManager("mcp_config.json")` just stores the config path. Nothing happens yet.

`_mcp.connect()` is where everything starts. Here is what it does:

### Step 3: MCPManager starts a background thread

```python
def connect(self):
    self._thread = threading.Thread(target=self._run_loop, daemon=True)
    self._thread.start()
    self._ready.wait(timeout=30)
```

Why a background thread? The MCP client library uses `async/await` (Python's way of doing things without blocking). But our agent loop is regular synchronous Python. So the MCPManager creates a background thread that runs an async event loop, and the main thread waits until it is ready.

Think of it like hiring an assistant who speaks a different language. You send requests to the assistant, the assistant translates and does the work, and sends results back.

### Step 4: MCPManager reads mcp_config.json

```python
async def _connect_all(self):
    with open(config_path) as f:
        config = json.load(f)
    
    servers = config.get("mcpServers", {})
    for server_name, server_config in servers.items():
        await self._connect_server(server_name, server_config)
```

It reads the config, loops through each server entry, and connects to each one.

### Step 5: For each server -- start a child process

```python
async def _connect_server(self, name, config):
    params = StdioServerParameters(
        command=command,     # "python" (resolved to the venv python)
        args=config["args"], # ["mcp_servers/billing_tools_server.py"]
        cwd=str(cwd),       # the project root directory
    )
    
    read_stream, write_stream = await self._enter_context(
        name, stdio_client(params)
    )
```

`stdio_client(params)` does this:
1. Starts `python mcp_servers/billing_tools_server.py` as a subprocess
2. Connects to its stdin (to send messages) and stdout (to receive messages)
3. Returns two streams: one for reading, one for writing

The server is now running as a separate process. The agent and server talk by passing text messages (JSON) through stdin/stdout, like two people passing notes.

### Step 6: initialize handshake

```python
session = await self._enter_context(
    name, ClientSession(read_stream, write_stream)
)
init_result = await session.initialize()
```

`session.initialize()` sends this JSON-RPC message to the server:

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "initialize",
  "params": {
    "protocolVersion": "2024-11-05",
    "capabilities": {},
    "clientInfo": {"name": "billing-agent", "version": "1.0.0"}
  }
}
```

The server replies with its own name and capabilities:

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "protocolVersion": "2025-11-25",
    "serverInfo": {"name": "billing-tools"}
  }
}
```

Now both sides know each other and have agreed on the protocol version.

**No AI runs here.** This is just two programs saying hello.

### Step 7: tools/list -- discover what tools the server has

```python
tools_result = await session.list_tools()
```

This sends:

```json
{"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
```

The server replies with its tool catalog -- name, description, and parameter schema for each tool:

```json
{
  "result": {
    "tools": [
      {
        "name": "get_ticket",
        "description": "Look up a support ticket by ticket_id...",
        "inputSchema": {
          "type": "object",
          "properties": {"ticket_id": {"type": "string"}},
          "required": ["ticket_id"]
        }
      },
      ...
    ]
  }
}
```

**No AI runs here either.** This is just the server telling the client its menu.

### Step 8: Convert tool schemas to OpenAI format

The Groq API (which runs our LLM) expects tool schemas in OpenAI format. The MCP SDK returns them in MCP format. The MCPManager converts:

```python
for tool in tools_result.tools:
    schema = {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.input_schema,
        },
    }
    self._tool_schemas.append(schema)
    self._tool_to_server[tool.name] = name    # remember which server owns this tool
```

It also remembers which server each tool belongs to, so later when the LLM says "call get_ticket", the manager knows to send it to the billing-tools server, not ticket-history.

### Step 9: Repeat for every server in the config

Steps 5-8 happen for each server entry in `mcp_config.json`. After both servers are connected:

```
[mcp] Connected to 'billing-tools': 4 tools discovered
  (get_ticket, get_order, get_customer_tier, search_knowledge_base)
[mcp] Connected to 'ticket-history': 2 tools discovered
  (lookup_ticket_history, get_escalation_history)
```

The MCPManager now holds 6 tool schemas, ready to pass to the LLM.

### Step 10: Agent loop runs as normal

From here, the agent loop works the same way it always did:

1. Send user question + discovered tool schemas to the LLM (Groq)
2. LLM decides which tool to call
3. Agent calls `_mcp.dispatch_tool("get_ticket", '{"ticket_id": "T002"}')`
4. MCPManager looks up which server owns "get_ticket" (billing-tools)
5. MCPManager sends a `tools/call` JSON-RPC request to that server
6. Server runs the function and returns the result
7. MCPManager passes the result back to the agent
8. Agent feeds the result to the LLM for the next turn

---

## Part 3: How Each MCP Server Works

### What makes a Python file an MCP server?

Three things:

**1. Import MCPServer and create an instance:**

```python
from mcp.server.mcpserver import MCPServer
mcp = MCPServer("my-server-name")
```

**2. Register tools using the @mcp.tool() decorator:**

```python
@mcp.tool()
def my_tool(some_argument: str) -> str:
    """This description is what the AI reads to decide when to call this tool."""
    result = do_something(some_argument)
    return json.dumps(result)
```

The function name becomes the tool name. The docstring becomes the description. The function parameters become the input schema (the MCP SDK reads the type hints automatically).

**3. Start the server at the bottom:**

```python
if __name__ == "__main__":
    mcp.run(transport="stdio")
```

`mcp.run(transport="stdio")` means: "Listen on stdin for JSON-RPC messages, handle them, and write responses to stdout." The server sits in a loop, waiting for the client to send requests.

### The billing-tools server (mcp_servers/billing_tools_server.py)

This server wraps the 4 existing tools from `agent/tools.py`:

```python
from agent.tools import get_ticket as _get_ticket   # import the existing function

@mcp.tool()
def get_ticket(ticket_id: str) -> str:
    """Look up a support ticket by ticket_id (format: Tnnn, e.g. T002, T008)."""
    result = _get_ticket(ticket_id)        # call the existing function
    return json.dumps(result)              # return the result as a JSON string
```

The wrapper pattern is: import the existing function, wrap it with `@mcp.tool()`, and return `json.dumps(result)`.

### The ticket-history server (mcp_servers/ticket_history_server.py)

This server is standalone -- it has its own data and its own tools:

```python
mcp = MCPServer("ticket-history")

_HISTORY = { "T002": {...}, "T008": {...} }     # data lives here

@mcp.tool()
def lookup_ticket_history(ticket_id: str) -> str:
    """Look up the full lifecycle history of a support ticket."""
    record = _HISTORY.get(ticket_id)
    if record is None:
        return json.dumps({"error": "not_found", "hint": "..."})
    return json.dumps(record)
```

It does not import anything from the main agent. It is completely independent. This is what makes it reusable by other applications.

---

## Part 4: How to Use These Same MCP Servers in Any Other Application

This is the big win of MCP. The servers you built here can be used by ANY application that speaks MCP -- a different Python project, a Node.js app, Claude Desktop, Cursor, or any other MCP-compatible tool.

### Option A: From another Python project

**Step 1:** Install the MCP client library:

```bash
pip install mcp[cli]>=1.0.0
```

**Step 2:** Create a config file (or use the same one):

```json
{
  "mcpServers": {
    "billing-tools": {
      "command": "python",
      "args": ["E:/Python/Project/rag-billing-support/mcp_servers/billing_tools_server.py"]
    },
    "ticket-history": {
      "command": "python",
      "args": ["E:/Python/Project/rag-billing-support/mcp_servers/ticket_history_server.py"]
    }
  }
}
```

Use absolute paths to the server scripts so they work from any directory.

**Step 3:** Connect and use the tools:

```python
import asyncio
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.client.session import ClientSession

async def main():
    # Connect to the billing-tools server
    params = StdioServerParameters(
        command="python",
        args=["E:/Python/Project/rag-billing-support/mcp_servers/billing_tools_server.py"],
    )
    
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            # Step 1: Initialize
            await session.initialize()
            
            # Step 2: Discover tools
            tools = await session.list_tools()
            print(f"Found {len(tools.tools)} tools:")
            for t in tools.tools:
                print(f"  - {t.name}: {t.description[:50]}")
            
            # Step 3: Call a tool
            result = await session.call_tool("get_ticket", {"ticket_id": "T002"})
            print(result.content[0].text)

asyncio.run(main())
```

That is the complete code to connect to your MCP server from any Python project. Three steps: initialize, list tools, call a tool.

**Step 4:** You can also reuse the MCPManager class. Copy `agent/mcp_client.py` into your other project and use it the same way:

```python
from mcp_client import MCPManager

mgr = MCPManager("mcp_config.json")
mgr.connect()

# See what tools are available
print(mgr.tool_count_report())

# Call any tool
result = mgr.dispatch_tool("get_ticket", '{"ticket_id": "T002"}')
print(result)
```

---

### Option B: From Claude Desktop

Claude Desktop has built-in MCP support. You do not need to write any client code.

**Step 1:** Open Claude Desktop settings, find the MCP section, and add the server:

```json
{
  "mcpServers": {
    "billing-tools": {
      "command": "python",
      "args": ["E:/Python/Project/rag-billing-support/mcp_servers/billing_tools_server.py"]
    }
  }
}
```

**Step 2:** Restart Claude Desktop. It will connect to the server, discover the tools, and make them available to Claude. You can then ask Claude "Look up ticket T002" and it will call the `get_ticket` tool automatically.

---

### Option C: From a Node.js / JavaScript project

**Step 1:** Install the MCP client:

```bash
npm install @modelcontextprotocol/sdk
```

**Step 2:** Connect and use:

```javascript
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";

const transport = new StdioClientTransport({
  command: "python",
  args: ["E:/Python/Project/rag-billing-support/mcp_servers/billing_tools_server.py"],
});

const client = new Client({ name: "my-js-app", version: "1.0.0" });
await client.connect(transport);

// Discover tools
const tools = await client.listTools();
console.log("Tools:", tools.tools.map(t => t.name));

// Call a tool
const result = await client.callTool("get_ticket", { ticket_id: "T002" });
console.log(result.content[0].text);
```

Same three steps: connect, list tools, call a tool. Different language, same protocol.

---

### Option D: From any LLM agent (OpenAI, Anthropic, Groq, etc.)

The pattern is always the same:

1. **Connect** to the MCP server (via stdio or HTTP)
2. **Discover** tools using `tools/list`
3. **Convert** the tool schemas to whatever format your LLM expects (OpenAI format, Anthropic format, etc.)
4. **Pass** the schemas to the LLM along with the user's question
5. When the LLM says "call tool X with arguments Y", **send** a `tools/call` request to the server
6. **Feed** the result back to the LLM

This is exactly what our `MCPManager` does. The conversion step (step 3) is the only part that changes between LLM providers.

---

## Part 5: How MCP Works at Runtime (The Full Flow)

Here is the complete picture of what happens when a user asks a question:

```
User: "What is the status of ticket T002?"
        |
        v
[1] Agent sends user question + 6 discovered tool schemas to Groq LLM
        |
        v
[2] LLM reads the tool descriptions and decides: "I need get_ticket"
    LLM outputs: tool_call(name="get_ticket", arguments={"ticket_id": "T002"})
        |
        v
[3] Agent receives the tool_call from the LLM
    Agent asks MCPManager: dispatch_tool("get_ticket", '{"ticket_id": "T002"}')
        |
        v
[4] MCPManager looks up: "get_ticket belongs to billing-tools server"
    MCPManager sends JSON-RPC tools/call to the billing-tools server process
        |
        v
[5] billing-tools server runs the get_ticket() function
    Function queries the database/memory for ticket T002
    Returns: {"ticket_id": "T002", "customer_id": "C102", "text": "..."}
        |
        v
[6] MCPManager receives the result and passes it back to the agent
        |
        v
[7] Agent sends the tool result back to the LLM as a "tool" role message
    LLM reads it and may call more tools or write the final answer
        |
        v
[8] LLM outputs: "Ticket T002 is about a duplicate charge..."
        |
        v
User sees the answer
```

The key insight: the LLM never talks to the MCP server directly. The agent (host) is always the middleman. The LLM makes decisions about which tools to call, and the agent carries out those decisions by talking to the servers.

---

## Part 6: Summary -- The Three Files That Matter

| File | Role | What it does |
|---|---|---|
| `mcp_config.json` | Registry | Lists which servers to connect to. Add a server here = agent discovers its tools automatically |
| `mcp_servers/*.py` | Servers | Expose tools over MCP. Each is a standalone program that any MCP client can connect to |
| `agent/mcp_client.py` | Client bridge | Reads config, connects to servers, discovers tools, converts schemas, routes tool calls |

To add a new tool to your system:
- Add it to an existing server script (or create a new server script)
- If it is a new server, add one entry to `mcp_config.json`
- Agent code does not change

To use your tools from another application:
- Point that application at your server scripts (via config or code)
- The application connects, discovers, and calls tools the same way
- Your server scripts do not change
