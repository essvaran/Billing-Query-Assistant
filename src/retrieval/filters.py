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
