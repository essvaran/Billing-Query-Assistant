"""MCP client bridge for the agent loop.

Connects to every server listed in mcp_config.json, discovers tools via
tools/list, and exposes them in OpenAI-compatible format (what Groq expects).
Dispatches tool calls to the correct server via tools/call.

Wire logging: writes raw JSON-RPC exchanges to wire.json when log_wire=True.
"""

import asyncio
import json
import os
import sys
import threading
from pathlib import Path

from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


# Environment variables forwarded to MCP server subprocesses. The MCP SDK gives a
# stdio server only a minimal default environment, so anything a server needs
# (database location, frozen as-of date) must be passed explicitly.
PASSTHROUGH_ENV = ("TIER1_DB_PATH", "CATALOG_DB_PATH", "TIER1_AS_OF", "TIER1_ABLATE", "HF_HOME", "HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE")

# Argument the client injects into every tool that declares it. It carries the
# request trace id across the stdio hop and is hidden from the model.
TRACE_ARG = "trace_id"
PARENT_ARG = "parent_span_id"   # lets the server's span hang under the client's tool span
HIDDEN_ARGS = (TRACE_ARG, PARENT_ARG)


def _schema_of(tool) -> dict:
    """Input JSON schema of an MCP tool, across SDK attribute spellings."""
    schema = getattr(tool, "inputSchema", None) or getattr(tool, "input_schema", None) or {}
    return dict(schema)


