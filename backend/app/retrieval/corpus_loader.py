"""Tìm và nạp corpus chunk JSON."""

from __future__ import annotations

import glob
import json
import os


def resolve_input_files(path_or_pattern: str) -> list[str]:
    if os.path.isfile(path_or_pattern):
        return [path_or_pattern]
    if os.path.isdir(path_or_pattern):
        return sorted(glob.glob(os.path.join(path_or_pattern, "*.json")))
    return sorted(glob.glob(path_or_pattern))


def load_chunks(path_or_pattern: str) -> list[dict]:
    paths = resolve_input_files(path_or_pattern)
    if not paths:
        raise FileNotFoundError(f"Không tìm thấy corpus chunk: {path_or_pattern}")

    chunks: list[dict] = []
    for path in paths:
        with open(path, "r", encoding="utf-8") as file:
            data = json.load(file)
        if not isinstance(data, list):
            raise ValueError(f"{path} không phải JSON list.")
        for chunk in data:
            if not isinstance(chunk, dict):
                raise ValueError(f"Chunk trong {path} không phải JSON object.")
            if "provision_id" not in chunk or "text" not in chunk:
                raise ValueError(
                    f"Chunk thiếu provision_id/text: {path}#{chunk.get('chunk_id')}"
                )
            chunks.append(chunk)

    # Dedupe vật lý theo provision_id, giữ bản cuối cùng.
    by_id = {chunk["provision_id"]: chunk for chunk in chunks}
    return list(by_id.values())
