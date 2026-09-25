"""Tổng hợp và xuất artifact benchmark cho báo cáo/khóa luận."""

from __future__ import annotations

from collections import Counter
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
from statistics import mean
from typing import Any, Iterable


def _ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _average(values: Iterable[float | None]) -> float | None:
    filtered = [float(value) for value in values if value is not None]
    return mean(filtered) if filtered else None


def _wilson_interval(successes: int, total: int, z: float = 1.96) -> list[float] | None:
    """Khoảng tin cậy Wilson 95% cho một tỷ lệ nhị thức."""
    if total == 0:
        return None
    proportion = successes / total
    denominator = 1 + (z**2 / total)
    centre = proportion + (z**2 / (2 * total))
    margin = z * (
        (proportion * (1 - proportion) / total + z**2 / (4 * total**2)) ** 0.5
    )
    return [
        max(0.0, (centre - margin) / denominator),
        min(1.0, (centre + margin) / denominator),
    ]


def _category_summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    citation_cases = [result for result in results if result["citation_group_count"] > 0]
    return {
        "cases": len(results),
        "citation_correct": sum(
            bool(result["citation_exact"]) for result in citation_cases
        ),
        "citation_evaluated": len(citation_cases),
        "answer_correct": sum(bool(result["answer_correct"]) for result in results),
        "answer_evaluated": len(results),
        "hallucination_present": sum(
            bool(result["hallucination_present"]) for result in results
        ),
        "hallucination_evaluated": len(results),
        "status_accuracy": _average(float(result["status_correct"]) for result in results),
        "citation_accuracy": _average(
            float(result["citation_exact"]) for result in citation_cases
        ),
        "answer_correctness": _average(
            float(result["answer_correct"]) for result in results
        ),
        "hallucination_rate": _average(
            float(result["hallucination_present"]) for result in results
        ),
        "mean_latency_seconds": _average(result.get("latency_seconds") for result in results),
    }


