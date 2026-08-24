"""Replay a single trace from evaluation/traces.jsonl using only its stored fields.

Fetches chunk text from ChromaDB by chunk_id, rebuilds the exact prompt,
re-calls the LLM with the same model and temperature, and prints
the original raw_output alongside the replayed output.

Usage:
    python scripts/replay_trace.py --trace-id <uuid>
    python scripts/replay_trace.py --trace-id <uuid> --jsonl path/to/traces.jsonl
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.generation.llm_client import ask_llm
from src.generation.prompts import SYSTEM_PROMPT, build_user_prompt
from src.retrieval.vector_store import get_collection

_DEFAULT_TRACES = Path(__file__).resolve().parents[1] / "evaluation" / "traces.jsonl"


def load_trace(trace_id: str, jsonl_path: Path) -> dict:
    with jsonl_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            if record.get("trace_id") == trace_id:
                return record
    raise ValueError(f"trace_id '{trace_id}' not found in {jsonl_path}")


def fetch_chunks_by_id(chunk_ids: list[str], collection_name: str) -> list[dict]:
    """Fetch chunk text and metadata from ChromaDB by chunk ID."""
    collection = get_collection(collection_name)
    result = collection.get(ids=chunk_ids, include=["documents", "metadatas"])
    chunks = []
    for rank, (cid, doc, meta) in enumerate(
        zip(result["ids"], result["documents"], result["metadatas"]), start=1
    ):
        chunks.append(
            {
                "rank": rank,
                "chunk_id": cid,
                "article_id": meta.get("article_id"),
                "section": meta.get("section"),
                "score": 0.0,  # score not stored per-chunk in replay; use 0 as sentinel
                "text": doc,
            }
        )
    return chunks


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay a stored trace.")
    parser.add_argument("--trace-id", required=True, help="UUID of the trace to replay")
    parser.add_argument(
        "--jsonl",
        default=str(_DEFAULT_TRACES),
        help="Path to traces.jsonl (default: evaluation/traces.jsonl)",
    )
    args = parser.parse_args()

    jsonl_path = Path(args.jsonl)
    if not jsonl_path.exists():
        print(f"ERROR: traces file not found at {jsonl_path}", file=sys.stderr)
        sys.exit(1)

    print(f"Loading trace {args.trace_id} …")
    trace = load_trace(args.trace_id, jsonl_path)

    print(f"\n{'='*70}")
    print(f"TRACE METADATA")
    print(f"{'='*70}")
    print(f"  trace_id     : {trace['trace_id']}")
    print(f"  timestamp    : {trace['timestamp']}")
    print(f"  question     : {trace['question']}")
    print(f"  model        : {trace['model']}")
    print(f"  temperature  : {trace['temperature']}")
    print(f"  prompt_ver   : {trace['prompt_version']}")
    print(f"  retriever    : {trace['retriever']}")
    print(f"  collection   : {trace['collection']}")
    print(f"  top_k        : {trace['top_k']}")
    print(f"  citations_v  : {trace['citations_valid']}")

    chunk_ids = [c["chunk_id"] for c in trace["retrieved_chunks"]]
    print(f"\nFetching {len(chunk_ids)} chunk(s) from ChromaDB …")
    try:
        chunks = fetch_chunks_by_id(chunk_ids, trace["collection"])
    except Exception as exc:
        print(f"WARNING: could not fetch chunks ({exc}). Replay may differ.")
        chunks = []

    print(f"\n{'='*70}")
    print("ORIGINAL raw_output")
    print(f"{'='*70}")
    print(trace["raw_output"])

    if chunks:
        print(f"\n{'='*70}")
        print("REPLAYED output  (re-calling LLM with stored prompt + temperature)")
        print(f"{'='*70}")
        user_prompt = build_user_prompt(trace["question"], chunks)
        replayed_text, in_tok, out_tok = ask_llm(SYSTEM_PROMPT, user_prompt)
        print(replayed_text)
        print(f"\n  input_tokens={in_tok}  output_tokens={out_tok}")
    else:
        print("\nSkipping replay — no chunks retrieved.")

    print(f"\n{'='*70}")
    print("NOTES")
    print(f"{'='*70}")
    print("  Fields present in trace: trace_id, timestamp, question, model,")
    print("  temperature, prompt_version, retriever, collection, top_k,")
    print("  retrieved_chunks (chunk_id + rank + score), raw_output,")
    print("  final_answer, citations, citations_valid, retrieval_ms,")
    print("  generation_ms, total_ms, input_tokens, output_tokens, error.")
    print()
    print("  Fields NOT stored (cannot reconstruct):")
    print("  - Chunk text (fetched live from ChromaDB — may change if re-ingested)")
    print("  - Exact system prompt text (prompt_version='v1' is stored, but")
    print("    the prompt content is read from the current prompts.py)")


if __name__ == "__main__":
    main()
