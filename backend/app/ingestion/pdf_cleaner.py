"""cleanned_data.py

Chuyển 01 PDF văn bản pháp luật có text-layer thành 01 file Markdown.

Mục tiêu:
- Không OCR nếu PDF đã có text layer -> hạn chế sửa sai nội dung pháp luật.
- Dựng lại dòng theo layout gốc của PDF.
- Giữ nguyên chữ hoa/thường và Unicode trong PDF.
- Giữ bold / italic dựa trên thuộc tính font của từng span PDF.
- Nối các dòng bị wrap do hết chiều rộng trang, nhưng KHÔNG nối nhầm
  Chương / Mục / Điều / Khoản / Điểm.
- Loại số trang đơn độc ở mép trên/dưới.
- Không dùng từ điển OCR tự sửa từ, vì có thể làm thay đổi nội dung luật.

Lưu ý về "giữ font": Markdown chuẩn không lưu được font family nhúng trong PDF.
File này giữ STYLE (bold/italic) và nguyên văn ký tự. Nếu cần đúng font family,
phải xuất HTML/DOCX/PDF thay vì Markdown thuần.

Dependency:
    pip install pymupdf
"""

from __future__ import annotations

import argparse
import os
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from statistics import median
from typing import Iterable, Optional

import fitz  # PyMuPDF


CONFIG = {
    # Có thể sửa trực tiếp hoặc truyền --input / --output khi chạy.
    "input_path": r"data/dataset/luat/het_hieu_luc_mot_phan/VanBanGoc_57.2024.QH15 (PDF).pdf",
    "output_path": r"data/57-2024-QH15.md",

    # Chỉ dùng để nhận diện số trang/header/footer, KHÔNG crop cứng nội dung.
    "page_number_top_zone": 55.0,
    "page_number_bottom_zone": 45.0,

    # Sai số gom / đánh giá dòng (point PDF).
    "large_gap_multiplier": 1.38,
    "column_gap_threshold": 42.0,

    # Giữ header chính thức ở trang đầu.
    "keep_first_page_header": True,

    # Nếu tài liệu có running-header thực sự lặp ở mọi trang, thêm regex tại đây.
    # Không nên đưa Quốc hiệu / tên cơ quan vào đây nếu muốn giữ trang đầu.
    "noise_patterns": [
        # Ví dụ: r"^CỔNG THÔNG TIN ĐIỆN TỬ.*$",
    ],
}


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class PdfLine:
    page_no: int
    plain: str
    styled: str
    x0: float
    x1: float
    y0: float
    y1: float
    page_width: float
    page_height: float
    font_size: float
    bold_ratio: float
    italic_ratio: float
    is_tableish: bool = False

    @property
    def height(self) -> float:
        return max(0.1, self.y1 - self.y0)

    @property
    def centered(self) -> bool:
        if not self.plain:
            return False
        line_center = (self.x0 + self.x1) / 2.0
        page_center = self.page_width / 2.0
        # Chỉ coi là centered nếu dòng không phủ gần hết chiều ngang.
        return (
            abs(line_center - page_center) <= 22
            and self.x0 >= 100
            and self.x1 <= self.page_width - 100
        )


# ---------------------------------------------------------------------------
# Markdown style from PDF span flags
# PyMuPDF flags: bit 1 (2) italic, bit 4 (16) bold.
# ---------------------------------------------------------------------------

def _span_style(flags: int) -> tuple[bool, bool]:
    return bool(flags & 16), bool(flags & 2)


def _wrap_md_style(text: str, *, bold: bool, italic: bool) -> str:
    """Bọc Markdown nhưng giữ whitespace ngoài marker để tránh `*text *`."""
    if not text:
        return ""

    m = re.match(r"^(\s*)(.*?)(\s*)$", text, flags=re.DOTALL)
    if not m:
        return text

    lead, core, tail = m.groups()
    if not core:
        return text

    if bold and italic:
        core = f"***{core}***"
    elif bold:
        core = f"**{core}**"
    elif italic:
        core = f"*{core}*"

    return lead + core + tail


