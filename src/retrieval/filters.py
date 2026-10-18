from src.retrieval.search import search


def compare_filtered_vs_unfiltered(
    collection_name: str, query: str, product_area: str
) -> dict:
    unfiltered_results = search(collection_name, query)
    filtered_results = search(
        collection_name, query, where={"product_area": product_area}
    )

    top1_changed = (
        not unfiltered_results
        or not filtered_results
        or unfiltered_results[0]["chunk_id"] != filtered_results[0]["chunk_id"]
    )

    return {
        "query": query,
        "product_area_filter": product_area,
        "unfiltered_results": unfiltered_results,
        "filtered_results": filtered_results,
        "top1_changed": top1_changed,
    }


# --- metadata filters shared by dense (Chroma) and BM25 retrieval -------------
#
# A "flat where" is a dict of {field: value} or {field: {"$in": [values]}}.
# Dense search converts it to a Chroma where clause; BM25 applies it in Python,
# so both retrievers always see the same candidate set.

NO_POLICY = "none"


def policy_where(policy_version: str | None) -> dict | None:
    """Filter that keeps general content plus ONLY the given refund-policy version.

    Chunks of articles and macros carry policy_version "none" and always pass; a
    policy or macro tagged with another version is excluded, so a customer on the
    30-day policy can never be shown the retired 14-day text.
    """
    if not policy_version or policy_version == NO_POLICY:
        return None
    return {"policy_version": {"$in": [policy_version, NO_POLICY]}}


def customer_where(policy_version: str | None, include_macros: bool = False) -> dict | None:
    """Filter for customer-facing answers.

    Zendesk macros are internal templates agents copy from, not documents a customer should be pointed at.
    They are also where stale text hides (an old macro quoting the retired 14-day window is how the original
    escalation happened), so they are excluded unless asked for.
    """
    where = dict(policy_where(policy_version) or {})
    if not include_macros:
        where["doc_type"] = {"$ne": "macro"}
    return where or None


def to_chroma_where(where: dict | None) -> dict | None:
    if not where:
        return None
    clauses = [{k: v} for k, v in where.items()]
    return clauses[0] if len(clauses) == 1 else {"$and": clauses}


def matches_where(chunk: dict, where: dict | None) -> bool:
    if not where:
        return True
    for field, cond in where.items():
        value = chunk.get(field)
        if isinstance(cond, dict) and "$in" in cond:
            if value not in cond["$in"]:
                return False
        elif isinstance(cond, dict) and "$ne" in cond:
            if value == cond["$ne"]:
                return False
        elif value != cond:
            return False
    return True
