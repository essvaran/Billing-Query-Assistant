"""User-facing feedback endpoint: thumbs up or down on an answer. Any signed-in user may call it."""
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.auth import UserOut, get_current_user
from src.observability.feedback import FeedbackError, reasons as feedback_reasons, submit_and_notify

router = APIRouter(prefix="/api/feedback", tags=["feedback"])


class FeedbackIn(BaseModel):
    trace_id: str = Field(min_length=1, max_length=64)
    rating: Literal["up", "down"]
    reason_code: Optional[str] = Field(default=None, max_length=40)
    comment: Optional[str] = Field(default=None, max_length=20000)   # the real limit is the setting feedback.max_comment


@router.get("/reasons")
def list_reasons(_user: UserOut = Depends(get_current_user)):
    return [{"code": code, "label": label} for code, label in feedback_reasons().items()]


@router.post("", status_code=201)
def create_feedback(body: FeedbackIn, user: UserOut = Depends(get_current_user)):
    try:
        result = submit_and_notify(body.trace_id, user.email, body.rating, body.reason_code, body.comment)
    except FeedbackError as exc:
        raise HTTPException(status_code=exc.status, detail=exc.message)
    return {"saved": True, "rating": result["rating"]}