def _normalize_span_text(text: str) -> str:
    # Không thay nội dung/chữ hoa-thường. Chỉ bỏ các control-char gây hỏng Markdown.
    text = unicodedata.normalize("NFC", text)
    text = text.replace("\u00a0", " ")
    text = text.replace("\r", "").replace("\f", "").replace("\v", "")
    return text


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------

def _is_page_number(line: PdfLine, cfg: dict) -> bool:
    if not re.fullmatch(r"\s*\d{1,4}\s*", line.plain):
        return False

    in_top = line.y0 <= cfg["page_number_top_zone"]
    in_bottom = line.y1 >= line.page_height - cfg["page_number_bottom_zone"]
    return in_top or in_bottom


def _is_config_noise(line: PdfLine, cfg: dict) -> bool:
    s = line.plain.strip()
    return any(re.match(p, s, re.IGNORECASE) for p in cfg.get("noise_patterns", []))


def _line_from_spans(page_no: int, page_rect, spans: list[dict], cfg: dict) -> Optional[PdfLine]:
    if not spans:
        return None

    # PyMuPDF đã trả spans đúng thứ tự đọc trong line.
    plain_parts: list[str] = []
    styled_parts: list[str] = []
    char_count = 0
    bold_chars = 0
    italic_chars = 0
    sizes: list[float] = []

    prev_x1: Optional[float] = None
    large_horizontal_gaps = 0

    x0 = min(float(s["bbox"][0]) for s in spans)
    y0 = min(float(s["bbox"][1]) for s in spans)
    x1 = max(float(s["bbox"][2]) for s in spans)
    y1 = max(float(s["bbox"][3]) for s in spans)

    for span in spans:
        raw = _normalize_span_text(span.get("text", ""))
        if not raw:
            continue

        sx0, _, sx1, _ = map(float, span["bbox"])
        if prev_x1 is not None and sx0 - prev_x1 >= cfg["column_gap_threshold"]:
            large_horizontal_gaps += 1
        prev_x1 = sx1

        bold, italic = _span_style(int(span.get("flags", 0)))
        n = len(raw.strip())
        char_count += n
        bold_chars += n if bold else 0
        italic_chars += n if italic else 0
        sizes.append(float(span.get("size", 0.0)))

        plain_parts.append(raw)
        styled_parts.append(_wrap_md_style(raw, bold=bold, italic=italic))

    plain = "".join(plain_parts).strip()
    styled = "".join(styled_parts).strip()
    if not plain:
        return None

    line = PdfLine(
        page_no=page_no,
        plain=plain,
        styled=styled,
        x0=x0,
        x1=x1,
        y0=y0,
        y1=y1,
        page_width=float(page_rect.width),
        page_height=float(page_rect.height),
        font_size=median(sizes) if sizes else 0.0,
        bold_ratio=(bold_chars / char_count) if char_count else 0.0,
        italic_ratio=(italic_chars / char_count) if char_count else 0.0,
        is_tableish=large_horizontal_gaps > 0,
    )

    if _is_page_number(line, cfg):
        return None
    if _is_config_noise(line, cfg):
        return None
    return line


def extract_pdf_lines(pdf_path: str, cfg: dict = CONFIG) -> list[PdfLine]:
    """Đọc line/span trực tiếp từ PDF để giữ bold/italic."""
    doc = fitz.open(pdf_path)
    all_lines: list[PdfLine] = []

    try:
        for page_index, page in enumerate(doc):
            data = page.get_text("dict", sort=True)
            page_lines: list[PdfLine] = []

            for block in data.get("blocks", []):
                if block.get("type", 0) != 0:  # chỉ text block
                    continue
                for raw_line in block.get("lines", []):
                    spans = raw_line.get("spans", [])
                    line = _line_from_spans(page_index + 1, page.rect, spans, cfg)
                    if line:
                        page_lines.append(line)

            page_lines.sort(key=lambda l: (round(l.y0, 1), l.x0))
            all_lines.extend(page_lines)
    finally:
        doc.close()

    return all_lines


