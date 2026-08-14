import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from api.models import AskRequest, AskResponse, ChunkResult
from src.generation.answer import answer_question
from src.generation.llm_client import LLMRequestError

app = FastAPI(title="Billing Support RAG API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["POST"],
    allow_headers=["Content-Type"],
)


@app.post("/api/ask", response_model=AskResponse)
def ask(request: AskRequest) -> AskResponse:
    if not request.question.strip():
        raise HTTPException(status_code=400, detail="Question must not be empty.")

    try:
        result = answer_question(request.question)
    except LLMRequestError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    chunks = [
        ChunkResult(
            rank=c["rank"],
            chunk_id=c["chunk_id"],
            article_id=c.get("article_id"),
            section=c.get("section"),
            score=c["score"],
            text=c["text"],
        )
        for c in result.retrieved_chunks
    ]

    return AskResponse(
        answer=result.final_answer,
        chunks=chunks,
        retrieval_ms=round(result.retrieval_ms, 1),
        generation_ms=round(result.generation_ms, 1),
        total_ms=round(result.retrieval_ms + result.generation_ms, 1),
        citations_valid=result.citations_valid,
    )
