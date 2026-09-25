"""Small environment-backed settings surface for the HTTP application."""

from __future__ import annotations

import os

DEFAULT_CORS_ORIGINS = (
    "http://localhost:5173",
    "http://127.0.0.1:5173",
)


def cors_origins() -> list[str]:
    configured = os.getenv("BACKEND_CORS_ORIGINS", "")
    if not configured.strip():
        return list(DEFAULT_CORS_ORIGINS)
    # Explicit origins only; wildcard is intentionally rejected.
    origins = [origin.strip().rstrip("/") for origin in configured.split(",") if origin.strip()]
    return [origin for origin in origins if origin != "*"]