# ---------------------------------------------------------------------------
# Structural classification
# ---------------------------------------------------------------------------

RE_CHUONG = re.compile(r"^Chương\s+(?:[IVXLCDM]+|\d+)\b", re.IGNORECASE)
RE_MUC = re.compile(r"^Mục\s+\d+[A-Za-zÀ-ỹ]?\b", re.IGNORECASE)
RE_DIEU = re.compile(r"^Điều\s+\d+[A-Za-zÀ-ỹ]*\.", re.IGNORECASE)
RE_QUOTED_DIEU = re.compile(r"^[“\"']\s*Điều\s+\d+[A-Za-zÀ-ỹ]*\.", re.IGNORECASE)
RE_KHOAN = re.compile(r"^(?:[“\"']\s*)?\d+[a-zA-Z]?\.\s+", re.IGNORECASE)
RE_DIEM = re.compile(r"^(?:[“\"']\s*)?[a-zđ]\)\s+", re.IGNORECASE)
RE_ROMAN_SECTION = re.compile(r"^[IVXLCDM]+\.\s+", re.IGNORECASE)


def _structure_kind(text: str) -> Optional[str]:
    s = text.strip()
    if RE_CHUONG.match(s):
        return "chuong"
    if RE_MUC.match(s):
        return "muc"
    if RE_DIEU.match(s):
        return "dieu"
    if RE_QUOTED_DIEU.match(s):
        return "quoted_dieu"
    if RE_KHOAN.match(s):
        return "khoan"
    if RE_DIEM.match(s):
        return "diem"
    return None


def _looks_like_title(line: PdfLine) -> bool:
    s = line.plain.strip()
    letters = [c for c in s if c.isalpha()]
    if not letters:
        return False
    upper_ratio = sum(c.isupper() for c in letters) / len(letters)
    return (
        upper_ratio >= 0.88
        and len(s) <= 110
        and line.bold_ratio >= 0.6
        and line.font_size >= 12
    )


def _is_new_logical_paragraph(curr: PdfLine, prev: Optional[PdfLine], typical_height: float, cfg: dict) -> bool:
    if prev is None:
        return True

    # Mỗi cấu trúc luật là một paragraph riêng.
    if _structure_kind(curr.plain):
        return True

    # Header đầu trang và các block có độ lệch lề lớn không được nối nhầm.
    if curr.page_no == 1 and (curr.y0 < 135 or prev.y0 < 135):
        return True
    if abs(curr.x0 - prev.x0) > 30:
        return True

    # Các tiêu đề/title căn giữa không được nối với đoạn văn.
    if curr.centered or prev.centered or _looks_like_title(curr) or _looks_like_title(prev):
        return True

    # Dòng dạng bảng / nhiều cột: giữ nguyên line để tránh phá hàng/cột.
    if curr.is_tableish or prev.is_tableish:
        return True

    # Sang trang: chỉ nối nếu rõ ràng là câu đang tiếp tục.
    if curr.page_no != prev.page_no:
        if _structure_kind(curr.plain):
            return True
        if prev.plain.rstrip().endswith((".", ";", ":", "?", "!", ".”", ".”")):
            return True
        return False

    gap = curr.y0 - prev.y1
    if gap > typical_height * cfg["large_gap_multiplier"]:
        return True

    # Dòng có bullet/roman section không thuộc cấu trúc Chương/Điều cũng tách riêng.
    if RE_ROMAN_SECTION.match(curr.plain.strip()):
        return True

    return False


# ---------------------------------------------------------------------------
# Markdown building
# ---------------------------------------------------------------------------

