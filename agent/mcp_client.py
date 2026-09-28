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


class MCPManager:
    """Manages connections to all configured MCP servers."""

    def __init__(self, config_path: str = "mcp_config.json", log_wire: bool = False):
        self._config_path = config_path
        self._log_wire = log_wire
        self._wire_log: list[dict] = []

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
        self._ready.wait(timeout=30)
        if not self._connected:
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

        params = StdioServerParameters(
            command=command,
            args=config.get("args", []),
            env=config.get("env"),
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
                        "protocolVersion": str(init_result.protocol_version),
                        "serverInfo": {
                            "name": init_result.server_info.name if init_result.server_info else name,
                            "version": init_result.server_info.version if init_result.server_info else "unknown",
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

        for tool in tools_result.tools:
            schema = {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description or "",
                    "parameters": tool.input_schema if hasattr(tool, "input_schema") else {},
                },
            }
            self._tool_schemas.append(schema)
            self._tool_to_server[tool.name] = name

        print(
            f"  [mcp] Connected to '{name}': "
            f"{len(tools_result.tools)} tools discovered "
            f"({', '.join(t.name for t in tools_result.tools)})",
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

    def dispatch_tool(self, name: str, arguments: str) -> str:
        """Call a tool by name and return the JSON result string."""
        if name not in self._tool_to_server:
            return json.dumps({"error": f"unknown_tool: {name}"})

        try:
            args = json.loads(arguments) if arguments else {}
        except json.JSONDecodeError:
            return json.dumps({"error": f"invalid JSON arguments: {arguments[:100]}"})

        future = asyncio.run_coroutine_threadsafe(
            self._call_tool(name, args), self._loop
        )
        try:
            result = future.result(timeout=30)
            return result
        except Exception as exc:
            return json.dumps({"error": str(exc)})

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
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self._wire_log, f, indent=2, ensure_ascii=False)
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