def aggregate_results(
    results: list[dict[str, Any]],
    citation_target: float = 0.85,
    hallucination_target: float = 0.05,
    answer_target: float | None = None,
) -> dict[str, Any]:
    successful = [result for result in results if not result.get("infrastructure_error")]
    citation_cases = [result for result in successful if result["citation_group_count"] > 0]
    out_of_scope_cases = [
        result for result in successful if result["category"] == "out_of_scope"
    ]
    temporal_cases = [
        result for result in successful if result["category"] == "temporal_aware"
    ]

    predicted_total = sum(result["predicted_citation_count"] for result in citation_cases)
    correct_total = sum(result["correct_citation_count"] for result in citation_cases)
    gold_group_total = sum(result["citation_group_count"] for result in citation_cases)
    hit_group_total = sum(result["citation_groups_hit"] for result in citation_cases)
    citation_precision = _ratio(correct_total, predicted_total)
    citation_recall = _ratio(hit_group_total, gold_group_total)
    citation_f1 = None
    if citation_precision is not None and citation_recall is not None:
        citation_f1 = (
            0.0
            if citation_precision + citation_recall == 0
            else 2 * citation_precision * citation_recall / (citation_precision + citation_recall)
        )

    citation_accuracy = _average(
        float(result["citation_exact"]) for result in citation_cases
    )
    answer_correctness = _average(
        float(result["answer_correct"]) for result in successful
    )
    hallucination_rate = _average(
        float(result["hallucination_present"]) for result in successful
    )
    out_of_scope_accuracy = _average(
        float(result["out_of_scope_correct"]) for result in out_of_scope_cases
    )
    temporal_accuracy = _average(
        float(result["temporal_correct"]) for result in temporal_cases
    )
    citation_correct_cases = sum(bool(result["citation_exact"]) for result in citation_cases)
    answer_correct_cases = sum(bool(result["answer_correct"]) for result in successful)
    hallucination_cases = sum(
        bool(result["hallucination_present"]) for result in successful
    )
    out_of_scope_correct_cases = sum(
        bool(result["out_of_scope_correct"]) for result in out_of_scope_cases
    )
    temporal_correct_cases = sum(
        bool(result["temporal_correct"]) for result in temporal_cases
    )

    by_category = {
        category: _category_summary(
            [result for result in successful if result["category"] == category]
        )
        for category in sorted({result["category"] for result in successful})
    }
    scoring_modes = Counter(result["answer_scoring_mode"] for result in successful)
    citation_scoring_modes = Counter(
        result["citation_scoring_mode"] for result in successful
    )

    threshold_checks: dict[str, bool | None] = {
        "citation_accuracy_at_least_target": (
            citation_accuracy is not None and citation_accuracy >= citation_target
        ),
        "hallucination_rate_at_most_target": (
            hallucination_rate is not None and hallucination_rate <= hallucination_target
        ),
        "answer_correctness_at_least_target": (
            None
            if answer_target is None
            else answer_correctness is not None and answer_correctness >= answer_target
        ),
        "no_infrastructure_errors": len(successful) == len(results),
    }

    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "total_cases": len(results),
        "successful_cases": len(successful),
        "infrastructure_errors": len(results) - len(successful),
        "category_counts": dict(Counter(result["category"] for result in results)),
        "answer_scoring_modes": dict(scoring_modes),
        "citation_scoring_modes": dict(citation_scoring_modes),
        "metrics": {
            # Chỉ tiêu chính: tỷ lệ câu có toàn bộ citation đúng và không có citation thừa.
            "citation_accuracy": citation_accuracy,
            "citation_precision_micro": citation_precision,
            "citation_recall_micro": citation_recall,
            "citation_f1_micro": citation_f1,
            "answer_correctness": answer_correctness,
            "mean_answer_token_f1": _average(
                result.get("answer_token_f1") for result in successful
            ),
            "hallucination_rate": hallucination_rate,
            "out_of_scope_accuracy": out_of_scope_accuracy,
            "temporal_accuracy": temporal_accuracy,
            "status_accuracy": _average(
                float(result["status_correct"]) for result in successful
            ),
            "mean_latency_seconds": _average(
                result.get("latency_seconds") for result in successful
            ),
        },
        "counts": {
            "citation_correct": citation_correct_cases,
            "citation_evaluated": len(citation_cases),
            "answer_correct": answer_correct_cases,
            "answer_evaluated": len(successful),
            "hallucination_present": hallucination_cases,
            "hallucination_evaluated": len(successful),
            "out_of_scope_correct": out_of_scope_correct_cases,
            "out_of_scope_evaluated": len(out_of_scope_cases),
            "temporal_correct": temporal_correct_cases,
            "temporal_evaluated": len(temporal_cases),
        },
        "confidence_intervals_95": {
            "citation_accuracy": _wilson_interval(
                citation_correct_cases, len(citation_cases)
            ),
            "answer_correctness": _wilson_interval(
                answer_correct_cases, len(successful)
            ),
            "hallucination_rate": _wilson_interval(
                hallucination_cases, len(successful)
            ),
            "out_of_scope_accuracy": _wilson_interval(
                out_of_scope_correct_cases, len(out_of_scope_cases)
            ),
            "temporal_accuracy": _wilson_interval(
                temporal_correct_cases, len(temporal_cases)
            ),
        },
        "targets": {
            "citation_accuracy_min": citation_target,
            "hallucination_rate_max": hallucination_target,
            "answer_correctness_min": answer_target,
        },
        "threshold_checks": threshold_checks,
        "by_category": by_category,
    }


