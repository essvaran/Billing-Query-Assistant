"""Chat front desk. The chat asks here first, then calls /api/ask (Docs) or /api/tier1/answer (assistant) as told,
so customers never choose a mode. Admins can still force one in the chat for testing.
"""
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from api.auth import UserOut, get_current_user
from api.limiter import limiter, user_or_ip
from src.generation.langfuse_client import get_langfuse
from src.routing.route import RouteDecision, decide_route

log = logging.getLogger("api.chat")
router = APIRouter(prefix="/api/chat", tags=["chat"])


class RouteRequest(BaseModel):
    text: str = Field(..., max_length=4000)
    customer_id: str | None = None


class RouteResponse(BaseModel):
    route: str
    source: str
    reason: str
    needs_account: bool


def _has_account(user: UserOut, customer_id: str | None) -> bool:
    from api.tier1_router import _own_customer, _ready
    from tier1 import db
    _ready()
    if user.role == "admin":
        return bool(customer_id) and db.get_customer(customer_id) is not None
    return _own_customer(user) is not None


def _trace(decision: RouteDecision, text: str, user_email: str) -> None:
    """One small trace per decision, so a misroute can be found next to the answer it caused."""
    lf = get_langfuse()
    if not lf:
        return
    try:
        lf.trace(id=uuid.uuid4().hex, name="route_question", user_id=user_email, input={"question": text},
                 output=decision.as_dict(), tags=[f"route:{decision.route}", f"route_source:{decision.source}"])
    except Exception:
        log.warning("could not record the routing trace")


@router.post("/route", response_model=RouteResponse)
@limiter.limit("30/minute", key_func=user_or_ip)
def route(request: Request, body: RouteRequest, user: UserOut = Depends(get_current_user)) -> RouteResponse:
    text = body.text.strip()
    if not text:
        raise HTTPException(400, "Question must not be empty.")
    decision = decide_route(text, _has_account(user, body.customer_id))
    _trace(decision, text, user.email)
    return RouteResponse(**decision.as_dict())
