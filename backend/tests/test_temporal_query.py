from backend.app.generation.retrieval_node import extract_as_of_date


def test_extracts_vietnamese_date_from_question():
    assert (
        extract_as_of_date("Tại thời điểm 06/02/2025, quy định nào áp dụng?")
        == "2025-02-06"
    )


def test_extracts_iso_date_from_question():
    assert extract_as_of_date("Áp dụng ngày 2026-07-01") == "2026-07-01"


def test_invalid_or_missing_date_returns_none():
    assert extract_as_of_date("Ngày 31/02/2025 có hợp lệ không?") is None
    assert extract_as_of_date("Quy định hiện hành là gì?") is None
