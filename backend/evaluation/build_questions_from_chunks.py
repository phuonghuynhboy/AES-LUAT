"""Sinh bộ benchmark có căn cứ trực tiếp từ ``data/chunks/*.json``.

Script này chỉ xây dựng dữ liệu; không gọi retriever, model hoặc pytest. Dataset sinh ra
là bản nháp có provenance rõ ràng và vẫn cần chuyên gia pháp lý duyệt trước khi dùng
số liệu trong báo cáo chính thức.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Iterable


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
CHUNKS_DIR = REPOSITORY_ROOT / "data" / "chunks"
DEFAULT_OUTPUT = Path(__file__).resolve().parent / "questions.json"
BENCHMARK_AS_OF = date(2026, 9, 24)

TARGET_COUNTS = {
    "single_hop": 46,
    "multi_hop": 28,
    "out_of_scope": 8,
    "temporal_aware": 8,
}

STOPWORDS = {
    "bằng",
    "cho",
    "chính",
    "các",
    "có",
    "của",
    "điều",
    "định",
    "đối",
    "được",
    "giữa",
    "hoặc",
    "khoản",
    "không",
    "luật",
    "một",
    "này",
    "những",
    "pháp",
    "quy",
    "sau",
    "theo",
    "thực",
    "tại",
    "trên",
    "trong",
    "trường",
    "và",
    "về",
    "việc",
    "với",
}


def load_corpus() -> tuple[list[dict[str, Any]], str]:
    files = sorted(CHUNKS_DIR.glob("*.json"), key=lambda path: path.name.casefold())
    if not files:
        raise FileNotFoundError(f"Không tìm thấy chunk JSON trong {CHUNKS_DIR}")

    digest = hashlib.sha256()
    chunks_by_id: dict[str, dict[str, Any]] = {}
    for path in files:
        raw = path.read_bytes()
        digest.update(path.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(raw)
        payload = json.loads(raw.decode("utf-8-sig"))
        if not isinstance(payload, list):
            raise ValueError(f"{path} không phải JSON list.")
        for chunk in payload:
            if not isinstance(chunk, dict):
                raise ValueError(f"{path} chứa chunk không phải object.")
            provision_id = str(chunk.get("provision_id") or "").strip()
            text = str(chunk.get("text") or "").strip()
            if not provision_id or not text:
                raise ValueError(f"Chunk thiếu provision_id/text trong {path}.")
            # Giống corpus_loader: provision_id trùng thì giữ bản xuất hiện cuối.
            chunks_by_id[provision_id] = chunk
    return list(chunks_by_id.values()), digest.hexdigest()


def _date_or_none(value: Any) -> date | None:
    text = str(value or "").strip()
    if not text or text.casefold() == "null":
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _is_effective(chunk: dict[str, Any], as_of: date = BENCHMARK_AS_OF) -> bool:
    valid_from = _date_or_none(chunk.get("valid_from"))
    valid_to = _date_or_none(chunk.get("valid_to"))
    if valid_from and valid_from > as_of:
        return False
    if valid_to and as_of > valid_to:
        return False
    return True


def _clean_markdown(value: str) -> str:
    value = re.sub(r"[*_`]+", "", value or "")
    return re.sub(r"\s+", " ", value).strip(" ;.")


def _body(chunk: dict[str, Any]) -> str:
    text = _clean_markdown(str(chunk.get("text") or ""))
    breadcrumb = _clean_markdown(str(chunk.get("breadcrumb") or ""))
    if breadcrumb and text.casefold().startswith(breadcrumb.casefold()):
        text = text[len(breadcrumb) :].lstrip(" :;-")
    elif ": " in text:
        text = text.split(": ", 1)[1]
    return text.strip()


def _shorten(value: str, maximum: int = 190) -> str:
    value = _clean_markdown(value)
    if len(value) <= maximum:
        return value
    shortened = value[:maximum].rsplit(" ", 1)[0].rstrip(" ,;:")
    return f"{shortened}…"


def _location_reference(chunk: dict[str, Any], maximum: int = 190) -> str:
    breadcrumb = _clean_markdown(str(chunk.get("breadcrumb") or ""))
    if len(breadcrumb) <= maximum:
        return breadcrumb
    structural_parts = [
        f"Điều {chunk['dieu']}" if chunk.get("dieu") else "",
        f"Khoản {chunk['khoan']}" if chunk.get("khoan") else "",
        f"Điểm {chunk['diem']}" if chunk.get("diem") else "",
    ]
    structure = ", ".join(part for part in structural_parts if part)
    suffix = f" [{structure}]" if structure else ""
    return _shorten(breadcrumb, maximum - len(suffix)) + suffix


def _doc_label(chunk: dict[str, Any]) -> str:
    doc_id = str(chunk.get("doc_id") or "văn bản không rõ số").strip()
    title = _clean_markdown(str(chunk.get("doc_title") or ""))
    if not title or len(title) > 120 or title.casefold() in {"đầu tư"}:
        return f"văn bản {doc_id}"
    return f"văn bản “{title}” ({doc_id})"


def _fact_rule(chunk: dict[str, Any], fact_id: str) -> dict[str, Any]:
    body = _body(chunk)
    words = body.split()
    phrase = " ".join(words[: min(14, len(words))]).strip(" ,;:.")
    if len(phrase) < 25:
        phrase = _shorten(body, 130)

    tokens: list[str] = []
    for token in re.findall(r"\w+", body.casefold(), flags=re.UNICODE):
        token = token.strip("_")
        if len(token) < 4 or token in STOPWORDS or token in tokens:
            continue
        tokens.append(token)
        if len(tokens) == 5:
            break
    pattern = "(?is)" + ".*".join(re.escape(token) for token in tokens)
    return {
        "fact_id": fact_id,
        "description": _shorten(body, 220),
        "any_of": [phrase],
        "patterns": [pattern] if len(tokens) >= 3 else [],
    }


def _eligible_source_chunk(chunk: dict[str, Any]) -> bool:
    text = str(chunk.get("text") or "").strip()
    breadcrumb = str(chunk.get("breadcrumb") or "").strip()
    return (
        not bool(chunk.get("is_amendment_text"))
        and bool(breadcrumb)
        and 90 <= len(text) <= 850
        and str(chunk.get("level") or "") in {"dieu", "khoan", "diem"}
        and _is_effective(chunk)
    )


def _stable_chunk_order(chunk: dict[str, Any]) -> str:
    provision_id = str(chunk["provision_id"])
    return hashlib.sha256(provision_id.encode("utf-8")).hexdigest()


def _round_robin(
    values_by_doc: dict[str, list[Any]],
    count: int,
) -> list[Any]:
    queues = {
        doc_id: list(values)
        for doc_id, values in sorted(values_by_doc.items())
        if values
    }
    selected: list[Any] = []
    while queues and len(selected) < count:
        for doc_id in list(queues):
            if len(selected) >= count:
                break
            queue = queues[doc_id]
            if queue:
                selected.append(queue.pop(0))
            if not queue:
                del queues[doc_id]
    if len(selected) != count:
        raise ValueError(f"Chỉ chọn được {len(selected)}/{count} phần tử có căn cứ.")
    return selected


def build_single_hop(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_doc: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for chunk in chunks:
        if _eligible_source_chunk(chunk):
            by_doc[str(chunk["doc_id"])].append(chunk)
    for candidates in by_doc.values():
        candidates.sort(key=_stable_chunk_order)

    cases: list[dict[str, Any]] = []
    for index, chunk in enumerate(
        _round_robin(by_doc, TARGET_COUNTS["single_hop"]), start=1
    ):
        breadcrumb = _location_reference(chunk)
        cases.append(
            {
                "id": f"SINGLE_{index:03d}",
                "enabled": True,
                "category": "single_hop",
                "question": (
                    f"Theo {_doc_label(chunk)}, {breadcrumb} quy định như thế nào?"
                ),
                "expected_statuses": ["full_answer"],
                "gold_answer": str(chunk["text"]).strip(),
                "gold_citation_groups": [[str(chunk["provision_id"])]] ,
                "answer_rubric": {
                    "required_facts": [_fact_rule(chunk, "fact_1")],
                    "forbidden_facts": [],
                    "minimum_fact_coverage": 1.0,
                },
                "notes": (
                    "Sinh từ một chunk corpus; cần chuyên gia xác nhận cách diễn đạt "
                    "câu hỏi và fact rubric trước báo cáo."
                ),
            }
        )
    return cases


def _pair_candidates(
    chunks: Iterable[dict[str, Any]],
) -> dict[str, list[tuple[dict[str, Any], dict[str, Any]]]]:
    by_article: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for chunk in chunks:
        if (
            not _eligible_source_chunk(chunk)
            or str(chunk.get("level") or "") not in {"khoan", "diem"}
        ):
            continue
        article = str(chunk.get("dieu") or "").strip()
        if article:
            by_article[(str(chunk["doc_id"]), article)].append(chunk)

    pairs_by_doc: dict[str, list[tuple[dict[str, Any], dict[str, Any]]]] = defaultdict(list)
    for (doc_id, _article), values in sorted(by_article.items()):
        ordered = sorted(values, key=lambda item: str(item["provision_id"]))
        for offset in range(0, len(ordered) - 1, 2):
            left, right = ordered[offset], ordered[offset + 1]
            if (
                left["provision_id"] != right["provision_id"]
                and _clean_markdown(str(left.get("breadcrumb") or ""))
                != _clean_markdown(str(right.get("breadcrumb") or ""))
            ):
                pairs_by_doc[doc_id].append((left, right))
    for pairs in pairs_by_doc.values():
        pairs.sort(
            key=lambda pair: hashlib.sha256(
                f"{pair[0]['provision_id']}|{pair[1]['provision_id']}".encode("utf-8")
            ).hexdigest()
        )
    return pairs_by_doc


def build_multi_hop(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    pairs = _round_robin(
        _pair_candidates(chunks), TARGET_COUNTS["multi_hop"]
    )
    cases: list[dict[str, Any]] = []
    for index, (left, right) in enumerate(pairs, start=1):
        left_ref = _location_reference(left, 150)
        right_ref = _location_reference(right, 150)
        cases.append(
            {
                "id": f"MULTI_{index:03d}",
                "enabled": True,
                "category": "multi_hop",
                "question": (
                    f"Theo {_doc_label(left)}, hãy trình bày đồng thời nội dung tại "
                    f"(1) {left_ref} và (2) {right_ref}."
                ),
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
                "notes": (
                    "Cần kết hợp hai chunk vật lý khác nhau trong cùng điều; cần "
                    "chuyên gia duyệt trước báo cáo."
                ),
            }
        )
    return cases


OUT_OF_SCOPE_QUESTIONS = [
    (
        "Điều kiện nhận nuôi con nuôi có yếu tố nước ngoài theo pháp luật Việt Nam là gì?",
        "nuôi con nuôi",
    ),
    (
        "Theo Bộ luật Dân sự, hàng thừa kế thứ nhất gồm những ai và được chia di sản theo nguyên tắc nào?",
        "hàng thừa kế thứ nhất",
    ),
    (
        "Theo Bộ luật Hình sự, hành vi trộm cắp tài sản có thể bị phạt tù tối đa bao nhiêu năm?",
        "trộm cắp tài sản",
    ),
    (
        "Theo pháp luật lao động, người lao động làm đủ 12 tháng được nghỉ hằng năm bao nhiêu ngày?",
        "nghỉ hằng năm",
    ),
    (
        "Điều kiện để lao động nữ được hưởng chế độ thai sản theo pháp luật bảo hiểm xã hội là gì?",
        "chế độ thai sản",
    ),
    (
        "Mức giảm trừ gia cảnh khi tính thuế thu nhập cá nhân hiện được xác định như thế nào?",
        "giảm trừ gia cảnh",
    ),
    (
        "Thời hạn bảo hộ nhãn hiệu theo pháp luật sở hữu trí tuệ là bao lâu và có được gia hạn không?",
        "bảo hộ nhãn hiệu",
    ),
    (
        "Điều kiện lập di chúc miệng hợp pháp theo Bộ luật Dân sự là gì?",
        "di chúc miệng",
    ),
]


def build_out_of_scope(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    corpus_text = "\n".join(str(chunk.get("text") or "") for chunk in chunks).casefold()
    present_anchors = [
        anchor for _question, anchor in OUT_OF_SCOPE_QUESTIONS if anchor.casefold() in corpus_text
    ]
    if present_anchors:
        raise ValueError(
            "Out-of-scope anchor đã xuất hiện trong corpus; cần thay câu hỏi: "
            + ", ".join(present_anchors)
        )
    return [
        {
            "id": f"OOS_{index:03d}",
            "enabled": True,
            "category": "out_of_scope",
            "question": question,
            "expected_statuses": ["refusal"],
            "gold_answer": "",
            "gold_citation_groups": [],
            "answer_rubric": {
                "required_facts": [],
                "forbidden_facts": [],
                "minimum_fact_coverage": 1.0,
            },
            "notes": (
                f"Cụm kiểm tra phạm vi “{anchor}” không xuất hiện trong corpus tại "
                "thời điểm sinh dataset; hệ thống phải từ chối và không hiển thị citation."
            ),
        }
        for index, (question, anchor) in enumerate(OUT_OF_SCOPE_QUESTIONS, start=1)
    ]


def build_temporal(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_doc: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for chunk in chunks:
        valid_from = _date_or_none(chunk.get("valid_from"))
        text = str(chunk.get("text") or "").strip()
        if (
            bool(chunk.get("is_amendment_text"))
            and valid_from is not None
            and valid_from <= BENCHMARK_AS_OF
            and not _date_or_none(chunk.get("valid_to"))
            and str(chunk.get("breadcrumb") or "").strip()
            and 90 <= len(text) <= 850
        ):
            by_doc[str(chunk["doc_id"])].append(chunk)
    for candidates in by_doc.values():
        candidates.sort(key=_stable_chunk_order)

    selected = _round_robin(by_doc, TARGET_COUNTS["temporal_aware"])
    cases: list[dict[str, Any]] = []
    for index, chunk in enumerate(selected, start=1):
        valid_from = _date_or_none(chunk["valid_from"])
        assert valid_from is not None
        cases.append(
            {
                "id": f"TEMPORAL_{index:03d}",
                "enabled": True,
                "category": "temporal_aware",
                "question": (
                    f"Tại thời điểm {valid_from.strftime('%d/%m/%Y')}, theo nội dung "
                    f"sửa đổi tại {_location_reference(chunk)} trong văn bản "
                    f"{chunk['doc_id']}, quy định được xác định như thế nào?"
                ),
                "as_of_date": valid_from.isoformat(),
                "expected_statuses": ["full_answer"],
                "gold_answer": str(chunk["text"]).strip(),
                "gold_citation_groups": [[str(chunk["provision_id"])]] ,
                "answer_rubric": {
                    "required_facts": [
                        _fact_rule(chunk, "effective_version_fact")
                    ],
                    "forbidden_facts": [],
                    "minimum_fact_coverage": 1.0,
                },
                "require_temporal_warning": False,
                "notes": (
                    f"Chunk sửa đổi có valid_from={valid_from.isoformat()}; corpus "
                    "không có phiên bản cũ cùng provision_key để tạo forbidden fact tự động."
                ),
            }
        )
    return cases


def build_dataset() -> dict[str, Any]:
    chunks, corpus_sha256 = load_corpus()
    cases = [
        *build_single_hop(chunks),
        *build_multi_hop(chunks),
        *build_out_of_scope(chunks),
        *build_temporal(chunks),
    ]
    return {
        "name": "AES LUAT corpus-derived benchmark",
        "version": "1.0.0-corpus-2026-09-24",
        "description": (
            "90 câu sinh có kiểm soát từ data/chunks: 46 single-hop, 28 multi-hop, "
            "8 out-of-scope, 8 temporal-aware. Gold answer giữ nguyên văn corpus. "
            f"Corpus SHA-256: {corpus_sha256}."
        ),
        "created_by": "Deterministic corpus-derived generator",
        "reviewed_by": "Chưa duyệt chuyên gia pháp lý",
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