class MCPManager:
    """Manages connections to all configured MCP servers.

    Per-server config may carry "allowed_tools": only those tools are exposed to
    the model, so a changed or rogue server cannot add capabilities silently.
    """

    def __init__(self, config_path: str = "mcp_config.json", log_wire: bool = False,
                 tool_timeout: float = 30.0, connect_timeout: float = 30.0):
        self._config_path = config_path
        self._log_wire = log_wire
        self._tool_timeout = tool_timeout
        self._connect_timeout = connect_timeout
        self._wire_log: list[dict] = []
        self._hidden_args: dict[str, set[str]] = {}   # tool -> hidden arguments it declares
        self._blocked_tools: list[str] = []   # discovered but not on the allow-list

        self._tool_schemas: list[dict] = []
        self._tool_to_server: dict[str, str] = {}

        self._sessions: dict[str, ClientSession] = {}
        self._transports: dict[str, tuple] = {}

        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._ready = threading.Event()

        self._exit_stacks: dict[str, list] = {}
        self._connected = False

    def connect(self):
        """Start a background event loop and connect to all MCP servers."""
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        self._ready.wait(timeout=self._connect_timeout)
        if not self._connected:
            self.close()
            raise RuntimeError("Failed to connect to MCP servers within timeout")

    def _run_loop(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._connect_all())

        self._connected = True
        self._ready.set()

        self._loop.run_forever()

    async def _connect_all(self):
        config_path = Path(self._config_path)
        if not config_path.is_absolute():
            config_path = Path(os.getcwd()) / config_path
        with open(config_path) as f:
            config = json.load(f)

        servers = config.get("mcpServers", {})
        for server_name, server_config in servers.items():
            await self._connect_server(server_name, server_config)

    async def _connect_server(self, name: str, config: dict):
        cwd = Path(self._config_path)
        if not cwd.is_absolute():
            cwd = Path(os.getcwd()) / cwd
        cwd = cwd.parent

        command = config["command"]
        if command == "python":
            command = sys.executable

        env = dict(config.get("env") or {})
        for key in PASSTHROUGH_ENV:
            if key in os.environ:
                env.setdefault(key, os.environ[key])

        params = StdioServerParameters(
            command=command,
            args=config.get("args", []),
            env=env or None,
            cwd=str(cwd),
        )

        read_stream, write_stream = await self._enter_context(
            name, stdio_client(params)
        )

        session = await self._enter_context(
            name, ClientSession(read_stream, write_stream)
        )

        init_result = await session.initialize()

        if self._log_wire:
            self._wire_log.append({
                "server": name,
                "step": "initialize",
                "request": {
                    "jsonrpc": "2.0",
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {},
                        "clientInfo": {"name": "billing-agent", "version": "1.0.0"},
                    },
                },
                "response": {
                    "jsonrpc": "2.0",
                    "result": {
                        "protocolVersion": str(getattr(init_result, "protocolVersion", getattr(init_result, "protocol_version", "unknown"))),
                        "serverInfo": {
                            "name": (getattr(init_result, "serverInfo", None) or getattr(init_result, "server_info", None) or type("", (), {"name": name, "version": "unknown"})()).name,
                            "version": (getattr(init_result, "serverInfo", None) or getattr(init_result, "server_info", None) or type("", (), {"name": name, "version": "unknown"})()).version,
                        },
                    },
                },
            })

        tools_result = await session.list_tools()

        if self._log_wire:
            tools_data = []
            for t in tools_result.tools:
                tools_data.append({
                    "name": t.name,
                    "description": t.description or "",
                    "inputSchema": t.input_schema if hasattr(t, "input_schema") else {},
                })
            self._wire_log.append({
                "server": name,
                "step": "tools/list",
                "request": {"jsonrpc": "2.0", "method": "tools/list", "params": {}},
                "response": {"jsonrpc": "2.0", "result": {"tools": tools_data}},
            })

        self._sessions[name] = session

        allowed = config.get("allowed_tools")
        exposed = []
        for tool in tools_result.tools:
            if allowed is not None and tool.name not in allowed:
                self._blocked_tools.append(f"{name}.{tool.name}")
                continue
            params_schema = _schema_of(tool)
            props = dict(params_schema.get("properties") or {})
            declared = {a for a in HIDDEN_ARGS if a in props}
            if declared:
                self._hidden_args[tool.name] = declared
                for a in declared:
                    props.pop(a)
                params_schema["properties"] = props
                params_schema["required"] = [r for r in params_schema.get("required", []) if r not in declared]
            schema = {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description or "",
                    "parameters": params_schema,
                },
            }
            self._tool_schemas.append(schema)
            self._tool_to_server[tool.name] = name
            exposed.append(tool.name)

        print(
            f"  [mcp] Connected to '{name}': {len(exposed)} tools discovered at runtime "
            f"({', '.join(exposed)})"
            + (f"; blocked by allow-list: {', '.join(t.split('.', 1)[1] for t in self._blocked_tools if t.startswith(name + '.'))}"
               if any(t.startswith(name + '.') for t in self._blocked_tools) else ""),
            flush=True,
        )

    async def _enter_context(self, name: str, cm):
        """Enter an async context manager and track it for cleanup."""
        if name not in self._exit_stacks:
            self._exit_stacks[name] = []
        result = await cm.__aenter__()
        self._exit_stacks[name].append(cm)
        return result

    def get_tool_schemas(self) -> list[dict]:
        """Return all discovered tools in OpenAI function-calling format."""
        return self._tool_schemas

    def get_tool_names(self) -> list[str]:
        """Return the names of all discovered tools."""
        return [s["function"]["name"] for s in self._tool_schemas]

    def get_server_for_tool(self, name: str) -> str | None:
        """Return which MCP server owns a given tool name, or None if unknown."""
        return self._tool_to_server.get(name)

    def dispatch_tool(self, name: str, arguments: str, trace_id: str | None = None,
                      parent_span_id: str | None = None) -> str:
        """Call a tool by name and return the JSON result string.

        When trace_id is given and the tool declares a trace_id argument, it is
        injected here, overriding anything the model supplied, so the server-side
        log line carries the id of the request that caused the call.
        """
        if name not in self._tool_to_server:
            available = list(self._tool_to_server.keys())
            return json.dumps({
                "error": f"unknown_tool '{name}' does not exist.",
                "available_tools": available,
                "instruction": f"You must only call one of: {', '.join(available)}. Do not call '{name}' again.",
            })

        try:
            args = json.loads(arguments) if arguments else {}
        except json.JSONDecodeError:
            return json.dumps({"error": f"invalid JSON arguments: {arguments[:100]}"})

        if not isinstance(args, dict):
            return json.dumps({"error": "arguments must be a JSON object"})
        for hidden in HIDDEN_ARGS:
            args.pop(hidden, None)  # never trust a model-supplied trace or span id
        declared = self._hidden_args.get(name, set())
        if trace_id and TRACE_ARG in declared:
            args[TRACE_ARG] = trace_id
        if parent_span_id and PARENT_ARG in declared:
            args[PARENT_ARG] = parent_span_id

        future = asyncio.run_coroutine_threadsafe(
            self._call_tool(name, args), self._loop
        )
        try:
            result = future.result(timeout=self._tool_timeout)
            return result
        except Exception as exc:
            future.cancel()
            return json.dumps({"error": "tool_failure", "detail": type(exc).__name__})

    def is_alive(self) -> bool:
        """True while the background loop that owns the server connections is still running."""
        return bool(self._connected and self._thread and self._thread.is_alive()
                    and self._loop is not None and self._loop.is_running())

    def close(self) -> None:
        """Abandon this manager. Stops its event loop; the server subprocesses exit when their stdin closes."""
        self._connected = False
        if self._loop is not None and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)

    def blocked_tools(self) -> list[str]:
        """Tools the servers offered that the allow-list kept away from the model."""
        return list(self._blocked_tools)

    async def _call_tool(self, name: str, arguments: dict) -> str:
        server_name = self._tool_to_server[name]
        session = self._sessions[server_name]

        result = await session.call_tool(name, arguments)

        result_text = ""
        if result.content:
            parts = []
            for block in result.content:
                if hasattr(block, "text"):
                    parts.append(block.text)
                else:
                    parts.append(str(block))
            result_text = "\n".join(parts)
        else:
            result_text = json.dumps({"result": "ok"})

        if self._log_wire:
            self._wire_log.append({
                "server": server_name,
                "step": "tools/call",
                "request": {
                    "jsonrpc": "2.0",
                    "method": "tools/call",
                    "params": {"name": name, "arguments": arguments},
                },
                "response": {
                    "jsonrpc": "2.0",
                    "result": {
                        "content": [{"type": "text", "text": result_text[:200]}],
                        "isError": getattr(result, "is_error", False),
                    },
                },
            })

        return result_text

    def save_wire_log(self, path: str = "wire.json"):
        """Write captured JSON-RPC exchanges to a file."""
        from src.observability.redact import redact

        with open(path, "w", encoding="utf-8") as f:
            json.dump(redact(self._wire_log), f, indent=2, ensure_ascii=False)
        print(f"  [mcp] Wire log saved to {path}", flush=True)

    def tool_count_report(self) -> str:
        """Return a summary of discovered tool counts and names per server."""
        lines = []
        server_tools: dict[str, list[str]] = {}
        for tool_name, server_name in self._tool_to_server.items():
            server_tools.setdefault(server_name, []).append(tool_name)

        total = len(self._tool_schemas)
        lines.append(f"Total tools discovered: {total}")
        for server, tools in server_tools.items():
            lines.append(f"  {server}: {len(tools)} tools -- {', '.join(tools)}")
        return "\n".join(lines)
