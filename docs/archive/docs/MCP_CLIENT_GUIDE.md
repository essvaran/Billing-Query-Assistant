# Calling the help-centre MCP server from your own client

This is for a reviewer from another squad. You should not need to ask the author anything. If you do, that is a
finding: write down where you stumbled in `deliverables/week12/fresh_eyes.md`.

All content is SYNTHETIC. The server exposes one tool, `search_help_centre`, over hybrid search (keyword plus
embeddings) of the Tier-1 help centre. No API key is needed for search; only the assistant itself calls a language
model.

There are two ways in. Pick one:

- **A. Over HTTP** (nothing to install on your side except your MCP client). The author starts the server and gives
  you a URL and a token.
- **B. Over stdio** (you clone the repository and your client starts the server as a local process).

## A. Over HTTP

### A1. The author starts the server

```bash
make mcp-http
```

(Windows: `./tasks.ps1 mcp-http`; or `python mcp_servers/help_centre_server.py --transport http`.)

It needs `MCP_HTTP_TOKEN` in `.env` (16 or more random characters; create one with
`python -c "import secrets; print(secrets.token_urlsafe(24))"`). Without it the server refuses to start. It loads the
embedding model first (about 10 seconds), then prints the address: `http://127.0.0.1:8765/mcp`.

- Same machine: use that address.
- Another machine on the same network: start it with `--host 0.0.0.0` and use the author's IP address.
- Over the internet: `ngrok http 8765` gives a public https address; use `https://<id>.ngrok-free.app/mcp`. The token
  still protects it. Stop the tunnel when the review ends.

Every request must carry the header `Authorization: Bearer <token>`. Without it the server answers 401.

### A2. Connect with MCP Inspector

```bash
npx @modelcontextprotocol/inspector
```

In the page that opens: Transport **Streamable HTTP**, URL as above, and under Authentication set the bearer token.
Click **Connect**, then **Tools**, **List Tools**, choose `search_help_centre`, fill in a query and **Run Tool**.

### A3. Connect with Claude Code or Claude Desktop

```bash
claude mcp add --transport http help-centre http://127.0.0.1:8765/mcp --header "Authorization: Bearer <token>"
```

Then ask: "Use the help-centre tool to find how many days a 30-day-policy customer has to request a refund."

For Claude Desktop, add a remote MCP server (Settings, Connectors) with the same URL and header if your version
supports custom headers; otherwise use way B.

### A4. Connect with ten lines of Python

```python
import asyncio
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

async def main():
    async with streamablehttp_client("http://127.0.0.1:8765/mcp", headers={"Authorization": "Bearer <token>"}) as (r, w, _):
        async with ClientSession(r, w) as s:
            await s.initialize()
            print([t.name for t in (await s.list_tools()).tools])
            res = await s.call_tool("search_help_centre", {"query": "refund window", "policy_version": "refund-30d"})
            print(res.content[0].text)

asyncio.run(main())
```

This is exactly what `tests/test_mcp_http.py` does.

## B. Over stdio

### B1. One-time setup (about 5 minutes, mostly the model download)

```bash
git clone <repo> && cd <repo>
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python scripts/generate_synthetic_corpus.py
python scripts/ingest_variant_a.py                    # builds the search index (downloads an embedding model once)
```

### B2. Prove the server works without any client

```bash
python scripts/mcp_smoke.py
```

Expected: both servers list their tools and one real call each returns `ok`.

### B3. Add it to your MCP client

```json
{
  "mcpServers": {
    "help-centre": {
      "command": "python",
      "args": ["mcp_servers/help_centre_server.py"],
      "cwd": "/absolute/path/to/the/repo"
    }
  }
}
```

The first start takes about 10 seconds: it loads the embedding model before it answers the handshake. A client with a
short startup timeout may report a failure; raise the timeout.

## The one tool

`search_help_centre(query, policy_version?, top_k?, include_macros?)`

| Argument | Meaning |
|---|---|
| `query` | what to search for, in natural language. Put an error code in exactly as written (for example `ERR-4032`). |
| `policy_version` | `refund-14d` or `refund-30d`. If given, results never include the other refund policy. Leave empty for non-refund questions. |
| `top_k` | 1 to 5 results (default 3) |
| `include_macros` | internal agent templates are hidden by default; true includes them |

The result is JSON: `query`, `policy_version_filter`, and `results`, each with `chunk_id`, `slug`, `policy_version`
(`refund-14d`, `refund-30d` or `none`), `doc_type`, `last_updated`, `section`, a relevance `score` and a text snippet.
An empty result carries a `note` telling the caller not to answer from memory. Try:

- `query: "how many days do I have to request a refund"`, `policy_version: "refund-30d"`: only 30-day policy text comes back.
- the same query with `policy_version: "refund-14d"`: only the retired 14-day text, and `last_updated` shows 2025-01-10.
- the same query with no `policy_version`: both versions appear. That is the situation the assistant avoids.
- an invalid `policy_version` such as `refund-7d`: an `invalid_policy_version` error listing the allowed values.

## What to tell the author

Open `deliverables/week12/fresh_eyes.md` and fill in: who you are, which squad, which client and which way (A or B)
you used, each place you hesitated or had to guess, and how long it took to get a first result.
