from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import os
from time import perf_counter
from typing import Any

import pytest

from backend.app.generation.rag_graph import answer_question
from backend.evaluation.metrics import enabled_cases, evaluate_response
from backend.evaluation.reporting import (
    aggregate_results,
    write_json_atomic,
    write_report_bundle,
)


pytestmark = [
    pytest.mark.evaluation,
    pytest.mark.skipif(
        os.getenv("RUN_RAG_EVALUATION") != "1",
        reason="Set RUN_RAG_EVALUATION=1 để cho phép benchmark gọi RAG/replay.",
    ),
]


def _infrastructure_result(
    case: dict[str, Any],
    message: str,
    latency_seconds: float | None,
) -> dict[str, Any]:
    return {
        "case_id": case["id"],
        "category": case["category"],
        "question": case["question"],
        "answer": "",
        "infrastructure_error": message,
        "latency_seconds": latency_seconds,
    }


def _response_cache_payload(
    dataset: dict[str, Any],
    cache: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    canonical_dataset = json.dumps(
        dataset,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return {
        "dataset": {
            "name": dataset.get("name"),
            "version": dataset.get("version"),
            "sha256": hashlib.sha256(canonical_dataset).hexdigest(),
        },
        "responses": cache,
    }


def _call_live_rag(case: dict[str, Any]) -> tuple[dict[str, Any] | None, float, str | None]:
    started_at = perf_counter()
    try:
        response = answer_question(case["question"])
        latency_seconds = perf_counter() - started_at
        if not isinstance(response, dict):
            raise TypeError("RAG response phải là JSON object/dict.")
        return response, latency_seconds, None
    except Exception as exc:
        return None, perf_counter() - started_at, repr(exc)


def test_rag_benchmark_generates_report(
    evaluation_config,
    evaluation_dataset,
    corpus_by_id,
    recorded_responses,
    human_reviews,
):
    generated_review_path = (
        evaluation_config.output_dir / "human_review_template.csv"
    ).resolve()
    if (
        evaluation_config.human_review_path is not None
        and evaluation_config.human_review_path == generated_review_path
    ):
        pytest.fail(
            "--eval-output-dir phải khác thư mục chứa human review đầu vào để "
            "không ghi đè nhãn chuyên gia."
        )

    cases = enabled_cases(evaluation_dataset)
    if evaluation_config.max_cases:
        cases = cases[: evaluation_config.max_cases]

    if evaluation_config.human_review_path is not None:
        incomplete_reviews = [
            case["id"]
            for case in cases
            if case["id"] not in human_reviews
            or (
                bool(case.get("gold_citation_groups"))
                and not isinstance(
                    human_reviews[case["id"]].get("citation_correct"), bool
                )
            )
            or not isinstance(human_reviews[case["id"]].get("answer_correct"), bool)
            or not isinstance(
                human_reviews[case["id"]].get("hallucination_present"), bool
            )
        ]
        if incomplete_reviews:
            pytest.fail(
                "Human review phải có answer/hallucination cho mọi case và "
                "citation cho case trong phạm vi; thiếu: "
                + ", ".join(incomplete_reviews)
            )

    replay_mode = evaluation_config.responses_path is not None
    response_cache = dict(recorded_responses)
    live_errors: dict[str, tuple[str, float | None]] = {}
    results: list[dict[str, Any]] = []

    if not replay_mode:
        pending_cases = [
            case
            for case in cases
            if not (evaluation_config.resume and case["id"] in response_cache)
        ]
        with ThreadPoolExecutor(max_workers=evaluation_config.workers) as executor:
            futures = {
                executor.submit(_call_live_rag, case): case
                for case in pending_cases
            }
            for future in as_completed(futures):
                case = futures[future]
                response, latency_seconds, error = future.result()
                if error is not None or response is None:
                    live_errors[case["id"]] = (
                        error or "RAG không trả response.",
                        latency_seconds,
                    )
                    continue
                response_cache[case["id"]] = {
                    "response": response,
                    "latency_seconds": latency_seconds,
                }
                write_json_atomic(
                    evaluation_config.output_dir / "responses.json",
                    _response_cache_payload(evaluation_dataset, response_cache),
                )

    for case in cases:
        latency_seconds: float | None = None
        try:
            cached = response_cache.get(case["id"])
            if cached is None:
                if case["id"] in live_errors:
                    message, latency_seconds = live_errors[case["id"]]
                    raise RuntimeError(message)
                raise KeyError(f"Replay thiếu response cho case {case['id']}")
            response = cached["response"]
            latency_seconds = cached.get("latency_seconds")
            result = evaluate_response(
                case,
                response,
                corpus_by_id,
                human_reviews.get(case["id"]),
            )
            result["latency_seconds"] = latency_seconds
            result["infrastructure_error"] = None
        except Exception as exc:  # tiếp tục để báo cáo đủ lỗi thay vì dừng giữa benchmark
            result = _infrastructure_result(case, repr(exc), latency_seconds)
        results.append(result)

    write_json_atomic(
        evaluation_config.output_dir / "responses.json",
        _response_cache_payload(evaluation_dataset, response_cache),
    )

    summary = aggregate_results(
        results,
        citation_target=evaluation_config.citation_target,
        hallucination_target=evaluation_config.hallucination_target,
        answer_target=evaluation_config.answer_target,
    )
    is_retest = evaluation_dataset.get("validation_profile") == "retest_three_groups"
    is_official_run = evaluation_config.is_official_run and not is_retest
    summary["run"] = {
        "mode": (
            "replay"
            if replay_mode
            else ("live-resume" if evaluation_config.resume else "live")
        ),
        "official_full_dataset": is_official_run,
        "validation_profile": evaluation_dataset.get(
            "validation_profile", "official"
        ),
        "max_cases": evaluation_config.max_cases,
        "dataset_path": str(evaluation_config.dataset_path),
        "responses_path": (
            str(evaluation_config.responses_path)
            if evaluation_config.responses_path
            else str(evaluation_config.output_dir / "responses.json")
        ),
        "human_review_path": (
            str(evaluation_config.human_review_path)
            if evaluation_config.human_review_path
            else None
        ),
        "dataset_sha256": _response_cache_payload(
            evaluation_dataset, {}
        )["dataset"]["sha256"],
    }
    dataset_metadata = {
        key: value for key, value in evaluation_dataset.items() if key != "cases"
    }
    write_report_bundle(
        evaluation_config.output_dir,
        dataset_metadata,
        results,
        summary,
    )

    print(f"\nEvaluation report: {evaluation_config.output_dir / 'report.md'}")
    print(f"Citation Accuracy: {summary['metrics']['citation_accuracy']}")
    print(f"Answer Correctness: {summary['metrics']['answer_correctness']}")
    print(f"Hallucination Rate: {summary['metrics']['hallucination_rate']}")

    failures: list[str] = []
    if summary["infrastructure_errors"]:
        failures.append(
            f"Có {summary['infrastructure_errors']} lỗi hạ tầng; xem case_results.json."
        )

    if is_official_run:
        checks = summary["threshold_checks"]
        if not checks["citation_accuracy_at_least_target"]:
            failures.append(
                "Citation Accuracy thấp hơn ngưỡng "
                f"{evaluation_config.citation_target:.2%}."
            )
        if not checks["hallucination_rate_at_most_target"]:
            failures.append(
                "Hallucination Rate cao hơn ngưỡng "
                f"{evaluation_config.hallucination_target:.2%}."
            )
        if (
            evaluation_config.answer_target is not None
            and not checks["answer_correctness_at_least_target"]
        ):
            failures.append(
                "Answer Correctness thấp hơn ngưỡng "
                f"{evaluation_config.answer_target:.2%}."
            )

    assert not failures, "\n".join(failures)
