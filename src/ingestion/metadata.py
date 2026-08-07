from src.config import REQUIRED_METADATA


def validate_metadata(metadata: dict) -> None:
    missing = [field for field in REQUIRED_METADATA if not metadata.get(field)]

    if missing:
        raise ValueError(f"Missing required metadata: {', '.join(missing)}")
