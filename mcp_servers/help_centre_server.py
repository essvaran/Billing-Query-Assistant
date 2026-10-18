"""MCP server: help-centre search. The capability we EXPOSE to outside clients.

search_help_centre runs hybrid retrieval (BM25 + dense, fused by RRF) over the
Tier-1 collection. Pass policy_version (refund-14d or refund-30d) and results never
include the other refund policy; general articles always pass the filter.

An outside client does not need to know about tracing: trace_id and parent_span_id are optional.

Run standalone for an external MCP client:  python mcp_servers/help_centre_server.py
"""
import json
import sys
import time
from pathlib import Path

_root = str(Path(__file__).resolve().parent.parent)
if _root not in sys.path:
    sys.path.insert(0, _root)

from mcp.server.fastmcp import FastMCP as MCPServer

from src.config import EMBEDDING_MODEL, TIER1_COLLECTION
from src.observability import tracing
from src.retrieval.filters import customer_where
from src.retrieval.hybrid_search import hybrid_search
from tier1 import tracing_store
from tier1.flags import ablated

mcp = MCPServer("help-centre")
tracing_store.install()



def _valid_versions() -> list[str]:
    """Refund policy codes from the catalog list policy_version; empty means no filter."""
    from src.catalog import ref
    return [""] + [c for c in ref.codes("policy_version", include_inactive=True) if c != "none"]


def _snippet_chars() -> int:
    from src.catalog import settings
    return settings.get("tier1.snippet_chars")


@mcp.tool()
def search_help_centre(query: str, policy_version: str = "", top_k: int = 3, include_macros: bool = False,
                       trace_id: str = "", parent_span_id: str = "") -> str:
    """Search the help centre (articles, macros, refund policies, shipping SLA matrix,
    changelog). Each result has a slug, the policy_version it belongs to (refund-14d,
    refund-30d or none), last_updated, and a text snippet. Cite results by chunk_id.
    policy_version: pass the customer's version from check_entitlement so the other
    refund policy is excluded. Leave empty for non-refund questions.
    top_k: number of results (1-5).
    include_macros: internal Zendesk macros are left out by default because they are agent templates, not customer-facing
    documents; set true only to look at them."""
    started = time.perf_counter()
    ok = False
    with tracing.span("server:search_help_centre", "mcp_server", trace_id=trace_id or None,
                      parent_id=parent_span_id or None, server="help-centre", tool="search_help_centre",
                      query_chars=len(query), policy_filter=policy_version or None) as sp:
        if policy_version not in _valid_versions():
            sp.set(ok=False, status="error")
            return json.dumps({"error": "invalid_policy_version", "allowed": _valid_versions()[1:]})
        try:
            with tracing.span("retrieval", "retrieval", embedding_model=EMBEDDING_MODEL, cost_note="local, no API cost") as rs:
                hits = hybrid_search(
                    TIER1_COLLECTION, query, top_n=max(1, min(int(top_k), 5)),
                    where=customer_where(None if ablated("version_filter") else (policy_version or None), include_macros or ablated("macro_filter")),
                )
                rs.set(cost_usd=0.0, results=len(hits))
            results = [
                {
                    "rank": h["rank"],
                    "chunk_id": h["chunk_id"],
                    "slug": h["slug"],
                    "doc_type": h["doc_type"],
                    "policy_version": h["policy_version"],
                    "last_updated": h["last_updated"],
                    "section": h["section"],
                    "score": h["rrf_score"],
                    "text": h["text"][:_snippet_chars()],
                }
                for h in hits
            ]
            payload = {"query": query, "policy_version_filter": policy_version or None, "results": results}
            if not results:
                payload["note"] = "No matching documents. Do not answer from memory; escalate."
            ok = True
            sp.set(ok=True, results=len(results))
        except Exception as exc:  # return failure as data so the agent can escalate
            payload = {"error": "search_failure", "detail": type(exc).__name__}
            sp.set(ok=False, status="error", error=type(exc).__name__)
    print(
        f"[help-centre] trace_id={trace_id or '-'} tool=search_help_centre ok={ok} "
        f"ms={(time.perf_counter() - started) * 1000:.1f}",
        file=sys.stderr, flush=True,
    )
    return json.dumps(payload)


def _warm_up() -> None:
    """Load the embedding model and BM25 index before serving.

    Importing torch and loading the model took up to ~100 s on a cold process.
    Paying that at startup (where the client waits for the handshake) keeps the
    first real search as fast as the rest, and surfaces a broken index at launch.
    """
    from src.retrieval.bm25_search import get_bm25_index
    from src.retrieval.vector_store import get_embeddings

    started = time.perf_counter()
    get_embeddings().embed_query("warm up")
    get_bm25_index(TIER1_COLLECTION)
    print(f"[help-centre] warm-up done in {time.perf_counter() - started:.1f}s", file=sys.stderr, flush=True)


def bearer_guard(app, token: str):
    """ASGI wrapper: every HTTP request needs `Authorization: Bearer <token>`. Lifespan events pass through."""
    import hmac
    expected = f"Bearer {token}".encode()

    async def guarded(scope, receive, send):
        if scope["type"] == "http":
            got = dict(scope.get("headers") or []).get(b"authorization", b"")
            if not hmac.compare_digest(got, expected):
                await send({"type": "http.response.start", "status": 401,
                            "headers": [(b"content-type", b"application/json"), (b"www-authenticate", b"Bearer")]})
                await send({"type": "http.response.body", "body": b'{"error": "missing or wrong bearer token"}'})
                return
        await app(scope, receive, send)
    return guarded


def main(argv: list[str] | None = None) -> int:
    import argparse
    import os
    ap = argparse.ArgumentParser(description="Help-centre MCP server")
    ap.add_argument("--transport", choices=["stdio", "http"], default="stdio",
                    help="stdio (default) for a client that starts this process; http so a client on another machine can connect")
    ap.add_argument("--host", default="127.0.0.1", help="http only; use 0.0.0.0 to accept other machines")
    ap.add_argument("--port", type=int, default=8765, help="http only")
    args = ap.parse_args(argv)

    if args.transport == "stdio":
        _warm_up()
        mcp.run(transport="stdio")
        return 0

    from dotenv import load_dotenv
    load_dotenv(Path(_root) / ".env", override=False)
    token = os.getenv("MCP_HTTP_TOKEN", "").strip()
    if len(token) < 16:
        print("MCP_HTTP_TOKEN must be set (16+ characters) before serving over HTTP: anyone who can reach the port could "
              "otherwise search the help centre.\nCreate one with: python -c \"import secrets; print(secrets.token_urlsafe(24))\"",
              file=sys.stderr)
        return 2
    import uvicorn
    _warm_up()
    print(f"[help-centre] serving MCP over streamable HTTP at http://{args.host}:{args.port}/mcp (bearer token required)",
          file=sys.stderr, flush=True)
    uvicorn.run(bearer_guard(mcp.streamable_http_app(), token), host=args.host, port=args.port, log_level="warning")
    return 0


if __name__ == "__main__":
    sys.exit(main())
