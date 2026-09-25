"""Các phép đo tái lập được cho benchmark RAG pháp luật.

Module này không gọi model. Nó chỉ so sánh response đã sinh với ground truth
được chuyên gia chuẩn bị trong dataset đánh giá.
"""

from __future__ import annotations

from collections import Counter
from datetime import date
import json
from pathlib import Path
import re
import unicodedata
from typing import Any


CATEGORY_RANGES: dict[str, tuple[int, int]] = {
    "single_hop": (40, 50),
    "multi_hop": (26, 32),
    "out_of_scope": (7, 9),
    "temporal_aware": (7, 9),
}
RETEST_CATEGORY_RANGES: dict[str, tuple[int, int]] = {
    "single_hop": (20, 20),
    "multi_hop": (15, 15),
    "temporal_aware": (2, 5),
}
RETEST_PROFILE = "retest_three_groups"
ALLOWED_STATUSES = {"full_answer", "partial_answer", "refusal"}
SUPPORTED_CLAIM_STATUSES = {"supported", "partially_supported"}


def load_dataset(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(
            f"Không tìm thấy dataset đánh giá: {path}. "
            "Hãy sao chép questions.template.json thành questions.json và biên soạn ground truth."
        )
    with path.open("r", encoding="utf-8") as file:
        payload = json.load(file)
    if not isinstance(payload, dict):
        raise ValueError("Dataset đánh giá phải là một JSON object.")
    return payload


def enabled_cases(dataset: dict[str, Any]) -> list[dict[str, Any]]:
    cases = dataset.get("cases")
    if not isinstance(cases, list):
        return []
    return [case for case in cases if isinstance(case, dict) and case.get("enabled", True)]


def _is_non_empty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _validate_fact_rules(case_id: str, rules: Any, field: str) -> list[str]:
    errors: list[str] = []
    if not isinstance(rules, list):
        return [f"{case_id}: answer_rubric.{field} phải là list."]
    for index, rule in enumerate(rules):
        prefix = f"{case_id}: answer_rubric.{field}[{index}]"
        if not isinstance(rule, dict):
            errors.append(f"{prefix} phải là object.")
            continue
        if not _is_non_empty_string(rule.get("fact_id")):
            errors.append(f"{prefix}.fact_id không được rỗng.")
        any_of = rule.get("any_of", [])
        patterns = rule.get("patterns", [])
        if not isinstance(any_of, list) or not all(_is_non_empty_string(item) for item in any_of):
            errors.append(f"{prefix}.any_of phải là list chuỗi không rỗng.")
        if not isinstance(patterns, list) or not all(_is_non_empty_string(item) for item in patterns):
            errors.append(f"{prefix}.patterns phải là list regex không rỗng.")
        if not any_of and not patterns:
            errors.append(f"{prefix} phải có ít nhất một any_of hoặc patterns.")
        for pattern in patterns if isinstance(patterns, list) else []:
            try:
                re.compile(pattern, flags=re.IGNORECASE)
            except re.error as exc:
                errors.append(f"{prefix} chứa regex không hợp lệ {pattern!r}: {exc}")
    return errors


def validate_dataset(
    dataset: dict[str, Any],
    corpus_ids: set[str] | None = None,
) -> list[str]:
    """Kiểm tra schema, phân bố theo profile và ground-truth citation."""
    errors: list[str] = []
    if not _is_non_empty_string(dataset.get("name")):
        errors.append("Dataset cần trường name là chuỗi không rỗng.")
    if not _is_non_empty_string(dataset.get("version")):
        errors.append("Dataset cần trường version là chuỗi không rỗng.")
    raw_cases = dataset.get("cases")
    if not isinstance(raw_cases, list):
        errors.append("Dataset phải có trường cases là một JSON list.")
        return errors
    for index, raw_case in enumerate(raw_cases):
        if not isinstance(raw_case, dict):
            errors.append(f"Case tại index {index} phải là object.")
        elif not isinstance(raw_case.get("enabled", True), bool):
            errors.append(f"Case tại index {index}: enabled phải là boolean.")

    cases = enabled_cases(dataset)
    profile = str(dataset.get("validation_profile") or "official").strip()
    if profile == RETEST_PROFILE:
        category_ranges = RETEST_CATEGORY_RANGES
        minimum_total = sum(value[0] for value in category_ranges.values())
        maximum_total = sum(value[1] for value in category_ranges.values())
        if not minimum_total <= len(cases) <= maximum_total:
            errors.append(
                "Dataset tái kiểm thử cần "
                f"{minimum_total}–{maximum_total} case được bật; hiện có {len(cases)}."
            )
    else:
        category_ranges = CATEGORY_RANGES
        if not 80 <= len(cases) <= 100:
            errors.append(f"Dataset cần 80–100 case được bật; hiện có {len(cases)}.")

    category_counts = Counter(
        case.get("category")
        if isinstance(case.get("category"), str)
        else "__invalid_category__"
        for case in cases
    )
    for category, (minimum, maximum) in category_ranges.items():
        actual = category_counts.get(category, 0)
        if not minimum <= actual <= maximum:
            errors.append(
                f"Nhóm {category} cần {minimum}–{maximum} case; hiện có {actual}."
            )
    unknown_categories = set(category_counts) - set(category_ranges)
    if unknown_categories:
        errors.append(f"Category không hợp lệ: {sorted(unknown_categories)}")

    seen_ids: set[str] = set()
    for index, case in enumerate(cases):
        case_id = str(case.get("id") or f"case_at_index_{index}").strip()
        if not _is_non_empty_string(case.get("id")):
            errors.append(f"Case tại index {index} thiếu id.")
        elif case_id in seen_ids:
            errors.append(f"ID bị trùng: {case_id}")
        seen_ids.add(case_id)

        if not _is_non_empty_string(case.get("question")):
            errors.append(f"{case_id}: question không được rỗng.")

        expected_statuses = case.get("expected_statuses")
        if (
            not isinstance(expected_statuses, list)
            or not expected_statuses
            or not all(isinstance(value, str) for value in expected_statuses)
            or not set(expected_statuses) <= ALLOWED_STATUSES
        ):
            errors.append(
                f"{case_id}: expected_statuses phải là list con không rỗng của {sorted(ALLOWED_STATUSES)}."
            )

        groups = case.get("gold_citation_groups")
        if not isinstance(groups, list):
            errors.append(f"{case_id}: gold_citation_groups phải là list.")
            groups = []
        for group_index, group in enumerate(groups):
            if not isinstance(group, list) or not group or not all(
                _is_non_empty_string(item) for item in group
            ):
                errors.append(
                    f"{case_id}: gold_citation_groups[{group_index}] phải là list ID không rỗng."
                )
                continue
            if corpus_ids is not None:
                missing = sorted(set(group) - corpus_ids)
                if missing:
                    errors.append(
                        f"{case_id}: provision_id không tồn tại trong corpus: {missing}"
                    )

        category = case.get("category")
        if category == "out_of_scope":
            if groups:
                errors.append(f"{case_id}: out_of_scope không được có gold citation.")
            if isinstance(expected_statuses, list) and "refusal" not in expected_statuses:
                errors.append(f"{case_id}: out_of_scope phải chấp nhận status refusal.")
        else:
            if not groups:
                errors.append(f"{case_id}: case trong phạm vi phải có gold citation.")
            if not _is_non_empty_string(case.get("gold_answer")):
                errors.append(f"{case_id}: case trong phạm vi phải có gold_answer.")

        if category == "single_hop" and len(groups) != 1:
            errors.append(f"{case_id}: single_hop phải có đúng một nhóm citation.")
        if category == "multi_hop" and len(groups) < 2:
            errors.append(f"{case_id}: multi_hop phải có ít nhất hai nhóm citation.")
        if category == "multi_hop":
            distinct_gold_ids = {
                provision_id
                for group in groups
                if isinstance(group, list)
                for provision_id in group
                if isinstance(provision_id, str)
            }
            if len(distinct_gold_ids) < 2:
                errors.append(
                    f"{case_id}: multi_hop phải cần ít nhất hai provision_id vật lý khác nhau."
                )
        if category == "temporal_aware":
            as_of_date = case.get("as_of_date")
            try:
                date.fromisoformat(as_of_date)
            except (TypeError, ValueError):
                errors.append(f"{case_id}: temporal_aware cần as_of_date dạng YYYY-MM-DD.")

        rubric = case.get("answer_rubric")
        if not isinstance(rubric, dict):
            errors.append(f"{case_id}: answer_rubric phải là object.")
            continue
        required_facts = rubric.get("required_facts", [])
        forbidden_facts = rubric.get("forbidden_facts", [])
        errors.extend(_validate_fact_rules(case_id, required_facts, "required_facts"))
        errors.extend(_validate_fact_rules(case_id, forbidden_facts, "forbidden_facts"))
        if category != "out_of_scope" and not required_facts:
            errors.append(f"{case_id}: case trong phạm vi cần ít nhất một required_fact.")
        minimum_coverage = rubric.get("minimum_fact_coverage", 1.0)
        if not isinstance(minimum_coverage, (int, float)) or not 0 <= minimum_coverage <= 1:
            errors.append(f"{case_id}: minimum_fact_coverage phải nằm trong [0, 1].")

    return errors


def normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFC", value or "").casefold()
    return re.sub(r"\s+", " ", normalized).strip()


def _rule_matches(text: str, rule: dict[str, Any]) -> bool:
    normalized_text = normalize_text(text)
    if any(normalize_text(phrase) in normalized_text for phrase in rule.get("any_of", [])):
        return True
    return any(
        re.search(pattern, text or "", flags=re.IGNORECASE | re.UNICODE) is not None
        for pattern in rule.get("patterns", [])
    )


def _token_f1(prediction: str, reference: str) -> float | None:
    reference_tokens = re.findall(r"\w+", normalize_text(reference), flags=re.UNICODE)
    if not reference_tokens:
        return None
    prediction_tokens = re.findall(r"\w+", normalize_text(prediction), flags=re.UNICODE)
    if not prediction_tokens:
        return 0.0
    overlap = sum((Counter(prediction_tokens) & Counter(reference_tokens)).values())
    precision = overlap / len(prediction_tokens)
    recall = overlap / len(reference_tokens)
    return 0.0 if precision + recall == 0 else 2 * precision * recall / (precision + recall)


def evaluate_response(
    case: dict[str, Any],
    response: dict[str, Any],
    corpus_by_id: dict[str, dict[str, Any]],
    human_review: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Chấm một response; không dùng LLM judge."""
    answer = str(response.get("answer") or "")
    status = str(response.get("status") or "")
    claims = response.get("claims") if isinstance(response.get("claims"), list) else []
    sources = response.get("sources") if isinstance(response.get("sources"), list) else []
    warnings = response.get("warnings") if isinstance(response.get("warnings"), list) else []

    raw_source_ids = [
        str(source.get("provision_id")).strip()
        for source in sources
        if isinstance(source, dict) and source.get("provision_id")
    ]
    source_by_id = {
        str(source.get("provision_id")).strip(): source
        for source in sources
        if isinstance(source, dict) and source.get("provision_id")
    }
    source_ids = set(source_by_id)
    duplicate_source_ids = sorted(
        provision_id
        for provision_id, count in Counter(raw_source_ids).items()
        if count > 1
    )
    malformed_source_count = sum(
        not isinstance(source, dict) or not str(source.get("provision_id") or "").strip()
        for source in sources
    )
    supported_claims = [
        claim
        for claim in claims
        if isinstance(claim, dict) and claim.get("status") in SUPPORTED_CLAIM_STATUSES
    ]
    unsupported_claims = [
        claim
        for claim in claims
        if isinstance(claim, dict) and claim.get("status") == "unsupported"
    ]
    predicted_citation_ids: list[str] = []
    supported_without_evidence: list[str] = []
    for claim in supported_claims:
        evidence_ids = [
            str(value).strip()
            for value in claim.get("evidence_chunk_ids") or []
            if str(value).strip()
        ]
        if not evidence_ids:
            supported_without_evidence.append(str(claim.get("claim_id") or "unknown"))
        for evidence_id in evidence_ids:
            if evidence_id not in predicted_citation_ids:
                predicted_citation_ids.append(evidence_id)

    unsupported_with_evidence = [
        str(claim.get("claim_id") or "unknown")
        for claim in unsupported_claims
        if any(str(value).strip() for value in claim.get("evidence_chunk_ids") or [])
    ]

    predicted_set = set(predicted_citation_ids)
    citation_invariant_violations = sorted(predicted_set - source_ids)
    unreferenced_source_ids = sorted(source_ids - predicted_set)
    gold_groups = [set(group) for group in case.get("gold_citation_groups", [])]
    accepted_ids = set().union(*gold_groups) if gold_groups else set()
    correct_citation_ids = predicted_set & accepted_ids
    extraneous_citation_ids = predicted_set - accepted_ids
    hit_groups = [sorted(group) for group in gold_groups if group & predicted_set]
    citation_group_count = len(gold_groups)
    citation_groups_hit = len(hit_groups)
    citation_precision = (
        len(correct_citation_ids) / len(predicted_set)
        if predicted_set
        else (1.0 if not gold_groups else 0.0)
    )
    citation_recall = (
        citation_groups_hit / citation_group_count if citation_group_count else 1.0
    )
    source_integrity_errors: list[str] = []
    if malformed_source_count:
        source_integrity_errors.append(
            f"malformed_sources_without_provision_id:{malformed_source_count}"
        )
    source_integrity_errors.extend(
        f"duplicate_source:{provision_id}" for provision_id in duplicate_source_ids
    )
    for provision_id, source in source_by_id.items():
        corpus_source = corpus_by_id.get(provision_id)
        if corpus_source is None:
            source_integrity_errors.append(f"unknown_source:{provision_id}")
        elif source.get("text") != corpus_source.get("text"):
            source_integrity_errors.append(f"source_text_mismatch:{provision_id}")
    citation_exact = (
        citation_recall == 1.0
        and not extraneous_citation_ids
        and not citation_invariant_violations
        and not unreferenced_source_ids
        and not source_integrity_errors
    )

    rubric = case.get("answer_rubric") or {}
    required_facts = rubric.get("required_facts") or []
    forbidden_facts = rubric.get("forbidden_facts") or []
    matched_required = [
        rule.get("fact_id") for rule in required_facts if _rule_matches(answer, rule)
    ]
    matched_forbidden = [
        rule.get("fact_id") for rule in forbidden_facts if _rule_matches(answer, rule)
    ]
    fact_coverage = (
        len(matched_required) / len(required_facts) if required_facts else 1.0
    )
    minimum_coverage = float(rubric.get("minimum_fact_coverage", 1.0))
    status_correct = status in set(case.get("expected_statuses") or [])
    status_semantics_correct = True
    if status == "full_answer":
        status_semantics_correct = bool(supported_claims) and not unsupported_claims
    elif status == "partial_answer":
        status_semantics_correct = bool(supported_claims) and bool(unsupported_claims)
    elif status == "refusal":
        # retrieved_sources được phép tồn tại để audit, nhưng tuyệt đối không trở thành citation.
        status_semantics_correct = (
            not supported_claims
            and not predicted_set
            and not source_ids
            and not unsupported_with_evidence
        )

    claim_citation_contract_correct = (
        not supported_without_evidence
        and not unsupported_with_evidence
        and not citation_invariant_violations
        and not unreferenced_source_ids
        and not source_integrity_errors
    )
    automatic_answer_correct = (
        status_correct
        and status_semantics_correct
        and fact_coverage >= minimum_coverage
        and not matched_forbidden
    )

    is_out_of_scope = case.get("category") == "out_of_scope"
    out_of_scope_correct = None
    if is_out_of_scope:
        out_of_scope_correct = (
            status == "refusal"
            and not supported_claims
            and not predicted_set
            and not source_ids
        )
        automatic_answer_correct = automatic_answer_correct and out_of_scope_correct

    expected_warning_codes = set(case.get("expected_warning_codes") or [])
    warning_codes_present = {str(value) for value in warnings}
    expected_warnings_present = expected_warning_codes <= warning_codes_present
    if case.get("require_temporal_warning"):
        expected_warnings_present = expected_warnings_present and any(
            bool(str(source.get("temporal_warning") or "").strip())
            for source in sources
            if isinstance(source, dict)
        )

    hallucination_reasons: list[str] = []
    hallucination_reasons.extend(
        f"citation_without_source:{value}" for value in citation_invariant_violations
    )
    hallucination_reasons.extend(
        f"source_without_supported_claim:{value}" for value in unreferenced_source_ids
    )
    hallucination_reasons.extend(source_integrity_errors)
    hallucination_reasons.extend(
        f"supported_claim_without_evidence:{value}" for value in supported_without_evidence
    )
    hallucination_reasons.extend(
        f"unsupported_claim_has_evidence:{value}" for value in unsupported_with_evidence
    )
    hallucination_reasons.extend(
        f"forbidden_fact:{value}" for value in matched_forbidden
    )
    if status == "refusal" and (supported_claims or predicted_set or source_ids):
        hallucination_reasons.append("refusal_contains_verified_citation")
    if is_out_of_scope and not out_of_scope_correct:
        hallucination_reasons.append("out_of_scope_not_safely_refused")

    automatic_citation_exact = citation_exact
    citation_scoring_mode = "automatic_ground_truth"
    answer_scoring_mode = "automatic_rubric"
    answer_correct = automatic_answer_correct
    hallucination_present = bool(hallucination_reasons)
    review_notes = ""
    if human_review:
        if isinstance(human_review.get("citation_correct"), bool):
            # Nhãn chuyên gia kiểm tra quan hệ nội dung claim ↔ nguồn. Các lỗi cấu trúc
            # hoặc sai corpus vẫn là hard guard và không thể bị nhãn tay ghi đè.
            citation_exact = (
                human_review["citation_correct"] and automatic_citation_exact
            )
            citation_scoring_mode = "human_expert_with_structural_guard"
        if isinstance(human_review.get("answer_correct"), bool):
            answer_correct = (
                human_review["answer_correct"]
                and status_correct
                and status_semantics_correct
            )
            answer_scoring_mode = "human_expert_with_status_guard"
        if isinstance(human_review.get("hallucination_present"), bool):
            hallucination_present = (
                human_review["hallucination_present"] or hallucination_present
            )
        review_notes = str(human_review.get("notes") or "")

    temporal_correct = None
    if case.get("category") == "temporal_aware":
        temporal_correct = (
            citation_exact and answer_correct and expected_warnings_present
        )

    return {
        "case_id": case["id"],
        "category": case["category"],
        "question": case["question"],
        "expected_statuses": case.get("expected_statuses", []),
        "actual_status": status,
        "status_correct": status_correct,
        "status_semantics_correct": status_semantics_correct,
        "claim_citation_contract_correct": claim_citation_contract_correct,
        "gold_citation_groups": case.get("gold_citation_groups", []),
        "predicted_citation_ids": predicted_citation_ids,
        "correct_citation_count": len(correct_citation_ids),
        "predicted_citation_count": len(predicted_set),
        "citation_group_count": citation_group_count,
        "citation_groups_hit": citation_groups_hit,
        "citation_precision": citation_precision,
        "citation_recall": citation_recall,
        "citation_exact": citation_exact,
        "automatic_citation_exact": automatic_citation_exact,
        "citation_scoring_mode": citation_scoring_mode,
        "citation_invariant_violations": citation_invariant_violations,
        "unreferenced_source_ids": unreferenced_source_ids,
        "supported_claims_without_evidence": supported_without_evidence,
        "unsupported_claims_with_evidence": unsupported_with_evidence,
        "extraneous_citation_ids": sorted(extraneous_citation_ids),
        "source_integrity_errors": source_integrity_errors,
        "required_fact_count": len(required_facts),
        "matched_required_facts": matched_required,
        "matched_forbidden_facts": matched_forbidden,
        "fact_coverage": fact_coverage,
        "answer_token_f1": _token_f1(answer, str(case.get("gold_answer") or "")),
        "automatic_answer_correct": automatic_answer_correct,
        "answer_correct": answer_correct,
        "answer_scoring_mode": answer_scoring_mode,
        "hallucination_present": hallucination_present,
        "hallucination_reasons": hallucination_reasons,
        "out_of_scope_correct": out_of_scope_correct,
        "temporal_correct": temporal_correct,
        "expected_warnings_present": expected_warnings_present,
        "review_notes": review_notes,
        "answer": answer,
        "claims_for_review": claims,
        "citation_sources_for_review": [
            {
                "provision_id": provision_id,
                "breadcrumb": source.get("breadcrumb"),
                "text": source.get("text"),
            }
            for provision_id, source in source_by_id.items()
        ],
    }
