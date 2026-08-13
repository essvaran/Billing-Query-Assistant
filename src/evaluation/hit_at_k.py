def evidence_present(text: str, required_evidence_terms: list[str]) -> bool:
    lower_text = text.lower()
    return all(term.lower() in lower_text for term in required_evidence_terms)


def hit_at_5(question: dict, results: list[dict]) -> tuple[bool, int | None]:
    required_evidence_terms = question["required_evidence_terms"]

    for result in results[:5]:
        if evidence_present(result["text"], required_evidence_terms):
            return True, result["rank"]

    return False, None
