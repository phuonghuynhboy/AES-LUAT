import os
import re
import json
import unicodedata

from temporal_utils import tag_temporal_fields

CHUNK_CONFIG = {

    "input_path": r"data/dataset/luat/het_hieu_luc_mot_phan/58-2024-QH15.md",
    "output_path": r"data/58-2024-QH15.json", 
    # 1. Pattern nhận diện ranh giới cấp cấu trúc 
    "patterns": {
        "chuong": r"^#{1,2}\s*\*{0,2}Chương\s+([IVXLCDM]+)\b",
        "muc": r"^#{0,3}\s*\*{0,2}Mục\s+(\d+)\b",
        "dieu": r"^#{1,2}\s*\*{0,2}Điều\s+(\d+)\.?\s*(.*)$",
        "khoan": r"^\*{0,2}(\d+)\.\*{0,2}\s+(.*)$",
        "diem": r"^\*{0,2}([a-zđĐ])\)\*{0,2}\s+(.*)$",
    },

    # 2. Ngưỡng ký tự: nếu 1 Khoản dài hơn ngưỡng này VÀ có chứa các Điểm con, thì cắt nhỏ theo cấp Điểm thay vì giữ nguyên cả Khoản.
    "max_khoan_chars": 800,

    # 3. Có gộp breadcrumb (Chương > Điều > Khoản...) vào đầu text của chunk hay không. Bật lên giúp mỗi chunk tự chứa đủ ngữ cảnh khi đưa vào RAG.
    "prepend_breadcrumb": True,

    # 4. Provision ID
    "doc_id_override": None,
}
# ==============================================================================


def _clean_line(line: str) -> str:
    """Chuẩn hóa 1 dòng: bỏ \\r, bỏ ký tự markdown bold thừa ở đầu/cuối, trim."""
    line = line.replace("\r", "")
    return line.strip()


def _is_heading_like(line: str, patterns: dict) -> bool:
    """Kiểm tra 1 dòng có phải là ranh giới cấu trúc (chuong/muc/dieu/khoan/diem)."""
    for key in ("chuong", "muc", "dieu", "khoan", "diem"):
        if re.match(patterns[key], line, re.IGNORECASE):
            return True
    return False


def load_markdown(config: dict) -> list:
    """Đọc file Markdown, trả về danh sách các dòng đã làm sạch (bỏ dòng rỗng)."""
    with open(config["input_path"], "r", encoding="utf-8") as f:
        raw = f.read()
    lines = [_clean_line(l) for l in raw.split("\n")]
    return [l for l in lines if l != ""]


