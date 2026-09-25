"""
temporal_matrix_builder.py
===========================
Cơ chế TEMPORAL FILTER — tầng 2 (corpus-level).

Chạy SAU KHI parser.py / parser_nghidinh.py đã parse toàn bộ corpus.
Mỗi văn bản tạo ra một file JSON chứa list chunk, trong đó mỗi chunk đã có:
    - provision_id
    - provision_key
    - valid_from
    - valid_to = None (ở tầng parser)
    - doc_id
    - các metadata cấu trúc khác

Điểm quan trọng:
Một provision_key có thể có NHIỀU chunk con trong CÙNG một phiên bản pháp lý.
Ví dụ Khoản 2 Điều 3 bị semantic chunking tách thành Điểm a, b, c, ... thì tất
cả các chunk đó vẫn thuộc cùng version nếu có cùng provision_key + valid_from.
Do đó tầng corpus KHÔNG được coi từng chunk là một phiên bản nối tiếp nhau.

Thuật toán:
  1. Đọc toàn bộ file chunk JSON trong thư mục corpus.
  2. Gom theo provision_key.
  3. Trong từng provision_key, gom tiếp theo valid_from => một VERSION.
  4. Sắp xếp các version theo valid_from tăng dần.
  5. valid_to của version i = valid_from(version i+1) - 1 ngày.
  6. Gắn cùng valid_to cho TOÀN BỘ chunk con thuộc version đó.
  7. Version cuối cùng có valid_to = None.
  8. Chunk thiếu valid_from được đưa vào unresolved và needs_manual_review=True.

Report mặc định được ghi NGAY TRONG thư mục chunks:
    data/chunks/hieu_luc_matrix_report.json

Loader tự loại file report ra khỏi glob, nên script có thể chạy lại nhiều lần.
"""

import glob
import json
import os
from collections import defaultdict
from copy import deepcopy
from datetime import date, timedelta
from typing import Optional


DEFAULT_CHUNKS_GLOB = "data/chunks/*.json"
DEFAULT_REPORT_NAME = "hieu_luc_matrix_report.json"


def _is_iso_date(value: Optional[str]) -> bool:
    if not value:
        return False
    try:
        date.fromisoformat(value)
        return True
    except (TypeError, ValueError):
        return False


def _default_report_path(json_glob_pattern: str) -> str:
    """Đặt report cùng thư mục với các file chunk."""
    parent = os.path.dirname(json_glob_pattern) or "."
    return os.path.join(parent, DEFAULT_REPORT_NAME)


def load_all_chunks(
    json_glob_pattern: str,
    exclude_paths: Optional[list[str]] = None,
) -> list:
    """
    Đọc toàn bộ file JSON chunk khớp glob.

    An toàn khi report nằm chung thư mục chunks:
      - loại các path trong exclude_paths;
      - bỏ qua hieu_luc_matrix_report.json;
      - chỉ nhận file JSON có root là list;
      - chỉ nhận phần tử kiểu dict.
    """
    excluded = {os.path.abspath(p) for p in (exclude_paths or [])}
    chunks = []

    for path in sorted(glob.glob(json_glob_pattern)):
        abs_path = os.path.abspath(path)

        if abs_path in excluded or os.path.basename(path) == DEFAULT_REPORT_NAME:
            continue

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if not isinstance(data, list):
            print(f"Bỏ qua {path}: root JSON không phải list chunk.")
            continue

        valid_items = [item for item in data if isinstance(item, dict)]
        if len(valid_items) != len(data):
            print(f"Cảnh báo {path}: bỏ qua {len(data) - len(valid_items)} phần tử không phải object.")

        chunks.extend(valid_items)

    return chunks


def _version_identity(chunk: dict) -> tuple:
    """
    Nhận diện một VERSION pháp lý trong cùng provision_key.

    valid_from là trục thời gian chính. doc_id được kèm theo để tránh hai văn bản
    khác nhau vô tình có cùng ngày hiệu lực bị nhập làm một version duy nhất.

    Nếu hệ thống sau này có amendment_source/version_id chuẩn hóa riêng thì có
    thể thay hàm này bằng khóa ổn định hơn.
    """
    return (
        chunk.get("valid_from"),
        chunk.get("doc_id"),
        chunk.get("amendment_source"),
    )


