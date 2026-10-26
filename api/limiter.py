"""Shared slowapi limiter (kept out of api.main so routers can import it without a cycle).

Behind nginx the client address comes from X-Forwarded-For, which uvicorn trusts only when started with
--proxy-headers and --forwarded-allow-ips (see the Dockerfile). Without that every client shares one bucket.
"""
from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request

limiter = Limiter(key_func=get_remote_address)


def user_or_ip(request: Request) -> str:
    """Key a limit on the signed-in user, so one account cannot use up a limit shared by everyone behind the
    same address, and one address cannot dodge a limit by switching accounts it does not hold. The token
    signature is checked here; an unsigned or expired token falls back to the address."""
    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        import jwt
        from api.auth import JWT_AUDIENCE, JWT_ISSUER
        from api.config import JWT_ALGORITHM, JWT_SECRET
        try:
            payload = jwt.decode(header[7:], JWT_SECRET, algorithms=[JWT_ALGORITHM],
                                 audience=JWT_AUDIENCE, issuer=JWT_ISSUER)
            if payload.get("sub"):
                return "user:" + str(payload["sub"]).lower()
        except jwt.PyJWTError:
            pass
    return "ip:" + get_remote_address(request)