def parse_structure(lines: list, config: dict) -> list:
    """
    Duyệt tuần tự các dòng, dựng cây phân cấp Chương > Mục > Điều > Khoản > Điểm.
    Trả về danh sách các "khoan_unit": mỗi phần tử là 1 Khoản hoàn chỉnh (đã nối
    các dòng tiếp diễn không có số thứ tự), kèm theo các Điểm con (nếu có) và
    đầy đủ breadcrumb (chuong/muc/dieu).

    Cấu trúc mỗi khoan_unit:
    {
        "chuong": "I" | None,
        "chuong_title": "CHẾ ĐỘ CHÍNH TRỊ" | None,
        "muc": "1" | None,
        "dieu": "5" | None,
        "dieu_title": "..." | None,
        "khoan": "2" | None,           # None nếu Điều không có Khoản (đoạn văn đơn)
        "khoan_text": "toàn bộ câu của khoản (đã nối các dòng vỡ)",
        "diem_list": [ {"diem": "a", "text": "..."} , ... ]  # rỗng nếu không có
    }
    """
    pat = config["patterns"]

    cur_chuong = None
    cur_chuong_title = None
    cur_muc = None
    cur_dieu = None
    cur_dieu_title = None

    units = []          # danh sách khoan_unit hoàn chỉnh
    cur_khoan_num = None
    cur_khoan_buf = []          # list các đoạn text (str) thuộc khoản hiện tại (trước khi gặp điểm)
    cur_diem_list = []          # list dict {"diem":..., "buf": [str,...]}
    cur_diem_num = None

    def flush_khoan():
        """Đóng khoản hiện tại lại thành 1 unit và reset buffer."""
        nonlocal cur_khoan_num, cur_khoan_buf, cur_diem_list, cur_diem_num
        # Nếu không có gì để đóng (chưa từng mở khoản/đoạn văn) thì bỏ qua
        if cur_khoan_num is None and not cur_khoan_buf and not cur_diem_list:
            return
        diem_list_final = [
            {"diem": d["diem"], "text": " ".join(d["buf"]).strip()}
            for d in cur_diem_list
            if " ".join(d["buf"]).strip()
        ]
        khoan_text = " ".join(cur_khoan_buf).strip()
        if khoan_text or diem_list_final:
            units.append({
                "chuong": cur_chuong,
                "chuong_title": cur_chuong_title,
                "muc": cur_muc,
                "dieu": cur_dieu,
                "dieu_title": cur_dieu_title,
                "khoan": cur_khoan_num,
                "khoan_text": khoan_text,
                "diem_list": diem_list_final,
            })
        cur_khoan_num = None
        cur_khoan_buf = []
        cur_diem_list = []
        cur_diem_num = None

    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]

        m_chuong = re.match(pat["chuong"], line, re.IGNORECASE)
        m_muc = re.match(pat["muc"], line, re.IGNORECASE)
        m_dieu = re.match(pat["dieu"], line, re.IGNORECASE)
        m_khoan = re.match(pat["khoan"], line)
        m_diem = re.match(pat["diem"], line)

        if m_chuong:
            flush_khoan()
            cur_chuong = m_chuong.group(1)
            cur_muc = None
            cur_dieu = None
            cur_dieu_title = None
            # Dòng liền sau thường là tiêu đề Chương (viết hoa), nếu không phải
            # heading khác thì lấy làm chuong_title.
            if i + 1 < n and not _is_heading_like(lines[i + 1], pat):
                cur_chuong_title = lines[i + 1]
                i += 1
            else:
                cur_chuong_title = None

        elif m_muc:
            flush_khoan()
            cur_muc = m_muc.group(1)

        elif m_dieu:
            flush_khoan()
            cur_dieu = m_dieu.group(1)
            title_on_same_line = m_dieu.group(2).strip() if m_dieu.lastindex and m_dieu.lastindex >= 2 else ""
            title_on_same_line = title_on_same_line.strip("*").strip()
            if title_on_same_line:
                cur_dieu_title = title_on_same_line
            elif i + 1 < n and not _is_heading_like(lines[i + 1], pat):
                # Một số văn bản đặt tên Điều ở dòng riêng ngay dưới heading(chỉ nhận nếu dòng đó KHÔNG phải là khoản/điểm, để tránh nuốt nhầm nội dung Điều không có tiêu đề riêng).
                nxt = lines[i + 1]
                if not re.match(pat["khoan"], nxt) and not re.match(pat["diem"], nxt):
                    cur_dieu_title = None  # để an toàn: văn bản luật VN chuẩn ít khi có
                else:
                    cur_dieu_title = None
            else:
                cur_dieu_title = None

        elif m_khoan:
            flush_khoan()
            cur_khoan_num = m_khoan.group(1)
            cur_khoan_buf = [m_khoan.group(2).strip()]

        elif m_diem:
            diem_letter = m_diem.group(1)
            diem_text = m_diem.group(2).strip()
            cur_diem_num = diem_letter
            cur_diem_list.append({"diem": diem_letter, "buf": [diem_text]})

        else:
            # Dòng tiếp diễn (câu bị ngắt dòng vật lý, không có số/chữ mở đầu).
            # Gắn vào điểm hiện tại nếu đang trong 1 điểm, ngược lại gắn vào khoản,
            # ngược lại nữa thì đây là đoạn văn của Điều không có khoản/điểm
            # (ví dụ Điều 1, Điều 3, Điều 6 trong Hiến pháp 2013).
            if cur_diem_list:
                cur_diem_list[-1]["buf"].append(line)
            elif cur_khoan_num is not None:
                cur_khoan_buf.append(line)
            else:
                cur_khoan_buf.append(line)  # đoạn văn thuần của Điều, khoan=None

        i += 1

    flush_khoan()
    return units


