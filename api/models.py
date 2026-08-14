from pydantic import BaseModel


class AskRequest(BaseModel):
    question: str
    use_hybrid: bool = False


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
