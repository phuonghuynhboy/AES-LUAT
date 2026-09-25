"""
temporal_utils.py
==================
Cơ chế TEMPORAL FILTER — tầng 1 (per-document).

Mục đích: gắn thêm vào mỗi chunk các field thời gian hiệu lực, để tầng 2
(temporal_matrix_builder.py, chạy ở mức corpus) có đủ dữ liệu dựng "ma trận
trạng thái hiệu lực" và trả lời câu hỏi "điều khoản X áp dụng bản nào tại
thời điểm T".

Dùng chung cho cả parser.py (Luật/Hiến pháp) và parser_nghidinh.py (Nghị định/
Nghị quyết có khối trích dẫn sửa đổi), để đảm bảo 2 pipeline không lệch nhau
về ý nghĩa của valid_from / valid_to / provision_key.

KHÔNG tự ý đoán khi regex không khớp: nếu không trích được ngày, field tương
ứng = None và chunk được gắn "temporal_incomplete": True để tầng review thủ
công (hoặc tầng corpus) biết mà xử lý tiếp, thay vì âm thầm sai.
"""
import re
import unicodedata
from datetime import date
# 1. Regex trích ngày tháng năm hiệu lực / thông qua / ký, theo văn phong văn bản pháp luật Việt Nam. Đã test khớp với mẫu 203/2025/QH15.


_THONG_QUA_RE = re.compile(
    r"thông qua\s+ngày\s+(\d{1,2})\s+tháng\s+(\d{1,2})\s+năm\s+(\d{4})",
    re.IGNORECASE,
)
_HIEU_LUC_TU_NGAY_THONG_QUA_RE = re.compile(
    r"có hiệu lực thi hành từ ngày được thông qua", re.IGNORECASE
)
_HIEU_LUC_KE_TU_NGAY_KY_RE = re.compile(
    r"có hiệu lực (?:thi hành\s+)?kể từ ngày ký", re.IGNORECASE
)
_HIEU_LUC_TU_NGAY_RE = re.compile(
    r"có hiệu lực (?:thi hành\s+)?(?:kể\s+)?từ\s+ngày\s+(\d{1,2})\s+tháng\s+(\d{1,2})\s+năm\s+(\d{4})",
    re.IGNORECASE,
)

# "Sửa đổi, bổ sung một số điều của Hiến pháp / Luật số X / Nghị định số Y ..." -> nhận diện văn bản GỐC bị sửa đổi, để nối provision_key xuyên văn bản.
_BASE_DOC_REF_RE = re.compile(
    r"[Ss]ửa đổi,?\s*bổ sung một số điều của\s+"
    r"(Hiến pháp|Luật|Nghị định|Nghị quyết|Thông tư|Pháp lệnh)"
    r"(?:\s+(?:nước[^\n\.]*?|năm\s*\d{4})?\s*số\s*[:\s]*([0-9]+\s*/\s*[0-9]{4}\s*/\s*[A-ZĐ][A-ZĐ0-9\-]*))?",
    re.IGNORECASE,
)
_VN_UPPERCASE_DIACRITIC_MAP = {"Đ": "D", "đ": "d"}

def _slugify(raw: str) -> str:
    """Bản slugify độc lập (không import chéo từ parser.py/parser_nghidinh.py
    để tránh circular import khi 2 file đó cùng import module này)."""
    s = raw.strip()
    for src, dst in _VN_UPPERCASE_DIACRITIC_MAP.items():
        s = s.replace(src, dst)
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.replace("/", "-")
    s = re.sub(r"\s+", "", s)
    s = re.sub(r"-{2,}", "-", s).strip("-")
    return s.upper()

def _to_iso(d, m, y):
    try:
        return date(int(y), int(m), int(d)).isoformat()
    except ValueError:
        return None