_VN_UPPERCASE_DIACRITIC_MAP = {"Đ": "D", "đ": "d"}

_DOC_SO_RE = re.compile(
    r"(?:Luật\s+số|Số)\s*:\s*([0-9]+\s*/\s*[0-9]{4}\s*/\s*[A-ZĐ][A-ZĐ0-9\-]*)",
    re.IGNORECASE,
)


def _slugify_doc_id(raw: str) -> str:
    """
    Chuẩn hóa số hiệu văn bản (vd '39/2019/QH14', '272/2026/NĐ-CP') thành doc_id
    dùng trong Provision ID. Xem PROVISION_ID_SPEC.md mục 3.
    """
    s = raw.strip()
    for src, dst in _VN_UPPERCASE_DIACRITIC_MAP.items():
        s = s.replace(src, dst)
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.replace("/", "-")
    s = re.sub(r"\s+", "", s)
    s = re.sub(r"-{2,}", "-", s).strip("-")
    return s.upper()


def get_doc_id(config: dict) -> str:
    """
    Xác định doc_id cho toàn bộ văn bản: ưu tiên 'doc_id_override' trong config,
    sau đó tìm dòng 'Số:'/'Luật số:' ở đầu file, cuối cùng fallback về tên file input.
    """
    override = config.get("doc_id_override")
    if override:
        return _slugify_doc_id(override)

    with open(config["input_path"], "r", encoding="utf-8") as f:
        head = f.read(4000)

    m = _DOC_SO_RE.search(head)
    if m:
        return _slugify_doc_id(m.group(1))

    stem = os.path.splitext(os.path.basename(config["input_path"]))[0]
    return _slugify_doc_id(stem)


def build_provision_id(doc_id: str, chunk: dict, seen_ids: dict) -> str:
    """
    Sinh provision_id cho 1 chunk theo Chuẩn Mã Định Danh (PROVISION_ID_SPEC.md).
    'seen_ids' là dict đếm số lần đã gặp mỗi base_id, dùng để chống trùng tự động
    (mục 6 của spec) — đảm bảo mọi chunk luôn có provision_id duy nhất.
    """
    segs = []
    if chunk.get("dieu"):
        segs.append(f"d{chunk['dieu']}")
    if chunk.get("khoan"):
        segs.append(f"k{chunk['khoan']}")
    if chunk.get("diem"):
        segs.append(f"p{chunk['diem']}")

    path = ".".join(segs) if segs else "root"
    base_id = f"{doc_id}#{path}"

    n = seen_ids.get(base_id, 0) + 1
    seen_ids[base_id] = n
    return base_id if n == 1 else f"{base_id}-{n}"


def assign_provision_ids(chunks: list, doc_id: str) -> list:
    """Gán provision_id duy nhất cho từng chunk, theo đúng thứ tự sinh ra."""
    seen_ids = {}
    for chunk in chunks:
        chunk["provision_id"] = build_provision_id(doc_id, chunk, seen_ids)
    return chunks


_DOC_TYPE_HEADING_RE = re.compile(
    r"^\*{0,2}(LUẬT|NGHỊ ĐỊNH|NGHỊ QUYẾT|THÔNG TƯ|PHÁP LỆNH|HIẾN PHÁP)\*{0,2}$"
)
_DOC_TYPE_LABEL_MAP = {
    "LUẬT": "luat",
    "NGHỊ ĐỊNH": "nghi_dinh",
    "NGHỊ QUYẾT": "nghi_quyet",
    "THÔNG TƯ": "thong_tu",
    "PHÁP LỆNH": "phap_lenh",
    "HIẾN PHÁP": "hien_phap",
}
_HIEU_LUC_DIR_MAP = {
    "con_hieuluc": "con_hieu_luc",
    "conhieuluc": "con_hieu_luc",
    "het_hieuluc_toanbo": "het_hieu_luc_toan_bo",
    "hethieuluctoanbo": "het_hieu_luc_toan_bo",
    "het_hieuluc1phan": "het_hieu_luc_mot_phan",
    "het_hieuluc_1_phan": "het_hieu_luc_mot_phan",
    "hethieuluc1phan": "het_hieu_luc_mot_phan",
    "chua_hieuluc": "chua_co_hieu_luc",
    "chuahieuluc": "chua_co_hieu_luc",
}