def write_json_atomic(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    with temporary.open("w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)
        file.write("\n")
    temporary.replace(path)


def _format_percent(value: float | None) -> str:
    return "N/A" if value is None else f"{value * 100:.2f}%"


def _format_interval(value: list[float] | None) -> str:
    if value is None:
        return "N/A"
    return f"{value[0] * 100:.2f}%–{value[1] * 100:.2f}%"


def _format_count_percent(count: int, total: int, value: float | None) -> str:
    if total == 0 or value is None:
        return "N/A"
    return f"{count}/{total} ({_format_percent(value)})"


def _write_case_csv(path: Path, results: list[dict[str, Any]]) -> None:
    fields = [
        "case_id",
        "category",
        "actual_status",
        "status_correct",
        "status_semantics_correct",
        "claim_citation_contract_correct",
        "citation_exact",
        "automatic_citation_exact",
        "citation_scoring_mode",
        "citation_precision",
        "citation_recall",
        "answer_correct",
        "answer_scoring_mode",
        "fact_coverage",
        "answer_token_f1",
        "hallucination_present",
        "out_of_scope_correct",
        "temporal_correct",
        "expected_warnings_present",
        "latency_seconds",
        "predicted_citation_ids",
        "extraneous_citation_ids",
        "unreferenced_source_ids",
        "hallucination_reasons",
        "infrastructure_error",
        "review_notes",
        "question",
        "answer",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        for result in results:
            row = {field: result.get(field) for field in fields}
            row["predicted_citation_ids"] = " | ".join(result.get("predicted_citation_ids", []))
            row["extraneous_citation_ids"] = " | ".join(result.get("extraneous_citation_ids", []))
            row["unreferenced_source_ids"] = " | ".join(result.get("unreferenced_source_ids", []))
            row["hallucination_reasons"] = " | ".join(result.get("hallucination_reasons", []))
            writer.writerow(row)


def _write_human_review_template(path: Path, results: list[dict[str, Any]]) -> None:
    fields = [
        "case_id",
        "category",
        "question",
        "system_answer",
        "gold_citation_groups",
        "claims_for_review",
        "citation_sources_for_review",
        "citation_correct",
        "answer_correct",
        "hallucination_present",
        "notes",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        for result in results:
            writer.writerow(
                {
                    "case_id": result["case_id"],
                    "category": result["category"],
                    "question": result["question"],
                    "system_answer": result.get("answer", ""),
                    "gold_citation_groups": json.dumps(
                        result.get("gold_citation_groups", []), ensure_ascii=False
                    ),
                    "claims_for_review": json.dumps(
                        result.get("claims_for_review", []), ensure_ascii=False
                    ),
                    "citation_sources_for_review": json.dumps(
                        result.get("citation_sources_for_review", []),
                        ensure_ascii=False,
                    ),
                    "citation_correct": "",
                    "answer_correct": "",
                    "hallucination_present": "",
                    "notes": "",
                }
            )


def _write_markdown(
    path: Path,
    dataset_metadata: dict[str, Any],
    summary: dict[str, Any],
) -> None:
    metrics = summary["metrics"]
    counts = summary["counts"]
    intervals = summary["confidence_intervals_95"]
    checks = summary["threshold_checks"]
    lines = [
        "# Báo cáo đánh giá hệ thống RAG pháp luật",
        "",
        f"- Dataset: `{dataset_metadata.get('name', 'Không đặt tên')}`",
        f"- Phiên bản: `{dataset_metadata.get('version', 'N/A')}`",
        f"- Số câu đã chạy: **{summary['total_cases']}**",
        f"- Lỗi hạ tầng: **{summary['infrastructure_errors']}**",
        f"- Chế độ chạy: **{summary.get('run', {}).get('mode', 'N/A')}**",
        f"- Toàn bộ dataset chính thức: **{'Có' if summary.get('run', {}).get('official_full_dataset') else 'Không'}**",
        f"- Dataset SHA-256: `{summary.get('run', {}).get('dataset_sha256', 'N/A')}`",
        f"- Chế độ chấm Answer Correctness: `{summary['answer_scoring_modes']}`",
        f"- Chế độ chấm Citation Accuracy: `{summary['citation_scoring_modes']}`",
        "",
        "## Chỉ tiêu chính",
        "",
        "| Chỉ tiêu | Kết quả | n | KTC Wilson 95% | Mục tiêu | Đạt |",
        "|---|---:|---:|---:|---:|:---:|",
        (
            f"| Citation Accuracy | {_format_percent(metrics['citation_accuracy'])} "
            f"| {counts['citation_evaluated']} | {_format_interval(intervals['citation_accuracy'])} "
            f"| ≥ {_format_percent(summary['targets']['citation_accuracy_min'])} "
            f"| {'Có' if checks['citation_accuracy_at_least_target'] else 'Không'} |"
        ),
        (
            f"| Answer Correctness | {_format_percent(metrics['answer_correctness'])} "
            f"| {counts['answer_evaluated']} | {_format_interval(intervals['answer_correctness'])} "
            f"| {_format_percent(summary['targets']['answer_correctness_min'])} "
            f"| {'N/A' if checks['answer_correctness_at_least_target'] is None else ('Có' if checks['answer_correctness_at_least_target'] else 'Không')} |"
        ),
        (
            f"| Hallucination Rate | {_format_percent(metrics['hallucination_rate'])} "
            f"| {counts['hallucination_evaluated']} | {_format_interval(intervals['hallucination_rate'])} "
            f"| ≤ {_format_percent(summary['targets']['hallucination_rate_max'])} "
            f"| {'Có' if checks['hallucination_rate_at_most_target'] else 'Không'} |"
        ),
        f"| Out-of-scope Accuracy | {_format_percent(metrics['out_of_scope_accuracy'])} | {counts['out_of_scope_evaluated']} | {_format_interval(intervals['out_of_scope_accuracy'])} | Chưa đặt | N/A |",
        f"| Temporal Accuracy | {_format_percent(metrics['temporal_accuracy'])} | {counts['temporal_evaluated']} | {_format_interval(intervals['temporal_accuracy'])} | Chưa đặt | N/A |",
        "",
        "## Chỉ tiêu citation bổ sung",
        "",
        f"- Micro precision: **{_format_percent(metrics['citation_precision_micro'])}**",
        f"- Micro recall: **{_format_percent(metrics['citation_recall_micro'])}**",
        f"- Micro F1: **{_format_percent(metrics['citation_f1_micro'])}**",
        "",
        "## Kết quả theo nhóm",
        "",
        "| Nhóm | Số câu | Citation đúng | Câu trả lời đúng | Câu bị Hallucination |",
        "|---|---:|---:|---:|---:|",
    ]
    for category, values in summary["by_category"].items():
        lines.append(
            f"| {category} | {values['cases']} | "
            f"{_format_count_percent(values['citation_correct'], values['citation_evaluated'], values['citation_accuracy'])} | "
            f"{_format_count_percent(values['answer_correct'], values['answer_evaluated'], values['answer_correctness'])} | "
            f"{_format_count_percent(values['hallucination_present'], values['hallucination_evaluated'], values['hallucination_rate'])} |"
        )
    lines.extend(
        [
            "",
            "## Ghi chú phương pháp",
            "",
            "Citation Accuracy là tỷ lệ câu có đủ mọi nhóm provision_id chuẩn, không có citation thừa và không vi phạm invariant evidence → sources.",
            "",
            "Answer Correctness dùng fact rubric xác định trước. Khi có file human review, nhãn chuyên gia thay thế điểm rubric nhưng vẫn chịu hard guard về status.",
            "",
            "Citation review của chuyên gia kiểm tra quan hệ nội dung claim ↔ nguồn. Nhãn tay không thể ghi đè lỗi provision_id, source hoặc corpus.",
            "",
            "Hallucination Rate tự động phát hiện citation không có nguồn, nguồn không khớp corpus, fact bị cấm và out-of-scope không từ chối an toàn. Kết quả dùng trong báo cáo chính thức nên kèm human review.",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def write_report_bundle(
    output_dir: Path,
    dataset_metadata: dict[str, Any],
    results: list[dict[str, Any]],
    summary: dict[str, Any],
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    write_json_atomic(output_dir / "summary.json", summary)
    write_json_atomic(output_dir / "case_results.json", results)
    _write_case_csv(output_dir / "case_results.csv", results)
    _write_human_review_template(output_dir / "human_review_template.csv", results)
    _write_markdown(output_dir / "report.md", dataset_metadata, summary)
