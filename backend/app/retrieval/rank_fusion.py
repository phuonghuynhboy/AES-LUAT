"""Reciprocal Rank Fusion cho nhiều danh sách kết quả."""

from __future__ import annotations


def rrf_fuse(
    ranked_lists: list[tuple[str, list[tuple[dict, float]]]],
    k: int,
    top_n: int,
) -> list[dict]:
    fused: dict[str, dict] = {}
    for list_name, ranked in ranked_lists:
        for rank, (chunk, _score) in enumerate(ranked, start=1):
            provision_id = chunk["provision_id"]
            entry = fused.setdefault(
                provision_id,
                {"chunk": chunk, "rrf_score": 0.0, "sources": set()},
            )
            entry["rrf_score"] += 1.0 / (k + rank)
            entry["sources"].add(list_name)

    merged = sorted(
        fused.values(),
        key=lambda entry: entry["rrf_score"],
        reverse=True,
    )[:top_n]
    for result in merged:
        result["sources"] = sorted(result["sources"])
    return merged