def _detect_doc_type_and_title(head_lines: list):
    """Tìm heading loại văn bản (LUẬT/NGHỊ ĐỊNH/...) và dòng tiêu đề ngay sau đó."""
    for idx, line in enumerate(head_lines):
        m = _DOC_TYPE_HEADING_RE.match(line.strip())
        if m:
            doc_type = _DOC_TYPE_LABEL_MAP.get(m.group(1), "khong_xac_dinh")
            title = None
            if idx + 1 < len(head_lines):
                nxt = head_lines[idx + 1].strip().strip("*").strip()
                if nxt:
                    title = nxt
            return doc_type, title
    return "nghi_dinh", None
#thay thế 

def _detect_hieu_luc_status(input_path: str) -> str:
    """Suy trạng thái hiệu lực từ tên thư mục cha (đã phân loại sẵn từ khâu làm sạch Tuần 1)."""
    for part in os.path.normpath(input_path).split(os.sep):
        key = part.lower().replace("-", "_")
        if key in _HIEU_LUC_DIR_MAP:
            return _HIEU_LUC_DIR_MAP[key]
    return "con_hieu_luc" 
#thay thế 

def extract_doc_metadata(config: dict, doc_id: str) -> dict:
    """Trích metadata cấp văn bản (mục 2, METADATA_SCHEMA.md): doc_type, doc_title, hieu_luc_status, source_file."""
    with open(config["input_path"], "r", encoding="utf-8") as f:
        head_raw = f.read(4000)
    head_lines = [_clean_line(l) for l in head_raw.split("\n") if _clean_line(l) != ""]
    doc_type, doc_title = _detect_doc_type_and_title(head_lines)
    return {
        "doc_id": doc_id,
        "doc_type": doc_type,
        "doc_title": doc_title or "ĐẦU TƯ",
        "hieu_luc_status": _detect_hieu_luc_status(config["input_path"]),
        "source_file": os.path.basename(config["input_path"]),
    }
#thay thế 

def tag_metadata(chunks: list, config: dict, doc_id: str) -> list:
    """Gắn metadata cấp văn bản + char_count + field is_amendment_text/amendment_source mặc định
    lên từng chunk, để schema đồng nhất trên toàn bộ chunks_processed.json (mục 4, METADATA_SCHEMA.md)."""
    doc_meta = extract_doc_metadata(config, doc_id)
    for chunk in chunks:
        chunk["char_count"] = len(chunk.get("text", ""))
        chunk.setdefault("is_amendment_text", False)
        chunk.setdefault("amendment_source", None)
        # Metadata cấp văn bản đặt lên đầu dict để dễ đọc khi export JSON.
        merged = {**doc_meta, **chunk}
        chunk.clear()
        chunk.update(merged)
    return chunks


def _breadcrumb(unit: dict) -> str:
    parts = []
    if unit.get("chuong"):
        label = f"Chương {unit['chuong']}"
        if unit.get("chuong_title"):
            label += f" – {unit['chuong_title']}"
        parts.append(label)
    if unit.get("muc"):
        parts.append(f"Mục {unit['muc']}")
    if unit.get("dieu"):
        label = f"Điều {unit['dieu']}"
        if unit.get("dieu_title"):
            label += f". {unit['dieu_title']}"
        parts.append(label)
    if unit.get("khoan"):
        parts.append(f"Khoản {unit['khoan']}")
    return " > ".join(parts)


