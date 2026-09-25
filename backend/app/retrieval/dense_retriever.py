"""Semantic search qua embeddings và Chroma."""

from __future__ import annotations


class DenseRetriever:
    def __init__(self, chunks: list[dict], config: dict):
        try:
            from langchain_chroma import Chroma
        except ImportError:
            from langchain_community.vectorstores import Chroma
        from langchain_huggingface import HuggingFaceEmbeddings

        self.chunks = chunks
        self.embeddings = HuggingFaceEmbeddings(
            model_name=config["embedding_model"]
        )
        self._id_to_chunk = {
            chunk["provision_id"]: chunk for chunk in chunks
        }
        self.store = Chroma(
            collection_name=config["collection_name"],
            embedding_function=self.embeddings,
            persist_directory=config["chroma_persist_dir"],
        )
        indexed_count = int(self.store._collection.count())
        corpus_count = len(self._id_to_chunk)
        self.corpus_coverage = (
            min(1.0, indexed_count / corpus_count) if corpus_count else 0.0
        )
        minimum_coverage = float(config.get("min_dense_corpus_coverage", 0.95))
        self.is_complete = self.corpus_coverage >= minimum_coverage

    @staticmethod
    def _fallback_chunk(document) -> dict:
        """Phục hồi chunk từ metadata nếu corpus JSON không chứa provision ID."""
        metadata = dict(document.metadata or {})
        metadata["text"] = document.page_content
        return metadata

    def search(self, query: str, top_k: int) -> list[tuple[dict, float]]:
        results = self.store.similarity_search_with_score(query, k=top_k)
        output: list[tuple[dict, float]] = []
        for document, score in results:
            provision_id = document.metadata.get("provision_id")
            chunk = self._id_to_chunk.get(provision_id) or self._fallback_chunk(
                document
            )
            if chunk.get("provision_id"):
                output.append((chunk, float(score)))
        return output
