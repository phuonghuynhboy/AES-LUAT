"""Lexical search tiếng Việt bằng BM25."""

from __future__ import annotations

import re
import unicodedata

_TOKEN_RE = re.compile(
    r"[0-9a-zA-Zàáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩị"
    r"òóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđĐ]+"
)


def vi_tokenize(text: str) -> list[str]:
    normalized = unicodedata.normalize("NFC", text or "").lower()
    return _TOKEN_RE.findall(normalized)


class BM25Retriever:
    def __init__(self, chunks: list[dict]):
        try:
            from rank_bm25 import BM25Okapi
        except ImportError as error:
            raise ImportError(
                "Thiếu dependency rank_bm25. Cài bằng: pip install rank-bm25"
            ) from error

        self.chunks = chunks
        self._corpus_tokens = [vi_tokenize(chunk["text"]) for chunk in chunks]
        self._bm25 = BM25Okapi(self._corpus_tokens)

    def search(self, query: str, top_k: int) -> list[tuple[dict, float]]:
        query_tokens = vi_tokenize(query)
        if not query_tokens:
            return []
        scores = self._bm25.get_scores(query_tokens)
        ranked_indices = sorted(
            range(len(scores)),
            key=lambda index: scores[index],
            reverse=True,
        )[:top_k]
        return [
            (self.chunks[index], float(scores[index]))
            for index in ranked_indices
            if scores[index] > 0
        ]
