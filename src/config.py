from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

ARTICLES_DIR = PROJECT_ROOT / "data" / "billing_articles"
MARKDOWN_ARTICLES_DIR = PROJECT_ROOT / "data" / "markdown"
CHROMA_DB_DIR = PROJECT_ROOT / "chroma_db"
EVALUATION_DIR = PROJECT_ROOT / "evaluation"
EVIDENCE_CHUNKS_DIR = PROJECT_ROOT / "evidence" / "chunks"

EMBEDDING_MODEL = "BAAI/bge-base-en-v1.5"
TOP_K = 3

# Minimum retrieval score to consider a result relevant.
# Queries with no chunk above this threshold get the refusal message.
# Dense  → cosine similarity (0–1); below 0.50 is near-random for this corpus.
# Hybrid → RRF score (max ≈ 0.033 when ranked #1 by both retrievers);
#           below 0.015 means the corpus has essentially nothing on the topic.
MIN_SCORE_DENSE = 0.50
MIN_SCORE_HYBRID = 0.015

# Pre-retrieval gate: cosine similarity between the query embedding and the
# corpus centroid (mean of all indexed chunk embeddings).  Queries below this
# threshold are rejected before any ChromaDB or BM25 call is made.
# Range 0–1; raise to be stricter, lower to be more permissive.
MIN_QUERY_RELEVANCE = 0.20

BASELINE_CHUNK_SIZE = 800
BASELINE_CHUNK_OVERLAP = 100

BASELINE_COLLECTION = "billing_baseline"
STRUCTURE_AWARE_COLLECTION = "billing_structure_aware"
SEMANTIC_COLLECTION = "billing_semantic"

DEFAULT_COLLECTION = STRUCTURE_AWARE_COLLECTION

REQUIRED_METADATA = {
    "source_file",
    "article_id",
    "product_area",
    "last_updated",
}
