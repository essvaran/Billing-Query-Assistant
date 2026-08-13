# Code Review: RAG Billing Support Project

## Summary

A well-structured RAG pipeline with three chunking strategies, semantic search, LLM-powered Q&A, and filtering capabilities. However, several gaps exist in error handling, test coverage, input validation, and documentation.

---

## 🚩 Critical Gaps

### 1. **Untracked/Unstaged Files** (BLOCKING)

- ❌ `tests/test_ask.py` - **Completely untracked** - will be lost if not added to git
- ❌ 5 modified files **not staged**:
  - `scripts/ask.py` (new features: filtering, parser refactoring)
  - `src/config.py` (TOP_K: 5→7)
  - `src/ingestion/loader.py` (multi-format support: .docx, .pdf)
  - `tests/test_metadata.py` (updates)
  - `tests/test_structure_chunker.py` (updates)

**Action Required:** Stage or commit all changes before pushing.

---

## ⚠️ High-Priority Gaps

### 2. **Missing Error Handling in Main Scripts**

**Files affected:** `scripts/ingest_articles.py`, `scripts/run_evaluation.py`, `scripts/run_filter_demo.py`, `scripts/run_search.py`

```python
# ❌ Current: No error handling
def main() -> None:
    articles = load_articles(ARTICLES_DIR)  # Could fail
    chunks = baseline_chunk_articles(articles)  # Could fail
```

**Should add:**

- Try-except for file I/O operations
- Try-except for embedding/vector store failures
- Graceful degradation or clear error messages

---

### 3. **Incomplete Test Coverage**

**Tests exist for:**

- ✅ Metadata validation
- ✅ Bootstrap script
- ✅ Structure chunker

**Tests missing for:**

- ❌ Semantic chunking (`src/chunking/semantic.py`)
- ❌ Baseline chunking (`src/chunking/baseline.py`)
- ❌ LLM client error handling & edge cases
- ❌ Citation extraction/validation edge cases
- ❌ Retrieval search with filters
- ❌ Vector store operations
- ❌ End-to-end Q&A pipeline
- ❌ Integration tests

**Example test gaps:**

```python
# Missing: semantic chunking tests
# Missing: what if all sentences are < 15 chars?
# Missing: embedding API timeout scenarios
# Missing: malformed citations in LLM responses
```

---

### 4. **No Input Validation**

**In `scripts/ask.py`:**

```python
# ❌ No validation that collection exists
collection = _STRATEGIES[args.strategy]

# ❌ No validation that filter value is valid
where = {"product_area": args.filter_product_area}

# ❌ Empty questions are silently skipped
question = input("> ").strip()
if not question:
    continue  # No logging, no feedback
```

**Should add:**

- Validate collection exists before querying
- Validate filter values against known metadata values
- Provide user feedback for invalid inputs
- Empty question warning/logging

---

### 5. **Multi-Format Support Added But Not Validated**

**`src/ingestion/loader.py` now supports:** `.md`, `.txt`, `.docx`, `.pdf`

**Problems:**

- ❌ `python-docx` and `PyPDF2` not in `requirements.txt` (only caught at runtime)
- ❌ No tests for `.docx` or `.pdf` loading
- ❌ Generic exception handling masks real errors:
  ```python
  try:
      import docx
  except Exception:  # Catches ImportError, but also catches real errors
      docx = None
  ```
- ❌ No validation that extracted text is non-empty
- ❌ PDF extraction could produce garbage for scanned PDFs

**Action Required:**

- Add `python-docx` and `PyPDF2` to `requirements.txt` (or move to optional)
- Add unit tests for each format
- Better error messages

---

### 6. **Configuration Issues**

**`src/config.py`:**

```python
# ❌ TOP_K changed from 5 to 7 but no comment explaining why
TOP_K = 7

# ❌ No validation these directories exist
CHROMA_DB_DIR = PROJECT_ROOT / "chroma_db"
ARTICLES_DIR = PROJECT_ROOT / "data" / "billing_articles"
```

**`.env.example` missing:**

- ❌ `LLM_MODEL` defaults documented but not parameterized consistently
- ❌ No guidance on groq.com API key creation beyond link

---

## 🟡 Medium-Priority Gaps

### 7. **No Logging System**

**Current state:** Silent failures or print() only

```python
# ❌ No way to debug production issues
print(f"Loaded articles: {len(articles)}")  # Hard to parse programmatically

# ❌ No logging levels
# ❌ No timestamped logs
# ❌ No error tracing
```

**Should implement:**

```python
import logging

logger = logging.getLogger(__name__)
logger.info(f"Loaded {len(articles)} articles")
logger.error(f"Failed to load articles: {exc}", exc_info=True)
```

---

### 8. **Missing Docstrings & Type Hints**

**Functions without docstrings:**

- `src/retrieval/vector_store.py`: `get_embeddings()`, `get_client()`, `build_collection()`
- `src/generation/llm_client.py`: `_ask_groq()`, `_ask_ollama()`
- `src/chunking/semantic.py`: Most helper functions
- `scripts/ask.py`: `_print_results()`, `build_parser()`

