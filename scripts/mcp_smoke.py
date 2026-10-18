"""Smoke test for the Tier-1 MCP servers, from a client that is not the agent.

Starts each server over stdio, lists its tools (runtime discovery), and makes one
real call per server. This is also what an outside reviewer's MCP client does.

Run:  python scripts/mcp_smoke.py
"""
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

TIMEOUT_S = 240  # first search loads the embedding model

CALLS = {
    "tier1_tools_server.py": ("check_entitlement", {"customer_id": "C1000", "order_id": "O2000", "trace_id": "smoke-001"}),
    "help_centre_server.py": ("search_help_centre", {"query": "how many days do I have to request a refund",
                                                       "policy_version": "refund-30d", "trace_id": "smoke-001"}),
}


async def probe(script: str) -> bool:
    params = StdioServerParameters(command=sys.executable, args=[f"mcp_servers/{script}"], cwd=str(ROOT))
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = (await session.list_tools()).tools
            print(f"{script}: discovered {[t.name for t in tools]}", flush=True)
            name, args = CALLS[script]
            result = await session.call_tool(name, args)
            text = "\n".join(getattr(b, "text", str(b)) for b in result.content)
            data = json.loads(text)
            ok = "error" not in data
            print(f"  call {name} -> {'ok' if ok else 'ERROR'}: {text[:160]}", flush=True)
            return ok


async def main() -> int:
    results = [await asyncio.wait_for(probe(s), timeout=TIMEOUT_S) for s in CALLS]
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
