from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

ARTICLES_DIR = PROJECT_ROOT / "data" / "billing_articles"
MARKDOWN_ARTICLES_DIR = PROJECT_ROOT / "data" / "markdown"
CHROMA_DB_DIR = PROJECT_ROOT / "chroma_db"
EVALUATION_DIR = PROJECT_ROOT / "evaluation"
EVIDENCE_CHUNKS_DIR = PROJECT_ROOT / "evidence" / "chunks"

EMBEDDING_MODEL = "BAAI/bge-base-en-v1.5"
TOP_K = 7

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
