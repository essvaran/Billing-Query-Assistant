from typing import Optional

from pydantic import BaseModel, ConfigDict


class AskRequest(BaseModel):
    question: str
    use_hybrid: bool = True


class ChunkResult(BaseModel):
    rank: int
    chunk_id: str
    article_id: str | None
    section: str | None
    score: float
    text: str


class AskResponse(BaseModel):
    answer: str
    chunks: list[ChunkResult]
    retrieval_ms: float
    generation_ms: float
    total_ms: float
    citations_valid: bool
    retriever: str
    trace_id: str | None = None


class TraceChunk(BaseModel):
    model_config = ConfigDict(extra="ignore")

    chunk_id: str
    document_id: Optional[str] = None
    score: float = 0.0
    rank: int = 0


class TraceRecord(BaseModel):
    model_config = ConfigDict(extra="ignore")

    trace_id: str
    timestamp: str
    question: str
    query_type: Optional[str] = None
    original_query: Optional[str] = None
    rewritten_query: Optional[str] = None
    prompt_version: str = "v1"
    model: str = ""
    temperature: float = 0.0
    retriever: str = ""
    top_k: int = 0
    collection: str = ""
    retrieved_chunks: list[TraceChunk] = []
    raw_output: str = ""
    final_answer: str = ""
    citations: list[str] = []
    citations_valid: bool = False
    retrieval_ms: float = 0.0
    generation_ms: float = 0.0
    total_ms: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    error: Optional[str] = None


class TracesResponse(BaseModel):
    traces: list[TraceRecord]
    total: int
    offset: int
    limit: int


class TracePrompt(BaseModel):
    trace_id: str
    query_type: str
    system_prompt: str
    user_prompt: str


class ReplayChunk(BaseModel):
    chunk_id: str
    article_id: Optional[str]
    section: Optional[str]
    text: str


class UploadResponse(BaseModel):
    filename: str
    chunks_indexed: int
    collection: str
    status: str


class ReplayResult(BaseModel):
    trace_id: str
    question: str
    original_model: str       # model stored in the trace
    replay_model: str         # model actually used during replay
    model_matched: bool       # True when both models are the same
    original_raw_output: str
    original_citations: list[str]
    original_citations_valid: bool
    replayed_raw_output: str
    replayed_citations: list[str]
    replayed_citations_valid: bool
    chunks_used: list[ReplayChunk]
    chunks_available: bool
    replayed_input_tokens: int
    replayed_output_tokens: int
    outputs_match: bool
