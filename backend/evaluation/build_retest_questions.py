"""Tạo bộ tái kiểm thử retrieval-aware cho ba nhóm câu hỏi.

Bộ này phục vụ kiểm tra chức năng sau khi quan sát lỗi retrieval của benchmark
đầy đủ. Mỗi câu chỉ được chọn khi toàn bộ ``gold_citation_groups`` xuất hiện
trong Top-2 của chính pipeline retrieval hiện tại. Vì có bước sàng lọc này,
kết quả KHÔNG được dùng thay cho benchmark độc lập 80-100 câu.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any, Iterable

# Không gọi mạng để kiểm tra model embedding đã có trong cache cục bộ.
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

from backend.app.retrieval.retriever import HybridRetriever
from backend.app.retrieval.retrieval_config import CONFIG
from backend.evaluation.build_questions_from_chunks import (
    _body,
    _clean_markdown,
    _doc_label,
    _fact_rule,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = Path(__file__).resolve().parent / "questions_retest.json"
RETEST_AS_OF = date(2026, 9, 24)
TARGET_COUNTS = {
    "single_hop": 20,
    "multi_hop": 15,
    "temporal_aware": 5,
}


def _stable_key(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _location(chunk: dict[str, Any]) -> str:
    breadcrumb = _clean_markdown(str(chunk.get("breadcrumb") or ""))
    if breadcrumb:
        return breadcrumb
    parts = [
        f"Điều {chunk['dieu']}" if chunk.get("dieu") else "",
        f"Khoản {chunk['khoan']}" if chunk.get("khoan") else "",
        f"Điểm {chunk['diem']}" if chunk.get("diem") else "",
    ]
    return " > ".join(part for part in parts if part)


def _topic_hint(chunk: dict[str, Any], maximum_words: int = 20) -> str:
    """Lấy cụm chủ đề ngắn, không chép toàn bộ đáp án vào câu hỏi."""
    body = _body(chunk)
    body = re.sub(r"^(?:[a-zđ]\)|\d+[.)])\s*", "", body, flags=re.I)
    first_clause = re.split(r"[.;:]", body, maxsplit=1)[0].strip(" ,")
    words = first_clause.split()
    if len(words) < 5:
        words = body.split()
    return " ".join(words[:maximum_words]).strip(" ,;:.")


def _is_effective(retriever: HybridRetriever, chunk: dict[str, Any]) -> bool:
    return retriever.temporal.is_effective(
        chunk,
        RETEST_AS_OF.isoformat(),
        strict_temporal=False,
    )


def _eligible_regular(retriever: HybridRetriever, chunk: dict[str, Any]) -> bool:
    text = str(chunk.get("text") or "").strip()
    return (
        not bool(chunk.get("is_amendment_text"))
        and bool(_location(chunk))
        and str(chunk.get("level") or "") in {"dieu", "khoan", "diem"}
        and 70 <= len(text) <= 760
        and _is_effective(retriever, chunk)
    )


def _eligible_temporal(retriever: HybridRetriever, chunk: dict[str, Any]) -> bool:
    text = str(chunk.get("text") or "").strip()
    return (
        bool(chunk.get("is_amendment_text"))
        and bool(chunk.get("valid_from"))
        and bool(_location(chunk))
        and 70 <= len(text) <= 760
        and _is_effective(retriever, chunk)
    )


def _retrieved_ids(retriever: HybridRetriever, question: str) -> list[str]:
    return [
        str(item.get("provision_id") or "")
        for item in retriever.retrieve(
            question,
            top_n=2,
            as_of=RETEST_AS_OF.isoformat(),
        )
    ]


def _screen_question(
    retriever: HybridRetriever,
    variants: Iterable[str],
    required_ids: set[str],
) -> tuple[str, list[str]] | None:
    for question in variants:
        retrieved_ids = _retrieved_ids(retriever, question)
        if required_ids <= set(retrieved_ids):
            return question, retrieved_ids
    return None


def _single_variants(chunk: dict[str, Any]) -> list[str]:
    document = _doc_label(chunk)
    location = _location(chunk)
    hint = _topic_hint(chunk)
    return [
        f"Theo {document}, tại {location}, pháp luật quy định như thế nào về {hint}?",
        f"Trong {document}, nội dung tại {location} quy định gì về {hint}?",
    ]


def _multi_variants(
    left: dict[str, Any],
    right: dict[str, Any],
) -> list[str]:
    document = _doc_label(left)
    left_location = _location(left)
    right_location = _location(right)
    left_hint = _topic_hint(left, maximum_words=16)
    right_hint = _topic_hint(right, maximum_words=16)
    return [
        (
            f"Theo {document}, hãy trình bày đồng thời: (1) quy định về "
            f"{left_hint} tại {left_location}; và (2) quy định về {right_hint} "
            f"tại {right_location}."
        ),
        (
            f"Trong {document}, nội dung tại (1) {left_location} về {left_hint} "
            f"và (2) {right_location} về {right_hint} được quy định như thế nào?"
        ),
    ]


def _temporal_variants(chunk: dict[str, Any]) -> list[str]:
    valid_from = date.fromisoformat(str(chunk["valid_from"]))
    location = _location(chunk)
    hint = _topic_hint(chunk)
    document = _doc_label(chunk)
    display_date = valid_from.strftime("%d/%m/%Y")
    return [
        (
            f"Tại thời điểm {RETEST_AS_OF.strftime('%d/%m/%Y')}, theo nội dung "
            f"sửa đổi có hiệu lực từ {display_date} trong {document}, {location} "
            f"quy định như thế nào về {hint}?"
        ),
        (
            f"Theo phiên bản sửa đổi có hiệu lực từ {display_date} của {document}, "
            f"tại thời điểm {RETEST_AS_OF.strftime('%d/%m/%Y')}, nội dung "
            f"{location} về {hint} được xác định như thế nào?"
        ),
    ]


def _round_robin(
    values_by_doc: dict[str, list[Any]],
    count: int,
) -> list[Any]:
    queues = {
        key: list(values)
        for key, values in sorted(values_by_doc.items())
        if values
    }
    selected: list[Any] = []
    while queues and len(selected) < count:
        for key in list(queues):
            if len(selected) >= count:
                break
            queue = queues[key]
            selected.append(queue.pop(0))
            if not queue:
                del queues[key]
    if len(selected) < count:
        raise ValueError(f"Chỉ tìm được {len(selected)}/{count} câu qua sàng lọc Top-2.")
    return selected


def build_single_hop(
    retriever: HybridRetriever,
) -> list[dict[str, Any]]:
    candidates_by_doc: dict[str, list[tuple[dict[str, Any], str, list[str]]]] = defaultdict(list)
    ordered = sorted(
        (chunk for chunk in retriever.chunks if _eligible_regular(retriever, chunk)),
        key=lambda chunk: _stable_key(str(chunk["provision_id"])),
    )
    for chunk in ordered:
        if sum(len(values) for values in candidates_by_doc.values()) >= 30:
            break
        doc_id = str(chunk.get("doc_id") or "")
        if len(candidates_by_doc[doc_id]) >= 2:
            continue
        screened = _screen_question(
            retriever,
            _single_variants(chunk),
            {str(chunk["provision_id"])},
        )
        if screened:
            question, retrieved_ids = screened
            candidates_by_doc[doc_id].append((chunk, question, retrieved_ids))
            print(
                f"single accepted {chunk['provision_id']}: {retrieved_ids}",
                flush=True,
            )

    selected = _round_robin(candidates_by_doc, TARGET_COUNTS["single_hop"])
    cases: list[dict[str, Any]] = []
    for index, (chunk, question, retrieved_ids) in enumerate(selected, start=1):
        cases.append(
            {
                "id": f"RETEST_SINGLE_{index:03d}",
                "enabled": True,
                "category": "single_hop",
                "question": question,
                "expected_statuses": ["full_answer"],
                "gold_answer": str(chunk["text"]).strip(),
                "gold_citation_groups": [[str(chunk["provision_id"])]],
                "answer_rubric": {
                    "required_facts": [_fact_rule(chunk, "fact_1")],
                    "forbidden_facts": [],
                    "minimum_fact_coverage": 1.0,
                },
                "retrieval_screen": {
                    "top_n": 2,
                    "retrieved_ids": retrieved_ids,
                },
                "notes": "Ca tái kiểm thử đã được sàng lọc để gold citation xuất hiện trong Top-2 retrieval.",
            }
        )
    return cases


def _pair_candidates(
    retriever: HybridRetriever,
) -> dict[str, list[tuple[dict[str, Any], dict[str, Any], str, list[str]]]]:
    by_article: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for chunk in retriever.chunks:
        if not _eligible_regular(retriever, chunk):
            continue
        article = str(chunk.get("dieu") or "").strip()
        if article and str(chunk.get("level") or "") in {"khoan", "diem"}:
            by_article[(str(chunk.get("doc_id") or ""), article)].append(chunk)

    passing_by_doc: dict[
        str,
        list[tuple[dict[str, Any], dict[str, Any], str, list[str]]],
    ] = defaultdict(list)
    for (doc_id, _article), chunks in sorted(by_article.items()):
        if sum(len(values) for values in passing_by_doc.values()) >= 24:
            break
        ordered = sorted(chunks, key=lambda item: str(item["provision_id"]))
        pairs: list[tuple[dict[str, Any], dict[str, Any]]] = []
        for left_index, left in enumerate(ordered[:10]):
            for right in ordered[left_index + 1 : 10]:
                if left["provision_id"] != right["provision_id"]:
                    pairs.append((left, right))
        pairs.sort(
            key=lambda pair: _stable_key(
                f"{pair[0]['provision_id']}|{pair[1]['provision_id']}"
            )
        )
        for left, right in pairs:
            if len(passing_by_doc[doc_id]) >= 3:
                break
            required_ids = {
                str(left["provision_id"]),
                str(right["provision_id"]),
            }
            screened = _screen_question(
                retriever,
                _multi_variants(left, right),
                required_ids,
            )
            if screened:
                question, retrieved_ids = screened
                passing_by_doc[doc_id].append(
                    (left, right, question, retrieved_ids)
                )
                print(
                    "multi accepted "
                    f"{left['provision_id']} + {right['provision_id']}: "
                    f"{retrieved_ids}",
                    flush=True,
                )
    return passing_by_doc


def build_multi_hop(
    retriever: HybridRetriever,
) -> list[dict[str, Any]]:
    selected = _round_robin(
        _pair_candidates(retriever),
        TARGET_COUNTS["multi_hop"],
    )
    cases: list[dict[str, Any]] = []
    for index, (left, right, question, retrieved_ids) in enumerate(selected, start=1):
        cases.append(
            {
                "id": f"RETEST_MULTI_{index:03d}",
                "enabled": True,
                "category": "multi_hop",
                "question": question,
                "expected_statuses": ["full_answer"],
                "gold_answer": (
                    f"{str(left['text']).strip()}\n\n{str(right['text']).strip()}"
                ),
                "gold_citation_groups": [
                    [str(left["provision_id"])],
                    [str(right["provision_id"])],
                ],
                "answer_rubric": {
                    "required_facts": [
                        _fact_rule(left, "hop_1_fact"),
                        _fact_rule(right, "hop_2_fact"),
                    ],
                    "forbidden_facts": [],
                    "minimum_fact_coverage": 1.0,
                },
                "retrieval_screen": {
                    "top_n": 2,
                    "retrieved_ids": retrieved_ids,
                },
                "notes": "Ca tái kiểm thử đã được sàng lọc để cả hai gold citation xuất hiện trong Top-2 retrieval.",
            }
        )
    return cases


def build_temporal(
    retriever: HybridRetriever,
) -> list[dict[str, Any]]:
    candidates_by_doc: dict[str, list[tuple[dict[str, Any], str, list[str]]]] = defaultdict(list)
    ordered = sorted(
        (chunk for chunk in retriever.chunks if _eligible_temporal(retriever, chunk)),
        key=lambda chunk: _stable_key(str(chunk["provision_id"])),
    )
    for chunk in ordered:
        if sum(len(values) for values in candidates_by_doc.values()) >= 10:
            break
        doc_id = str(chunk.get("doc_id") or "")
        if len(candidates_by_doc[doc_id]) >= 3:
            continue
        screened = _screen_question(
            retriever,
            _temporal_variants(chunk),
            {str(chunk["provision_id"])},
        )
        if screened:
            question, retrieved_ids = screened
            candidates_by_doc[doc_id].append((chunk, question, retrieved_ids))
            print(
                f"temporal accepted {chunk['provision_id']}: {retrieved_ids}",
                flush=True,
            )

    selected = _round_robin(candidates_by_doc, TARGET_COUNTS["temporal_aware"])
    cases: list[dict[str, Any]] = []
    for index, (chunk, question, retrieved_ids) in enumerate(selected, start=1):
        cases.append(
            {
                "id": f"RETEST_TEMPORAL_{index:03d}",
                "enabled": True,
                "category": "temporal_aware",
                "question": question,
                "as_of_date": RETEST_AS_OF.isoformat(),
                "expected_statuses": ["full_answer"],
                "gold_answer": str(chunk["text"]).strip(),
                "gold_citation_groups": [[str(chunk["provision_id"])]],
                "answer_rubric": {
                    "required_facts": [
                        _fact_rule(chunk, "effective_version_fact")
                    ],
                    "forbidden_facts": [],
                    "minimum_fact_coverage": 1.0,
                },
                "require_temporal_warning": False,
                "retrieval_screen": {
                    "top_n": 2,
                    "retrieved_ids": retrieved_ids,
                },
                "notes": "Ca temporal tái kiểm thử dùng phiên bản có hiệu lực tại ngày 2026-09-24 và đã qua sàng lọc Top-2.",
            }
        )
    return cases


def build_dataset() -> dict[str, Any]:
    retriever = HybridRetriever(dict(CONFIG))
    cases = [
        *build_single_hop(retriever),
        *build_multi_hop(retriever),
        *build_temporal(retriever),
    ]
    return {
        "name": "AES LUAT retrieval-aware functional retest",
        "version": "1.0.0-retest-2026-09-24",
        "validation_profile": "retest_three_groups",
        "description": (
            "40 câu tái kiểm thử: 20 single-hop, 15 multi-hop và 5 temporal-aware. "
            "Mỗi case được sàng lọc để gold citation xuất hiện trong Top-2 retrieval; "
            "không dùng thay benchmark độc lập."
        ),
        "created_by": "Deterministic retrieval-aware retest generator",
        "reviewed_by": "Chưa duyệt chuyên gia pháp lý",
        "selection_bias_warning": (
            "Dataset được chọn sau bước kiểm tra retrieval nên chỉ đo pipeline sinh và "
            "xác minh trên các ca có bằng chứng nằm trong Top-2."
        ),
        "cases": cases,
    }


def main() -> None:
    dataset = build_dataset()
    DEFAULT_OUTPUT.write_text(
        json.dumps(dataset, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    counts = {
        category: sum(case["category"] == category for case in dataset["cases"])
        for category in TARGET_COUNTS
    }
    print(f"Created {DEFAULT_OUTPUT}")
    print(json.dumps(counts, ensure_ascii=False))


if __name__ == "__main__":
    main()
