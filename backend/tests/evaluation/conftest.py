from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from typing import Any

import pytest

from backend.app.retrieval.corpus_loader import load_chunks
from backend.app.retrieval.retrieval_config import CONFIG
from backend.evaluation.metrics import load_dataset, validate_dataset


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DATASET = REPOSITORY_ROOT / "backend" / "evaluation" / "questions.json"
DEFAULT_RESULTS_ROOT = REPOSITORY_ROOT / "backend" / "evaluation" / "results"


@dataclass(frozen=True)
class EvaluationConfig:
    dataset_path: Path
    output_dir: Path
    responses_path: Path | None
    human_review_path: Path | None
    citation_target: float
    hallucination_target: float
    answer_target: float | None
    max_cases: int
    resume: bool
    workers: int

    @property
    def is_official_run(self) -> bool:
        return self.max_cases == 0


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("rag-evaluation")
    group.addoption(
        "--eval-dataset",
        default=os.getenv("EVAL_DATASET_PATH", str(DEFAULT_DATASET)),
        help="Đường dẫn đến questions.json đã được chuyên gia duyệt.",
    )
    group.addoption(
        "--eval-output-dir",
        default=os.getenv("EVAL_OUTPUT_DIR", ""),
        help="Thư mục xuất JSON/CSV/Markdown; mặc định tạo run_<UTC timestamp>.",
    )
    group.addoption(
        "--eval-responses",
        default=os.getenv("EVAL_RESPONSES_PATH", ""),
        help="Replay response đã lưu thay vì gọi RAG thật.",
    )
    group.addoption(
        "--eval-human-review",
        default=os.getenv("EVAL_HUMAN_REVIEW_PATH", ""),
        help="CSV nhãn chuyên gia cho Answer Correctness và Hallucination Rate.",
    )
    group.addoption(
        "--eval-min-citation-accuracy",
        type=float,
        default=0.85,
        help="Ngưỡng Citation Accuracy tối thiểu.",
    )
    group.addoption(
        "--eval-max-hallucination-rate",
        type=float,
        default=0.05,
        help="Ngưỡng Hallucination Rate tối đa.",
    )
    group.addoption(
        "--eval-min-answer-correctness",
        type=float,
        default=None,
        help="Ngưỡng Answer Correctness tùy chọn.",
    )
    group.addoption(
        "--eval-max-cases",
        type=int,
        default=0,
        help="Chỉ chạy N case đầu để smoke test; 0 là toàn bộ dataset.",
    )
    group.addoption(
        "--eval-resume",
        action="store_true",
        default=False,
        help="Tiếp tục live run từ responses.json đã có trong output-dir.",
    )
    group.addoption(
        "--eval-workers",
        type=int,
        default=1,
        help="Số case live chạy song song; mặc định 1.",
    )


def _optional_path(value: str) -> Path | None:
    return Path(value).resolve() if value.strip() else None


