from dataclasses import dataclass
from typing import Any


@dataclass
class Chunk:
    page_content: str
    metadata: dict[str, Any]
