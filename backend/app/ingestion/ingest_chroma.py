"""
Ingest corpus chunks vào ChromaDB cho chatbot AI Luật có Temporal Filter.

Pipeline:
    parser -> chunks/*.json -> ingest_chroma.py -> ChromaDB
                               (text + legal metadata + temporal metadata)

Ví dụ:
    python ingest_chroma.py --chunks "data/chunks/*.json" --rebuild
    python ingest_chroma.py --chunks data/chunks_processed.json --rebuild

Khuyến nghị dùng --rebuild sau khi thay đổi parser/temporal metadata để tránh
entry cũ còn sót trong Chroma.
"""

import argparse
import glob
import json
import os
import shutil
from collections import Counter

CONFIG = {
    "chunks_path": "data/chunks/*.json",
    "chroma_persist_dir": "data/chroma_db",
    "collection_name": "luat_chunks",
    "embedding_model": "bkai-foundation-models/vietnamese-bi-encoder",
    "batch_size": 128,
    "metadata_fields": [
        # document metadata
        "doc_id", "doc_type", "doc_title", "hieu_luc_status", "source_file",
        # structural metadata
        "level", "chuong", "muc", "dieu", "khoan", "diem",
        "breadcrumb", "char_count", "is_amendment_text", "amendment_source",
        # temporal metadata -- BẮT BUỘC để retriever lọc theo thời điểm
        "provision_key", "ngay_thong_qua", "ngay_hieu_luc",
        "hieu_luc_ke_tu_ky", "valid_from", "valid_to",
        "temporal_incomplete", "needs_manual_review",
    ],
}


def _resolve_input_files(path_or_pattern: str) -> list[str]:
    """Nhận 1 JSON, thư mục JSON, hoặc glob pattern và trả về danh sách file."""
    if os.path.isfile(path_or_pattern):
        return [path_or_pattern]
    if os.path.isdir(path_or_pattern):
        return sorted(glob.glob(os.path.join(path_or_pattern, "*.json")))
    return sorted(glob.glob(path_or_pattern))


def load_chunks(path_or_pattern: str) -> list:
    """Đọc toàn corpus; mỗi chunk bắt buộc có provision_id + text."""
    paths = _resolve_input_files(path_or_pattern)
    if not paths:
        raise FileNotFoundError(f"Không tìm thấy file chunk từ: {path_or_pattern}")

    chunks = []
    for path in paths:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, list):
            raise ValueError(f"{path} không phải JSON list các chunk.")
        for c in data:
            if "provision_id" not in c or "text" not in c:
                raise ValueError(
                    f"Chunk thiếu provision_id/text trong {path}: {c.get('chunk_id')}"
                )
            chunks.append(c)

    if not chunks:
        raise ValueError("Corpus chunk rỗng.")
    return chunks


def _sanitize_metadata_value(v):
    """Chroma metadata chỉ nhận str/int/float/bool; None được chuẩn hóa thành ''."""
    if v is None:
        return ""
    if isinstance(v, (str, int, float, bool)):
        return v
    return json.dumps(v, ensure_ascii=False)


def build_metadata(chunk: dict, fields: list) -> dict:
    metadata = {f: _sanitize_metadata_value(chunk.get(f)) for f in fields}
    metadata["provision_id"] = _sanitize_metadata_value(chunk["provision_id"])
    return metadata


def get_embeddings(model_name: str):
    from langchain_huggingface import HuggingFaceEmbeddings
    return HuggingFaceEmbeddings(model_name=model_name)


def get_chroma_store(persist_dir: str, collection_name: str, embeddings):
    try:
        from langchain_chroma import Chroma
    except ImportError:
        from langchain_community.vectorstores import Chroma
    return Chroma(
        collection_name=collection_name,
        embedding_function=embeddings,
        persist_directory=persist_dir,
    )


