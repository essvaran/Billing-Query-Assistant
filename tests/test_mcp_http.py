"""The help-centre MCP server over HTTP, as a client on another machine would reach it: no token, no access."""
import asyncio
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

from tier1 import preflight

ROOT = Path(__file__).resolve().parent.parent
TOKEN = "test-token-0123456789abcdef"

pytestmark = pytest.mark.skipif(preflight.collection_size() == 0, reason="needs the search index (make up)")


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def server():
    port = _free_port()
    env = {**os.environ, "MCP_HTTP_TOKEN": TOKEN}
    proc = subprocess.Popen([sys.executable, "mcp_servers/help_centre_server.py", "--transport", "http", "--port", str(port)],
                            cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = f"http://127.0.0.1:{port}/mcp"
    deadline = time.monotonic() + 240
    while time.monotonic() < deadline:
        try:
            httpx.get(url, timeout=2)
            break
        except httpx.HTTPError:
            if proc.poll() is not None:
                pytest.fail("server exited during start-up")
            time.sleep(1)
    yield url
    proc.terminate()
    proc.wait(timeout=20)


def test_refuses_to_serve_http_without_a_token():
    env = {k: v for k, v in os.environ.items() if k != "MCP_HTTP_TOKEN"}
    env["MCP_HTTP_TOKEN"] = ""
    r = subprocess.run([sys.executable, "mcp_servers/help_centre_server.py", "--transport", "http", "--port", str(_free_port())],
                       cwd=ROOT, env=env, capture_output=True, text=True, timeout=120)
    assert r.returncode == 2 and "MCP_HTTP_TOKEN" in r.stderr


def test_requests_without_the_token_get_401(server):
    assert httpx.post(server, json={}, timeout=10).status_code == 401
    assert httpx.post(server, json={}, headers={"Authorization": "Bearer wrong"}, timeout=10).status_code == 401


def test_a_client_with_the_token_discovers_and_calls_search(server):
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    async def go():
        async with streamablehttp_client(server, headers={"Authorization": f"Bearer {TOKEN}"}) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = [t.name for t in (await session.list_tools()).tools]
                result = await session.call_tool("search_help_centre",
                                                 {"query": "how many days to request a refund", "policy_version": "refund-30d"})
                return tools, result.content[0].text

    tools, text = asyncio.run(go())
    assert tools == ["search_help_centre"]
    assert '"policy_version_filter": "refund-30d"' in text and "refund-14d" not in text.split('"results"')[1]
