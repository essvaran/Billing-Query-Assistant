"""Shared slowapi limiter (kept out of api.main so routers can import it without a cycle)."""
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