def build_validity_matrix(chunks: list) -> dict:
    """
    Dựng ma trận hiệu lực theo cấu trúc:

    {
      provision_key: {
        "versions": [
          {
            "valid_from": "YYYY-MM-DD",
            "valid_to": "YYYY-MM-DD" | None,
            "doc_id": "...",
            "chunks": [chunk, chunk, ...]
          }
        ],
        "unresolved": [chunk, ...]
      }
    }

    Mỗi version có thể chứa nhiều chunk con (ví dụ nhiều Điểm của cùng Khoản).
    Tất cả chunk trong cùng version nhận cùng valid_from / valid_to.
    """
    by_key = defaultdict(list)
    for original in chunks:
        key = original.get("provision_key")
        if not key:
            continue
        # Không sửa trực tiếp object nguồn do parser sinh ra.
        by_key[key].append(deepcopy(original))

    matrix = {}

    for provision_key, group in by_key.items():
        dated = []
        unresolved = []

        for chunk in group:
            valid_from = chunk.get("valid_from")
            if _is_iso_date(valid_from):
                dated.append(chunk)
            else:
                chunk["valid_to"] = None
                chunk["needs_manual_review"] = True
                unresolved.append(chunk)

        # Nhóm các chunk cùng một version pháp lý.
        version_groups = defaultdict(list)
        for chunk in dated:
            version_groups[_version_identity(chunk)].append(chunk)

        versions = []
        for identity, version_chunks in version_groups.items():
            valid_from, doc_id, amendment_source = identity
            versions.append(
                {
                    "valid_from": valid_from,
                    "valid_to": None,
                    "doc_id": doc_id,
                    "amendment_source": amendment_source,
                    "chunks": version_chunks,
                }
            )

        # Sắp theo ngày hiệu lực; tie-break bằng doc_id để output ổn định.
        versions.sort(
            key=lambda v: (
                v["valid_from"],
                v.get("doc_id") or "",
                v.get("amendment_source") or "",
            )
        )

        # Tính valid_to theo VERSION, không phải theo từng chunk con.
        for idx, version in enumerate(versions):
            if idx + 1 < len(versions):
                next_from = date.fromisoformat(versions[idx + 1]["valid_from"])
                valid_to = (next_from - timedelta(days=1)).isoformat()
            else:
                valid_to = None

            version["valid_to"] = valid_to
            for chunk in version["chunks"]:
                chunk["valid_to"] = valid_to
                chunk.setdefault("needs_manual_review", False)

        matrix[provision_key] = {
            "versions": versions,
            "unresolved": unresolved,
        }

    return matrix


def query_effective_provision(
    matrix: dict,
    provision_key: str,
    as_of: str = None,
) -> list:
    """
    Trả về TOÀN BỘ chunk thuộc version đang hiệu lực của provision_key tại as_of.

    Khác bản cũ trả về đúng 1 chunk, hàm này trả về list vì một version có thể
    gồm nhiều Điểm con sau semantic chunking.

    Trả về [] nếu:
      - provision_key không tồn tại;
      - chưa có version có hiệu lực ở thời điểm as_of;
      - dữ liệu chỉ nằm trong unresolved.
    """
    as_of = as_of or date.today().isoformat()
    if not _is_iso_date(as_of):
        raise ValueError(f"as_of phải có dạng YYYY-MM-DD, nhận được: {as_of!r}")

    entry = matrix.get(provision_key)
    if not entry:
        return []

    for version in entry.get("versions", []):
        valid_from = version["valid_from"]
        valid_to = version.get("valid_to") or "9999-12-31"
        if valid_from <= as_of <= valid_to:
            return version.get("chunks", [])

    return []


def export_matrix_report(matrix: dict, output_path: str) -> None:
    """
    Xuất report audit nhưng vẫn giữ cấu trúc version -> chunks để nhìn rõ:
      provision_key
        -> version hiệu lực
          -> các chunk con thuộc version đó

    Không dump toàn bộ text để report gọn hơn; vẫn giữ metadata đủ để audit và
    đối chiếu ngược về file chunk gốc.
    """
    report = {}

    for key, entry in matrix.items():
        report[key] = {
            "versions": [],
            "unresolved": [],
        }

        for version in entry.get("versions", []):
            report[key]["versions"].append(
                {
                    "doc_id": version.get("doc_id"),
                    "amendment_source": version.get("amendment_source"),
                    "valid_from": version.get("valid_from"),
                    "valid_to": version.get("valid_to"),
                    "chunk_count": len(version.get("chunks", [])),
                    "chunks": [
                        {
                            "chunk_id": c.get("chunk_id"),
                            "provision_id": c.get("provision_id"),
                            "level": c.get("level"),
                            "dieu": c.get("dieu"),
                            "khoan": c.get("khoan"),
                            "diem": c.get("diem"),
                            "breadcrumb": c.get("breadcrumb"),
                            "valid_from": c.get("valid_from"),
                            "valid_to": c.get("valid_to"),
                            "is_amendment_text": c.get("is_amendment_text", False),
                            "needs_manual_review": c.get("needs_manual_review", False),
                        }
                        for c in version.get("chunks", [])
                    ],
                }
            )

        report[key]["unresolved"] = [
            {
                "chunk_id": c.get("chunk_id"),
                "doc_id": c.get("doc_id"),
                "provision_id": c.get("provision_id"),
                "level": c.get("level"),
                "dieu": c.get("dieu"),
                "khoan": c.get("khoan"),
                "diem": c.get("diem"),
                "breadcrumb": c.get("breadcrumb"),
                "valid_from": c.get("valid_from"),
                "valid_to": c.get("valid_to"),
                "temporal_incomplete": c.get("temporal_incomplete", False),
                "needs_manual_review": True,
            }
            for c in entry.get("unresolved", [])
        ]

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)


def main(
    chunks_glob: str = DEFAULT_CHUNKS_GLOB,
    report_path: Optional[str] = None,
):
    report_path = report_path or _default_report_path(chunks_glob)

    all_chunks = load_all_chunks(
        chunks_glob,
        exclude_paths=[report_path],
    )
    if not all_chunks:
        raise ValueError(f"Không tìm thấy chunk hợp lệ từ glob: {chunks_glob}")

    matrix = build_validity_matrix(all_chunks)
    export_matrix_report(matrix, report_path)

    total_versions = sum(len(v.get("versions", [])) for v in matrix.values())
    total_unresolved = sum(len(v.get("unresolved", [])) for v in matrix.values())

    print(f"Đã đọc {len(all_chunks)} chunk.")
    print(f"Đã dựng ma trận cho {len(matrix)} provision_key / {total_versions} version.")
    print(f"Chunk cần review thủ công: {total_unresolved}.")
    print(f"Report: {report_path}")

    return matrix


if __name__ == "__main__":
    main()