def _dataset_sha256(dataset: dict[str, Any]) -> str:
    canonical = json.dumps(
        dataset,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


@pytest.fixture(scope="session")
def evaluation_config(pytestconfig: pytest.Config) -> EvaluationConfig:
    output_value = str(pytestconfig.getoption("--eval-output-dir")).strip()
    if output_value:
        output_dir = Path(output_value).resolve()
    else:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        output_dir = DEFAULT_RESULTS_ROOT / f"run_{timestamp}"

    max_cases = int(pytestconfig.getoption("--eval-max-cases"))
    if max_cases < 0:
        pytest.fail("--eval-max-cases phải lớn hơn hoặc bằng 0.")

    config = EvaluationConfig(
        dataset_path=Path(pytestconfig.getoption("--eval-dataset")).resolve(),
        output_dir=output_dir,
        responses_path=_optional_path(str(pytestconfig.getoption("--eval-responses"))),
        human_review_path=_optional_path(
            str(pytestconfig.getoption("--eval-human-review"))
        ),
        citation_target=float(
            pytestconfig.getoption("--eval-min-citation-accuracy")
        ),
        hallucination_target=float(
            pytestconfig.getoption("--eval-max-hallucination-rate")
        ),
        answer_target=pytestconfig.getoption("--eval-min-answer-correctness"),
        max_cases=max_cases,
        resume=bool(pytestconfig.getoption("--eval-resume")),
        workers=int(pytestconfig.getoption("--eval-workers")),
    )
    if not 0 <= config.citation_target <= 1:
        pytest.fail("--eval-min-citation-accuracy phải nằm trong [0, 1].")
    if not 0 <= config.hallucination_target <= 1:
        pytest.fail("--eval-max-hallucination-rate phải nằm trong [0, 1].")
    if config.answer_target is not None and not 0 <= config.answer_target <= 1:
        pytest.fail("--eval-min-answer-correctness phải nằm trong [0, 1].")
    if config.workers < 1 or config.workers > 8:
        pytest.fail("--eval-workers phải nằm trong [1, 8].")
    return config


@pytest.fixture(scope="session")
def corpus_by_id() -> dict[str, dict[str, Any]]:
    return {
        str(chunk["provision_id"]): chunk
        for chunk in load_chunks(CONFIG["chunks_path"])
    }


@pytest.fixture(scope="session")
def raw_evaluation_dataset(evaluation_config: EvaluationConfig) -> dict[str, Any]:
    try:
        return load_dataset(evaluation_config.dataset_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        pytest.fail(str(exc))


@pytest.fixture(scope="session")
def evaluation_dataset(
    raw_evaluation_dataset: dict[str, Any],
    corpus_by_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    errors = validate_dataset(raw_evaluation_dataset, set(corpus_by_id))
    if errors:
        pytest.fail("Dataset không hợp lệ:\n- " + "\n- ".join(errors))
    return raw_evaluation_dataset


def _parse_optional_bool(value: str, *, row_number: int, field: str) -> bool | None:
    normalized = value.strip().casefold()
    if not normalized:
        return None
    if normalized in {"1", "true", "yes", "y", "có", "co", "đúng", "dung"}:
        return True
    if normalized in {"0", "false", "no", "n", "không", "khong", "sai"}:
        return False
    raise ValueError(
        f"Dòng {row_number}, cột {field}: chỉ chấp nhận true/false hoặc để trống."
    )


@pytest.fixture(scope="session")
def human_reviews(evaluation_config: EvaluationConfig) -> dict[str, dict[str, Any]]:
    path = evaluation_config.human_review_path
    if path is None:
        return {}
    if not path.is_file():
        pytest.fail(f"Không tìm thấy file human review: {path}")

    reviews: dict[str, dict[str, Any]] = {}
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as file:
            for row_number, row in enumerate(csv.DictReader(file), start=2):
                case_id = str(row.get("case_id") or "").strip()
                if not case_id:
                    continue
                reviews[case_id] = {
                    "citation_correct": _parse_optional_bool(
                        str(row.get("citation_correct") or ""),
                        row_number=row_number,
                        field="citation_correct",
                    ),
                    "answer_correct": _parse_optional_bool(
                        str(row.get("answer_correct") or ""),
                        row_number=row_number,
                        field="answer_correct",
                    ),
                    "hallucination_present": _parse_optional_bool(
                        str(row.get("hallucination_present") or ""),
                        row_number=row_number,
                        field="hallucination_present",
                    ),
                    "notes": str(row.get("notes") or "").strip(),
                }
    except (OSError, ValueError) as exc:
        pytest.fail(str(exc))
    return reviews


@pytest.fixture(scope="session")
def recorded_responses(evaluation_config: EvaluationConfig) -> dict[str, dict[str, Any]]:
    path = evaluation_config.responses_path
    if path is None and evaluation_config.resume:
        resume_path = evaluation_config.output_dir / "responses.json"
        path = resume_path if resume_path.is_file() else None
    if path is None:
        return {}
    if not path.is_file():
        pytest.fail(f"Không tìm thấy file response để replay: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        pytest.fail(f"Không đọc được response replay {path}: {exc}")

    metadata = payload.get("dataset") if isinstance(payload, dict) else None
    raw_responses = payload.get("responses", payload) if isinstance(payload, dict) else None
    if not isinstance(raw_responses, dict):
        pytest.fail("File replay phải là object hoặc có trường responses là object.")

    if isinstance(metadata, dict):
        current_dataset = load_dataset(evaluation_config.dataset_path)
        expected_sha256 = _dataset_sha256(current_dataset)
        replay_sha256 = metadata.get("sha256")
        if replay_sha256 and replay_sha256 != expected_sha256:
            pytest.fail(
                "Dataset hiện tại không khớp dataset đã sinh responses.json "
                f"({expected_sha256} != {replay_sha256})."
            )
        replay_version = metadata.get("version")
        if replay_version and replay_version != current_dataset.get("version"):
            pytest.fail("Phiên bản dataset hiện tại không khớp file replay.")

    normalized: dict[str, dict[str, Any]] = {}
    for case_id, entry in raw_responses.items():
        if not isinstance(entry, dict):
            continue
        if isinstance(entry.get("response"), dict):
            normalized[str(case_id)] = entry
        else:
            normalized[str(case_id)] = {"response": entry, "latency_seconds": None}
    return normalized
