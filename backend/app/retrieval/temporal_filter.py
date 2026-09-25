"""Chọn đúng phiên bản điều khoản có hiệu lực tại thời điểm truy vấn."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime


def parse_iso_day(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def normalize_as_of(as_of: str | None) -> str:
    value = as_of or date.today().isoformat()
    if parse_iso_day(value) is None:
        raise ValueError("as_of phải có định dạng YYYY-MM-DD")
    return value


class TemporalIndex:
    """Nhóm chunk theo provision key và ngày bắt đầu hiệu lực."""

    def __init__(self, chunks: list[dict]):
        self.by_key = defaultdict(lambda: defaultdict(list))
        self.no_key_ids: set[str] = set()
        for chunk in chunks:
            key = chunk.get("provision_key")
            if not key:
                self.no_key_ids.add(chunk["provision_id"])
                continue
            valid_from = chunk.get("valid_from") or ""
            self.by_key[key][valid_from].append(chunk)

    def effective_version_from(self, provision_key: str, as_of: str) -> str | None:
        """Trả valid_from mới nhất đã bắt đầu hiệu lực tại ``as_of``."""
        versions = self.by_key.get(provision_key)
        if not versions:
            return None
        dated = [
            valid_from
            for valid_from in versions
            if valid_from and parse_iso_day(valid_from) and valid_from <= as_of
        ]
        return max(dated) if dated else None

    def is_effective(
        self,
        chunk: dict,
        as_of: str,
        strict_temporal: bool = False,
    ) -> bool:
        if strict_temporal and (
            chunk.get("temporal_incomplete") or chunk.get("needs_manual_review")
        ):
            return False

        provision_key = chunk.get("provision_key")
        if not provision_key:
            return not strict_temporal
        effective_from = self.effective_version_from(provision_key, as_of)
        if effective_from is None:
            return False
        return (chunk.get("valid_from") or "") == effective_from

    def filter_ranked(
        self,
        ranked: list[tuple[dict, float]],
        as_of: str,
        strict_temporal: bool,
    ) -> list[tuple[dict, float]]:
        return [
            (chunk, score)
            for chunk, score in ranked
            if self.is_effective(chunk, as_of, strict_temporal)
        ]
