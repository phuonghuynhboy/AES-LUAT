"""Orchestrator của hybrid retrieval có temporal filter.

Luồng truy vấn::

    BM25 candidates ----\
                         RRF -> temporal-safe results
    Dense candidates ---/

Corpus loading, temporal filtering, từng search backend và rank fusion được đặt
trong các module riêng. File này giữ ``HybridRetriever`` và re-export API cũ.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
import logging

try:
    from .bm25_retriever import BM25Retriever, vi_tokenize
    from .corpus_loader import load_chunks, resolve_input_files
    from .dense_retriever import DenseRetriever
    from .rank_fusion import rrf_fuse
    from .retrieval_config import BASE_DIR, CONFIG
    from .temporal_filter import TemporalIndex, normalize_as_of, parse_iso_day
except ImportError:  # Hỗ trợ chạy trực tiếp file này khi debug.
    from bm25_retriever import BM25Retriever, vi_tokenize
    from corpus_loader import load_chunks, resolve_input_files
    from dense_retriever import DenseRetriever
    from rank_fusion import rrf_fuse
    from retrieval_config import BASE_DIR, CONFIG
    from temporal_filter import TemporalIndex, normalize_as_of, parse_iso_day

# Alias tương thích với helper private của file nguyên khối trước đây.
_resolve_input_files = resolve_input_files
_parse_iso_day = parse_iso_day
_normalize_as_of = normalize_as_of

logger = logging.getLogger(__name__)


@dataclass
class HybridRetriever:
    config: dict = field(default_factory=lambda: dict(CONFIG))

    def __post_init__(self) -> None:
        self.chunks = load_chunks(self.config["chunks_path"])
        self.temporal = TemporalIndex(self.chunks)
        self.bm25 = BM25Retriever(self.chunks)
        self.dense = DenseRetriever(self.chunks, self.config)
        self.dense_enabled = not (
            self.config.get("disable_incomplete_dense", True)
            and not self.dense.is_complete
        )
        if not self.dense_enabled:
            logger.warning(
                "Tắt dense retrieval vì Chroma chỉ bao phủ %.2f%% corpus; "
                "hệ thống tạm dùng BM25 cho đến khi index được ingest đầy đủ.",
                self.dense.corpus_coverage * 100,
            )

    def retrieve(
        self,
        query: str,
        top_n: int | None = None,
        as_of: str | None = None,
        strict_temporal: bool | None = None,
    ) -> list[dict]:
        """Truy xuất hybrid theo phiên bản pháp luật hiệu lực tại ``as_of``."""
        effective_date = normalize_as_of(as_of)
        top_n = top_n or self.config["final_top_n"]
        if strict_temporal is None:
            strict_temporal = self.config.get("strict_temporal", False)

        multiplier = max(1, int(self.config.get("candidate_multiplier", 4)))
        bm25_candidate_k = max(self.config["bm25_top_k"], top_n * multiplier)
        dense_candidate_k = max(self.config["dense_top_k"], top_n * multiplier)

        bm25_candidates = self.bm25.search(query, bm25_candidate_k)
        dense_candidates = (
            self.dense.search(query, dense_candidate_k)
            if self.dense_enabled
            else []
        )

        # Loại phiên bản hết hiệu lực trước fusion để chúng không được cộng RRF.
        bm25_results = self.temporal.filter_ranked(
            bm25_candidates,
            effective_date,
            strict_temporal,
        )[: self.config["bm25_top_k"]]
        dense_results = self.temporal.filter_ranked(
            dense_candidates,
            effective_date,
            strict_temporal,
        )[: self.config["dense_top_k"]]

        fused = rrf_fuse(
            ranked_lists=[("bm25", bm25_results), ("dense", dense_results)],
            k=self.config["rrf_k"],
            top_n=top_n,
        )

        output: list[dict] = []
        for result in fused:
            chunk = result["chunk"]
            warning = None
            if chunk.get("temporal_incomplete") or chunk.get(
                "needs_manual_review"
            ):
                warning = "temporal_metadata_incomplete"
            output.append(
                {
                    "provision_id": chunk["provision_id"],
                    "provision_key": chunk.get("provision_key"),
                    "doc_id": chunk.get("doc_id"),
                    "breadcrumb": chunk.get("breadcrumb", ""),
                    "text": chunk["text"],
                    "valid_from": chunk.get("valid_from"),
                    "valid_to": chunk.get("valid_to"),
                    "as_of": effective_date,
                    "temporal_warning": warning,
                    "rrf_score": round(result["rrf_score"], 5),
                    "sources": result["sources"],
                }
            )
        return output


def main() -> None:
    retriever = HybridRetriever()
    query = (
        "Theo Luật số 57/2024/QH15 quy định về thủ tục đầu tư đặc biệt tại "
        "khu công nghệ cao đối với dự án đầu tư trong lĩnh vực đổi mới sáng tạo, "
        "dự án đầu tư nhà ở xã hội có được áp dụng thủ tục đầu tư đặc biệt này không?"
    )
    for result in retriever.retrieve(query, as_of=date.today().isoformat()):
        print(
            f"[{result['rrf_score']}] {result['provision_id']} "
            f"({result['sources']}) [{result['valid_from']} -> "
            f"{result['valid_to']}] — {result['breadcrumb']}"
        )


if __name__ == "__main__":
    main()
