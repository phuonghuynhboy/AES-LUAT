"""Khởi tạo Gemini client và thực hiện generate với retry/fallback model."""

from __future__ import annotations

import json
import logging
import os
import re
import time
from threading import Lock
from typing import Any

from google import genai
from google.genai import types

from .prompts import SYSTEM_PROMPT
from .rag_config import GRAPH_CONFIG

logger = logging.getLogger(__name__)

_client: genai.Client | None = None
_current_model_name: str | None = None
_client_lock = Lock()


def get_api_key() -> str:
    env_name = str(GRAPH_CONFIG["gemini_api_key_env"])
    api_key = os.getenv(env_name, "").strip()
    if not api_key:
        raise RuntimeError(
            f"Thiếu {env_name}. Hãy set biến môi trường {env_name} hoặc khai báo "
            "biến này trong file .env ở thư mục gốc dự án."
        )
    return api_key


def get_client() -> genai.Client:
    """Tạo Gemini client một lần và tái sử dụng cho toàn bộ pipeline."""
    global _client, _current_model_name
    if _client is None:
        with _client_lock:
            if _client is None:
                _client = genai.Client(
                    api_key=get_api_key(),
                    http_options=types.HttpOptions(
                        timeout=int(GRAPH_CONFIG.get("gemini_timeout_ms", 60_000))
                    ),
                )
                _current_model_name = str(GRAPH_CONFIG["gemini_model"])
                logger.debug(
                    "Đã khởi tạo Google GenAI client. Model mặc định: %s",
                    _current_model_name,
                )
    return _client


def response_to_text(response: Any) -> str:
    """Lấy text từ response, kể cả khi SDK không cung cấp ``response.text``."""
    text = getattr(response, "text", None)
    if isinstance(text, str) and text.strip():
        return text.strip()

    parts_text: list[str] = []
    try:
        candidates = getattr(response, "candidates", []) or []
        for candidate in candidates:
            content = getattr(candidate, "content", None)
            parts = getattr(content, "parts", []) if content is not None else []
            for part in parts:
                part_text = getattr(part, "text", None)
                if isinstance(part_text, str) and part_text:
                    parts_text.append(part_text)
    except Exception:
        pass
    return "".join(parts_text).strip()


def is_model_error(error: Exception) -> bool:
    message = str(error).lower()
    return any(
        signal in message
        for signal in ("404", "not found", "not supported", "not available")
    )


def is_overloaded_error(error: Exception) -> bool:
    message = str(error).lower()
    return any(
        signal in message
        for signal in (
            "503",
            "unavailable",
            "high demand",
            "overloaded",
            "deadline exceeded",
            "504",
        )
    )


def is_non_retryable_error(error: Exception) -> bool:
    message = str(error).lower()
    return any(
        signal in message
        for signal in (
            "api key not valid",
            "permission denied",
            "403",
            "invalid_argument",
            "400",
        )
    )


def candidate_models() -> list[str]:
    primary = str(GRAPH_CONFIG["gemini_model"])
    fallbacks = [str(model) for model in GRAPH_CONFIG.get("fallback_models", [])]
    models: list[str] = []
    for model in [primary, *fallbacks]:
        if model and model not in models:
            models.append(model)
    return models


def make_generate_config() -> types.GenerateContentConfig:
    """Tạo config tương thích với nhiều phiên bản google-genai."""
    kwargs: dict[str, Any] = {
        "system_instruction": SYSTEM_PROMPT,
        "temperature": float(GRAPH_CONFIG["temperature"]),
        "max_output_tokens": int(GRAPH_CONFIG["max_output_tokens"]),
    }

    try:
        if hasattr(types, "ThinkingConfig"):
            if hasattr(types, "ThinkingLevel") and hasattr(
                types.ThinkingLevel, "MINIMAL"
            ):
                kwargs["thinking_config"] = types.ThinkingConfig(
                    thinking_level=types.ThinkingLevel.MINIMAL
                )
            else:
                kwargs["thinking_config"] = types.ThinkingConfig(thinking_budget=0)
    except Exception:
        pass
    return types.GenerateContentConfig(**kwargs)


def call_gemini_once(prompt: str, model_name: str) -> str:
    response = get_client().models.generate_content(
        model=model_name,
        contents=prompt,
        config=make_generate_config(),
    )
    answer = response_to_text(response)
    return answer or str(GRAPH_CONFIG["not_found_phrase"])


def looks_incomplete_answer(answer: str) -> bool:
    """Nhận diện JSON bị cắt hoặc câu legacy kết thúc dang dở."""
    text = (answer or "").strip()
    if not text or text == GRAPH_CONFIG["not_found_phrase"]:
        return False

    candidate = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
    candidate = re.sub(r"\s*```$", "", candidate).strip()
    if candidate.startswith("{"):
        try:
            data = json.loads(candidate)
            if isinstance(data, dict) and isinstance(data.get("claims"), list):
                return False
        except json.JSONDecodeError:
            return True

    bad_endings = (
        " theo",
        " tại",
        " của",
        " và",
        " là",
        " tối",
        " diện tích tối",
        "Bộ luật Hàng hải Việt",
        "quy định tại",
        "căn cứ",
    )
    return text.rstrip().endswith(bad_endings)


def generate_with_retry(prompt: str) -> str:
    """Gọi Gemini với retry và chuyển sang fallback model khi cần."""
    global _current_model_name

    max_retries = int(GRAPH_CONFIG["max_retries"])
    backoff = float(GRAPH_CONFIG["retry_backoff_base_sec"])
    last_error: Exception | None = None

    for model_name in candidate_models():
        _current_model_name = model_name
        for attempt in range(1, max_retries + 1):
            try:
                answer = call_gemini_once(prompt, model_name)
                if looks_incomplete_answer(answer):
                    logger.warning(
                        "Gemini trả lời có dấu hiệu bị cắt với model %s. Thử lại/fallback.",
                        model_name,
                    )
                    if attempt < max_retries:
                        time.sleep(backoff * (2 ** (attempt - 1)))
                        continue
                    break
                return answer
            except Exception as error:
                last_error = error
                if is_model_error(error):
                    logger.warning(
                        "Model Gemini không khả dụng: %s. Thử model fallback nếu có. Chi tiết: %s",
                        model_name,
                        error,
                    )
                    break
                if is_non_retryable_error(error):
                    raise RuntimeError(
                        "Lỗi Gemini không thể retry. "
                        f"Model hiện tại: {model_name}. Chi tiết: {error}"
                    ) from error

                logger.warning(
                    "Gọi Gemini API thất bại lần %d/%d với model %s: %s",
                    attempt,
                    max_retries,
                    model_name,
                    error,
                )
                if is_overloaded_error(error):
                    break
                if attempt < max_retries:
                    time.sleep(backoff * (2 ** (attempt - 1)))

    raise RuntimeError(
        f"Gọi Gemini API thất bại. Lỗi cuối: {last_error}"
    ) from last_error