def semantic_chunk(units: list, config: dict) -> list:
    """
    Áp dụng quy tắc semantic chunking:
    - Mặc định: mỗi Khoản (kèm toàn bộ Điểm con nối liền) = 1 chunk.
    - Nếu 1 Khoản vượt quá 'max_khoan_chars' VÀ có Điểm con -> cắt nhỏ theo
      từng Điểm thành các chunk riêng (mỗi chunk = 1 Điểm), để đảm bảo mỗi
      chunk không quá dài mà vẫn trọn vẹn 1 ý pháp lý.
    - Nếu Điều không có Khoản (đoạn văn đơn, ví dụ Điều 1) -> cả Điều là 1 chunk.
    """
    max_chars = config["max_khoan_chars"]
    prepend = config["prepend_breadcrumb"]
    chunks = []
    chunk_id = 0

    for unit in units:
        breadcrumb = _breadcrumb(unit)
        diem_list = unit["diem_list"]
        khoan_text = unit["khoan_text"]

        # Tổng độ dài = khoản + toàn bộ điểm con (ước lượng để quyết định có tách không)
        total_len = len(khoan_text) + sum(len(d["text"]) for d in diem_list)

        if diem_list and total_len > max_chars:
            # Tách theo Điểm: mỗi Điểm là 1 chunk riêng, kèm câu dẫn của Khoản
            # (nếu có) để không mất ngữ cảnh "chủ ngữ" của khoản.
            for d in diem_list:
                chunk_id += 1
                full_bc = breadcrumb + (f" > Điểm {d['diem']}" if breadcrumb else f"Điểm {d['diem']}")
                lead = f"{khoan_text} " if khoan_text else ""
                text_body = f"{lead}{d['diem']}) {d['text']}".strip()
                text = f"{full_bc}: {text_body}" if prepend and full_bc else text_body
                chunks.append({
                    "chunk_id": chunk_id,
                    "level": "diem",
                    "chuong": unit["chuong"],
                    "muc": unit["muc"],
                    "dieu": unit["dieu"],
                    "khoan": unit["khoan"],
                    "diem": d["diem"],
                    "breadcrumb": full_bc,
                    "text": text,
                })
        else:
            # Giữ nguyên cả Khoản (kèm điểm con nối liền trong cùng 1 chunk),
            # hoặc cả đoạn văn của Điều nếu không có khoản.
            chunk_id += 1
            body_parts = [khoan_text] if khoan_text else []
            for d in diem_list:
                body_parts.append(f"{d['diem']}) {d['text']}")
            text_body = " ".join(p for p in body_parts if p).strip()
            text = f"{breadcrumb}: {text_body}" if prepend and breadcrumb else text_body
            level = "khoan" if unit["khoan"] else "dieu"
            chunks.append({
                "chunk_id": chunk_id,
                "level": level,
                "chuong": unit["chuong"],
                "muc": unit["muc"],
                "dieu": unit["dieu"],
                "khoan": unit["khoan"],
                "diem": None,
                "breadcrumb": breadcrumb,
                "text": text,
            })

    return chunks


def run(config: dict) -> list:
    doc_id = get_doc_id(config)
    lines = load_markdown(config)
    units = parse_structure(lines, config)
    chunks = semantic_chunk(units, config)
    chunks = assign_provision_ids(chunks, doc_id)
    chunks = tag_metadata(chunks, config, doc_id)
    # Cơ chế Temporal Filter (tầng 1 - per-document): gắn ngay_hieu_luc,
    # valid_from, provision_key cho từng chunk. Xem temporal_utils.py.
    with open(config["input_path"], "r", encoding="utf-8") as f:
        full_text = f.read()
    chunks = tag_temporal_fields(chunks, doc_id, full_text)
    return chunks


def main():
    os.makedirs(os.path.dirname(CHUNK_CONFIG["output_path"]), exist_ok=True)
    print(f"Đang bóc tách: {CHUNK_CONFIG['input_path']} ...")
    try:
        chunks = run(CHUNK_CONFIG)
        with open(CHUNK_CONFIG["output_path"], "w", encoding="utf-8") as f:
            json.dump(chunks, f, ensure_ascii=False, indent=2)
        print(f"Hoàn tất! Tổng số chunk: {len(chunks)}")
        print(f"File lưu tại: {CHUNK_CONFIG['output_path']}")
    except Exception as e:
        print(f"Lỗi xử lý: {e}")
        raise


if __name__ == "__main__":
    main()
