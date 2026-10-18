"""The Docs-mode refusal message (catalog prompt docs.refusal) and the openings that identify a refusal."""
from src.catalog import prompts, ref


def refusal_message() -> str:
    return prompts.body("docs.refusal").strip()


def refusal_prefixes() -> tuple[str, ...]:
    """The current message's first sentence plus older wordings (catalog list refusal_prefix), for old traces."""
    current = refusal_message().split(".")[0].strip()
    return tuple(dict.fromkeys([current] + [v["label"] for v in ref.values("refusal_prefix")]))


def is_refusal(answer: str | None) -> bool:
    return (answer or "").strip().startswith(refusal_prefixes())