**Missing type hints:**

- Return types often omitted
- Parameter types incomplete in some functions

---

### 9. **Semantic Chunker Edge Cases**

**`src/chunking/semantic.py`:**

```python
def _split_sentences(text: str) -> list[str]:
    parts = _SENT_RE.split(text)
    return [p.strip() for p in parts if len(p.strip()) > 15]
    # ⚠️ What if ALL sentences are < 15 chars?
    # ⚠️ What if text has no sentence boundaries?

# Returns single chunk with full content, but what about very short articles?
if len(sentences) <= 1:
    return [_make_chunk([article.content.strip()], article, 1)]
```

---

### 10. **Citation Extraction May Be Too Strict**

**`src/generation/citations.py`:**

```python
_CITATION_RE = re.compile(r"\[([A-Za-z0-9]+(?:-[A-Za-z0-9]+)*--[A-Za-z0-9-]+--[A-Za-z0-9-]+)\]")
# Requires format: [base-identifier--section-title--subsection]
# ⚠️ What if LLM uses [chunk_id] format instead?
# ⚠️ What if whitespace is added: [ chunk_id ]?
# ⚠️ Regex is brittle - no tests for malformed inputs
```

---

### 11. **Thread Safety Concerns**

**`src/retrieval/vector_store.py`:**

```python
_embeddings = None

def get_embeddings() -> HuggingFaceEmbeddings:
    global _embeddings
    if _embeddings is None:
        _embeddings = HuggingFaceEmbeddings(...)
    return _embeddings
    # ⚠️ Not thread-safe if multiple threads call simultaneously
    # ⚠️ No timeout for embedding model download/initialization
```

---

### 12. **No Collection Existence Check**

**`src/retrieval/search.py`:**

```python
def search(collection_name: str, query: str, k: int = TOP_K, where: dict | None = None) -> list[dict]:
    collection = get_collection(collection_name)  # Silently fails if collection doesn't exist
    # ⚠️ Should validate collection exists and provide clear error
```

---

## 🟢 Low-Priority Gaps

### 13. **Missing .gitignore / Environment Setup**

- ❌ `.gitignore` not shown - should exclude `.env`, `chroma_db/`, `*.pth`
- ❌ No `setup.py` or `pyproject.toml` (though may not be necessary)

---

### 14. **Performance Metrics**

**Currently:**

- ✅ Timing data collected in `Answer` dataclass
- ❌ But no aggregation/reporting of performance across runs
- ❌ No memory profiling for embedding operations

---

### 15. **Bonus Question Logic**

**`scripts/run_generation_tests.py`:**

```python
# Q4 is the best bonus candidate...
BONUS_QUESTION = "How do I fix ERR-6030?"
# ⚠️ Hard-coded for Q4 - if questions.json structure changes, breaks silently
```

---

## ✅ Things Done Well

1. **Clear module separation** - chunking, ingestion, retrieval, generation are well organized
2. **Three chunking strategies** - good experiment design
3. **Metadata validation** - caught missing fields early
4. **Filter support** - clean architecture for metadata filtering
5. **Citation validation** - prevents hallucination by validating sources
6. **Graceful degradation** - optional docx/pdf support doesn't break if missing
7. **Multiple LLM backends** - groq + ollama support is flexible
8. **Error classes** - `LLMRequestError` for clear error handling

---

## 📋 Action Checklist

### Must Do (Before Committing)

- [ ] Stage all unstaged files: `git add scripts/ask.py src/config.py src/ingestion/loader.py tests/test_*.py`
- [ ] Track `tests/test_ask.py`: `git add tests/test_ask.py`

### Should Do (High Priority)

- [ ] Add `python-docx` and `PyPDF2` to `requirements.txt`
- [ ] Add error handling to main scripts (try-except + logging)
- [ ] Add unit tests for semantic chunking
- [ ] Add input validation to `ask.py` (collection exists, filter validation)
- [ ] Add collection existence check to `search.py`

### Nice to Have (Medium Priority)

- [ ] Add logging system
- [ ] Add docstrings to key functions
- [ ] Make embedding initialization thread-safe
- [ ] Add integration tests
- [ ] Add edge case tests for semantic chunker

### Polish (Low Priority)

- [ ] Performance profiling & reporting
- [ ] Additional citation format robustness
- [ ] `pyproject.toml` for better packaging

---

## Summary Statistics

| Category           | Count     | Status               |
| ------------------ | --------- | -------------------- |
| Modules            | 11        | ✅ Good structure    |
| Test files         | 4         | ⚠️ Low coverage      |
| Main scripts       | 6         | ⚠️ No error handling |
| Unstaged files     | 5         | ❌ MUST STAGE        |
| Untracked files    | 1         | ❌ MUST ADD          |
| Missing docstrings | ~15       | ⚠️ Should add        |
| Missing tests      | ~8 topics | ⚠️ Should add        |
