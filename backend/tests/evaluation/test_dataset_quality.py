from __future__ import annotations

import os

import pytest

from backend.evaluation.metrics import CATEGORY_RANGES, enabled_cases, validate_dataset


pytestmark = [
    pytest.mark.evaluation,
    pytest.mark.skipif(
        os.getenv("RUN_RAG_EVALUATION") != "1",
        reason="Set RUN_RAG_EVALUATION=1 để kiểm tra benchmark đã được biên soạn.",
    ),
]


def test_curated_dataset_is_report_ready(raw_evaluation_dataset, corpus_by_id):
    errors = validate_dataset(raw_evaluation_dataset, set(corpus_by_id))
    assert not errors, "Dataset không hợp lệ:\n- " + "\n- ".join(errors)


def test_dataset_distribution_matches_research_protocol(evaluation_dataset):
    cases = enabled_cases(evaluation_dataset)
    counts = {
        category: sum(case["category"] == category for case in cases)
        for category in CATEGORY_RANGES
    }
    assert 80 <= len(cases) <= 100
    for category, (minimum, maximum) in CATEGORY_RANGES.items():
        assert minimum <= counts[category] <= maximum


def test_gold_citations_are_physical_provision_ids(evaluation_dataset, corpus_by_id):
    corpus_ids = set(corpus_by_id)
    for case in enabled_cases(evaluation_dataset):
        for group in case["gold_citation_groups"]:
            assert set(group) <= corpus_ids, (
                f"{case['id']} chứa ID không phải provision_id vật lý trong corpus."
            )