def extract_temporal_metadata(full_text: str) -> dict:
    """
    Trích mốc thời gian hiệu lực CẤP VĂN BẢN từ toàn văn.

    Trả về:
      ngay_thong_qua      : ISO date | None
      ngay_hieu_luc       : ISO date | None
      hieu_luc_ke_tu_ky   : bool  (True nếu ghi "hiệu lực... kể từ ngày ký"
                                    và không trích được ngày ký cụ thể)
      base_doc_type       : "Hiến pháp" | "Luật" | "Nghị định" | ... | None
      base_doc_so         : "24/2024/NĐ-CP" | None  (None nếu là văn bản KHÔNG
                             phải bản sửa đổi, hoặc là sửa Hiến pháp - vốn
                             không đánh số riêng)
    """
    result = {
        "ngay_thong_qua": None,
        "ngay_hieu_luc": None,
        "hieu_luc_ke_tu_ky": False,
        "base_doc_type": None,
        "base_doc_so": None,
    }

    m_tq = _THONG_QUA_RE.search(full_text)
    if m_tq:
        result["ngay_thong_qua"] = _to_iso(*m_tq.groups())
    if _HIEU_LUC_TU_NGAY_THONG_QUA_RE.search(full_text):
        result["ngay_hieu_luc"] = result["ngay_thong_qua"]
    else:
        m_hl = _HIEU_LUC_TU_NGAY_RE.search(full_text)
        if m_hl:
            result["ngay_hieu_luc"] = _to_iso(*m_hl.groups())
        elif _HIEU_LUC_KE_TU_NGAY_KY_RE.search(full_text):
            result["hieu_luc_ke_tu_ky"] = True
    m_base = _BASE_DOC_REF_RE.search(full_text)
    if m_base:
        result["base_doc_type"] = m_base.group(1)
        result["base_doc_so"] = m_base.group(2).strip() if m_base.group(2) else None
    return result


def build_provision_key(doc_id: str, temporal_meta: dict, chunk: dict) -> str:
    """
    Khóa định danh 1 điều/khoản XUYÊN VĂN BẢN — trục để dựng ma trận hiệu lực
    ở tầng corpus. Ưu tiên:
      1. base_doc_so đã trích được (vd sửa Nghị định số X)  -> slugify(X)
      2. base_doc_type == "Hiến pháp" mà không có số riêng   -> hằng "HIENPHAP"
         (Việt Nam chỉ có 1 bản Hiến pháp hiện hành tại mỗi thời điểm)
      3. Không phải văn bản sửa đổi (văn bản gốc)            -> doc_id của
         chính nó
    """
    base_so = temporal_meta.get("base_doc_so")
    base_type = temporal_meta.get("base_doc_type")

    if base_so:
        root_doc_id = _slugify(base_so)
    elif base_type and base_type.strip().lower() == "hiến pháp":
        root_doc_id = "HIENPHAP"
    else:
        root_doc_id = doc_id
    dieu = chunk.get("dieu")
    khoan = chunk.get("khoan")
    key = f"{root_doc_id}#d{dieu}" if dieu else root_doc_id
    if khoan:
        key += f".k{khoan}"
    return key

def tag_temporal_fields(chunks: list, doc_id: str, full_text: str) -> list:
    """
    API DUY NHẤT mà parser.py và parser_nghidinh.py cần gọi (giữ 2 pipeline
    đồng nhất). Gắn lên mỗi chunk:
      - ngay_thong_qua, ngay_hieu_luc, hieu_luc_ke_tu_ky  (cấp văn bản, lặp lại
        trên từng chunk để mỗi chunk tự chứa đủ ngữ cảnh khi đưa vào RAG)
      - provision_key : khóa xuyên văn bản
      - valid_from    : = ngay_hieu_luc (None nếu chưa trích được)
      - valid_to      : luôn None ở tầng này — chỉ tầng corpus (so sánh nhiều
        văn bản) mới biết điều khoản nào bị thay thế và thay thế từ ngày nào.
      - temporal_incomplete : True nếu thiếu ngay_hieu_luc lẫn hieu_luc_ke_tu_ky
        -> cần rà soát thủ công trước khi đưa vào ma trận hiệu lực.
    """
    meta = extract_temporal_metadata(full_text)
    incomplete = meta["ngay_hieu_luc"] is None and not meta["hieu_luc_ke_tu_ky"]
    for chunk in chunks:
        chunk["ngay_thong_qua"] = meta["ngay_thong_qua"] or NULL
        chunk["ngay_hieu_luc"] = meta["ngay_hieu_luc"] or NULL
        chunk["hieu_luc_ke_tu_ky"] = meta["hieu_luc_ke_tu_ky"]
        chunk["valid_from"] = meta["ngay_hieu_luc"] or NULL 
        chunk["valid_to"] = None
        chunk["provision_key"] = build_provision_key(doc_id, meta, chunk)
        chunk["temporal_incomplete"] = incomplete
    return chunks   