def _merge_fragments(parts: list[str]) -> str:
    """Nối line-wrap bằng đúng 1 space, xử lý gạch nối cuối dòng thận trọng."""
    out = ""
    for frag in parts:
        frag = frag.strip()
        if not frag:
            continue
        if not out:
            out = frag
            continue

        # Chỉ nối từ bị gãy bằng dấu '-' ASCII, không động vào dấu gạch ngang pháp lý.
        if out.endswith("-") and re.search(r"[A-Za-zÀ-ỹ]-$", out) and re.match(r"^[A-Za-zÀ-ỹ]", frag):
            out = out[:-1] + frag
        else:
            out += " " + frag
    out = out.strip()
    # Khi một paragraph được tạo từ nhiều physical line có cùng style,
    # gộp marker để Markdown sạch hơn: `*a* *b*` -> `*a b*`.
    previous = None
    while previous != out:
        previous = out
        out = re.sub(r"\*\*\*([^*]+)\*\*\*\s+\*\*\*([^*]+)\*\*\*", r"***\1 \2***", out)
        out = re.sub(r"\*\*([^*]+)\*\*\s+\*\*([^*]+)\*\*", r"**\1 \2**", out)
        out = re.sub(r"(?<!\*)\*([^*]+)\*\s+\*([^*]+)\*(?!\*)", r"*\1 \2*", out)
    return out


def _apply_heading_marker(kind: Optional[str], styled_text: str) -> str:
    if kind == "chuong":
        return f"# {styled_text}"
    if kind == "muc":
        return f"## {styled_text}"
    if kind == "dieu":
        return f"## {styled_text}"
    return styled_text


def lines_to_markdown(lines: list[PdfLine], cfg: dict = CONFIG) -> str:
    if not lines:
        return ""

    heights = [l.height for l in lines if 5 <= l.height <= 30]
    typical_height = median(heights) if heights else 14.0

    paragraphs: list[tuple[PdfLine, list[str]]] = []
    prev: Optional[PdfLine] = None

    for line in lines:
        if _is_new_logical_paragraph(line, prev, typical_height, cfg):
            paragraphs.append((line, [line.styled]))
        else:
            paragraphs[-1][1].append(line.styled)
        prev = line

    output: list[str] = []
    for first_line, fragments in paragraphs:
        text = _merge_fragments(fragments)
        if not text:
            continue

        kind = _structure_kind(first_line.plain)
        text = _apply_heading_marker(kind, text)
        output.append(text)

    # Một blank line giữa các paragraph để Markdown ổn định và dễ parse về sau.
    result = "\n\n".join(output)
    result = re.sub(r"[ \t]+\n", "\n", result)
    result = re.sub(r"\n{3,}", "\n\n", result)
    return result.strip() + "\n"


def convert_pdf_to_markdown(pdf_path: str, output_path: str, cfg: dict = CONFIG) -> str:
    if not os.path.isfile(pdf_path):
        raise FileNotFoundError(f"Không tìm thấy PDF: {pdf_path}")

    lines = extract_pdf_lines(pdf_path, cfg)
    if not lines:
        raise ValueError(
            "PDF không có text layer hoặc không trích được text. "
            "File này cần pipeline OCR riêng; không nên OCR âm thầm trong cleaner."
        )

    md = lines_to_markdown(lines, cfg)
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(md, encoding="utf-8")
    return md


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Convert one legal PDF to one Markdown file while preserving PDF text styles.")
    p.add_argument("--input", default=CONFIG["input_path"], help="Đường dẫn PDF input")
    p.add_argument("--output", default=CONFIG["output_path"], help="Đường dẫn .md output")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    print(f"Đang xử lý: {args.input}")
    md = convert_pdf_to_markdown(args.input, args.output, CONFIG)
    print(f"Đã tạo: {args.output}")
    print(f"Độ dài Markdown: {len(md):,} ký tự")


if __name__ == "__main__":
    main()
