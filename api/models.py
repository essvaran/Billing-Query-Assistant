from pydantic import BaseModel


class AskRequest(BaseModel):
    question: str


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