def _dedupe_by_provision_id(chunks: list) -> list:
    """
    provision_id là ID vật lý của chunk nên phải duy nhất toàn corpus.
    Nếu trùng, giữ bản xuất hiện cuối cùng nhưng cảnh báo rõ.
    """
    counts = Counter(c["provision_id"] for c in chunks)
    dup_ids = [pid for pid, n in counts.items() if n > 1]
    if dup_ids:
        print(
            f"CẢNH BÁO: {len(dup_ids)} provision_id bị trùng toàn corpus; "
            f"ví dụ: {dup_ids[:5]}"
        )
        print("  -> Giữ chunk xuất hiện cuối cùng cho mỗi provision_id.")

    seen = {}
    for c in chunks:
        seen[c["provision_id"]] = c
    return list(seen.values())


def validate_temporal_metadata(chunks: list) -> None:
    missing_key = sum(not c.get("provision_key") for c in chunks)
    missing_from = sum(not c.get("valid_from") for c in chunks)
    incomplete = sum(bool(c.get("temporal_incomplete")) for c in chunks)

    print(
        "Temporal metadata: "
        f"missing provision_key={missing_key}, "
        f"missing valid_from={missing_from}, "
        f"temporal_incomplete={incomplete}"
    )
    if missing_key:
        print("CẢNH BÁO: chunk thiếu provision_key sẽ không được temporal-filter chính xác.")
    if incomplete:
        print(
            "CẢNH BÁO: có chunk temporal_incomplete=True; retriever sẽ gắn cảnh báo "
            "và có thể loại chúng nếu bật strict_temporal."
        )


def ingest(config: dict, rebuild: bool = False) -> int:
    from langchain_core.documents import Document

    persist_dir = config["chroma_persist_dir"]
    if rebuild and os.path.isdir(persist_dir):
        print(f"--rebuild: xoá index cũ tại {persist_dir} ...")
        shutil.rmtree(persist_dir)
    os.makedirs(persist_dir, exist_ok=True)

    chunks = load_chunks(config["chunks_path"])
    chunks = _dedupe_by_provision_id(chunks)
    print(f"Đã đọc {len(chunks)} chunk từ: {config['chunks_path']}")
    validate_temporal_metadata(chunks)

    embeddings = get_embeddings(config["embedding_model"])
    store = get_chroma_store(
        persist_dir, config["collection_name"], embeddings
    )

    docs = []
    ids = []
    for c in chunks:
        docs.append(
            Document(
                page_content=c["text"],
                metadata=build_metadata(c, config["metadata_fields"]),
            )
        )
        ids.append(c["provision_id"])

    batch_size = config["batch_size"]
    total = len(docs)
    for i in range(0, total, batch_size):
        batch_docs = docs[i : i + batch_size]
        batch_ids = ids[i : i + batch_size]
        store.add_documents(batch_docs, ids=batch_ids)
        print(f"  Đã ingest {min(i + batch_size, total)}/{total} chunk...")

    print(
        f"Hoàn tất. Index: {persist_dir} "
        f"(collection: {config['collection_name']})"
    )
    return total


def main():
    parser = argparse.ArgumentParser(
        description="Ingest corpus chunks vào ChromaDB với temporal metadata."
    )
    parser.add_argument(
        "--chunks",
        default=CONFIG["chunks_path"],
        help="File JSON, thư mục, hoặc glob, vd data/chunks/*.json",
    )
    parser.add_argument(
        "--persist-dir",
        default=CONFIG["chroma_persist_dir"],
        help="Thư mục lưu ChromaDB",
    )
    parser.add_argument(
        "--collection",
        default=CONFIG["collection_name"],
        help="Tên collection Chroma",
    )
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Xoá index cũ và build lại từ đầu",
    )
    args = parser.parse_args()

    config = dict(CONFIG)
    config["chunks_path"] = args.chunks
    config["chroma_persist_dir"] = args.persist_dir
    config["collection_name"] = args.collection
    ingest(config, rebuild=args.rebuild)


if __name__ == "__main__":
    main()
