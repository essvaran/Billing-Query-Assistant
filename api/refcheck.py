"""Request validation against catalog reference lists (Admin, Reference data) instead of hard-coded enums."""
from typing import Annotated

from pydantic import AfterValidator


def _checker(category: str):
    def check(value):
        if value is None:
            return value
        from src.catalog import ref
        if value not in ref.codes(category):
            raise ValueError(f"must be one of {ref.codes(category)}")
        return value
    return check


def RefCode(category: str):
    """Annotated str type: the value must be an active code of the catalog list `category`."""
    return Annotated[str, AfterValidator(_checker(category))]


def setting(key: str):
    """default_factory for a field whose default is a setting."""
    def factory():
        from src.catalog import settings
        return settings.get(key)
    return factory
