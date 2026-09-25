import os
import re
import json
import unicodedata
from typing import Optional

try:
    from temporal_utils import tag_temporal_fields
except Exception:
    tag_temporal_fields = None


CHUNK_CONFIG = {
    "input_path": r"data/dataset/luat/het_hieu_luc_mot_phan/39-2019-QH14.md",
    "output_path": r"data/39-2019-QH14.json",
    "max_chunk_chars": 1100,
    "prepend_breadcrumb": True,
    "include_preamble_chunk": False,
    "doc_id_override": None,
}

# -----------------------------------------------------------------------------
# Basic normalization
# -----------------------------------------------------------------------------


def _strip_md(s: str) -> str:
    s = s.replace("\r", "").strip()
    # Markdown emphasis only; do not alter legal punctuation/content.
    s = re.sub(r"^#{1,6}\s*", "", s)
    s = s.replace("**", "").replace("__", "")
    s = s.replace("*", "")
    return s.strip()


def _clean_text(s: str) -> str:
    s = unicodedata.normalize("NFC", s or "")
    s = re.sub(r"[ \t]+", " ", s)
    return s.strip()


def _slugify_doc_id(raw: str) -> str:
    s = raw.strip().replace("Đ", "D").replace("đ", "d")
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.replace("/", "-")
    s = re.sub(r"\s+", "", s)
    s = re.sub(r"-{2,}", "-", s).strip("-")
    return s.upper()


_DOC_NO_RE = re.compile(
    r"(?:Luật\s+số|Số)\s*:\s*([0-9]+\s*/\s*[0-9]{4}\s*/\s*[A-ZĐ][A-ZĐ0-9\-]*)",
    re.I,
)


def load_markdown(config: dict):
    with open(config["input_path"], "r", encoding="utf-8") as f:
        raw = unicodedata.normalize("NFC", f.read())
    lines = [_clean_text(x) for x in raw.splitlines()]
    return raw, [x for x in lines if x]


def get_doc_id(config: dict, raw: str) -> str:
    if config.get("doc_id_override"):
        return _slugify_doc_id(config["doc_id_override"])
    plain = _strip_md(raw[:5000])
    m = _DOC_NO_RE.search(plain)
    if m:
        return _slugify_doc_id(m.group(1))
    return _slugify_doc_id(os.path.splitext(os.path.basename(config["input_path"]))[0])


# -----------------------------------------------------------------------------
# Document/base-law metadata
# -----------------------------------------------------------------------------


def _extract_doc_title(lines: list[str]) -> Optional[str]:
    # Join consecutive bold/all-uppercase title lines after LUẬT/NGHỊ QUYẾT/...
    kinds = {"LUẬT", "NGHỊ ĐỊNH", "NGHỊ QUYẾT", "THÔNG TƯ", "PHÁP LỆNH", "HIẾN PHÁP"}
    for i, line in enumerate(lines):
        p = _strip_md(line)
        if p.upper() in kinds:
            parts = []
            j = i + 1
            while j < len(lines):
                t = _strip_md(lines[j])
                if not t or t.lower().startswith("căn cứ") or t.lower().startswith("quốc hội ban hành"):
                    break
                if re.match(r"^Điều\s+\d+", t, re.I):
                    break
                parts.append(t)
                if len(parts) >= 5:
                    break
                j += 1
            return " ".join(parts).strip() or None
    return None


def _detect_doc_type(lines: list[str]) -> str:
    mapping = {
        "LUẬT": "luat", "NGHỊ ĐỊNH": "nghi_dinh", "NGHỊ QUYẾT": "nghi_quyet",
        "THÔNG TƯ": "thong_tu", "PHÁP LỆNH": "phap_lenh", "HIẾN PHÁP": "hien_phap",
    }
    for line in lines[:40]:
        t = _strip_md(line).upper()
        if t in mapping:
            return mapping[t]
    return "khong_xac_dinh"


def _detect_hieu_luc_status(input_path: str) -> str:
    aliases = {
        "con_hieuluc": "con_hieu_luc", "con_hieu_luc": "con_hieu_luc",
        "het_hieu_luc_mot_phan": "het_hieu_luc_mot_phan", "het_hieuluc_mot_phan": "het_hieu_luc_mot_phan",
        "het_hieuluc1phan": "het_hieu_luc_mot_phan", "het_hieuluc_1_phan": "het_hieu_luc_mot_phan",
        "het_hieu_luc_toan_bo": "het_hieu_luc_toan_bo", "het_hieuluc_toanbo": "het_hieu_luc_toan_bo",
        "chua_hieu_luc": "chua_co_hieu_luc", "chua_hieuluc": "chua_co_hieu_luc",
    }
    for part in os.path.normpath(input_path).split(os.sep):
        key = part.lower().replace("-", "_")
        if key in aliases:
            return aliases[key]
    return "khong_xac_dinh"


def _norm_law_name(name: str) -> str:
    s = _strip_md(name).lower()
    s = re.sub(r"\bsố\s+\d+\s*/\s*\d{4}\s*/\s*[a-zđ0-9\-]+.*$", "", s, flags=re.I)
    s = re.sub(r"\s+", " ", s).strip(" ,.;:")
    return s


def extract_base_law_catalog(raw: str) -> list[dict]:
    """Extract base statutes mentioned in the promulgation paragraph.

    Output example:
      {name: 'Luật Quy hoạch', doc_no: '21/2017/QH14', doc_id: '21-2017-QH14'}
    """
    plain = _strip_md(raw)
    plain = re.sub(r"\s+", " ", plain)

    # Stop before Điều 1 to avoid picking every cross-reference later.
    m_stop = re.search(r"\bĐiều\s+1\.", plain)
    head = plain[:m_stop.start()] if m_stop else plain[:12000]

    # Known legal-name structure: Luật <name> số <number>.
    pat = re.compile(
        r"\bLuật\s+(.{2,120}?)\s+số\s+([0-9]+\s*/\s*[0-9]{4}\s*/\s*[A-ZĐ][A-ZĐ0-9\-]*)",
        re.I,
    )
    out = []
    seen = set()
    for m in pat.finditer(head):
        raw_name = re.sub(r"\s+", " ", m.group(1)).strip(" ,.;:")
        # The promulgation sentence itself often says
        # "Luật sửa đổi ... của Luật Quy hoạch số ..."; keep only the
        # base-law name after the last "của Luật". Likewise a regex match may
        # cross a semicolon from a list of previous amendments.
        if re.search(r"\bcủa\s+Luật\s+", raw_name, re.I):
            raw_name = re.split(r"\bcủa\s+(?=Luật\s+)", raw_name, flags=re.I)[-1]
        if "; Luật " in raw_name:
            raw_name = "Luật " + raw_name.rsplit("; Luật ", 1)[-1]
        elif not raw_name.lower().startswith("luật "):
            raw_name = "Luật " + raw_name
        name = raw_name.strip(" ,.;:")
        # Reject artifacts from amendment-number lists such as
        # "Luật số 15/2023/QH15, Luật".
        if len(name) > 130 or re.match(r"^Luật\s+số\b", name, re.I) or name.lower() == "luật":
            continue
        doc_no = re.sub(r"\s+", "", m.group(2))
        key = (name.lower(), doc_no)
        if key in seen:
            continue
        seen.add(key)
        out.append({"name": name, "name_norm": _norm_law_name(name), "doc_no": doc_no, "doc_id": _slugify_doc_id(doc_no)})
    return out


def resolve_target_doc(article_title: Optional[str], catalog: list[dict]) -> Optional[dict]:
    if not article_title:
        return None
    title = _strip_md(article_title)
    m = re.search(r"(?:của|vào)\s+(Luật\s+.+)$", title, re.I)
    wanted = _norm_law_name(m.group(1) if m else title)
    if not wanted:
        return None

    best = None
    best_score = 0
    for item in catalog:
        n = item["name_norm"]
        # exact/substr first
        if wanted == n:
            return item
        if wanted in n or n in wanted:
            score = min(len(wanted), len(n))
        else:
            wt, nt = set(wanted.split()), set(n.split())
            score = len(wt & nt) * 10
        if score > best_score:
            best, best_score = item, score
    return best if best_score >= 20 else None


# -----------------------------------------------------------------------------
# Amendment-target parsing
# -----------------------------------------------------------------------------

_ARTICLE_RE = re.compile(r"^#{0,3}\s*\*{0,2}Điều\s+(\d+[a-z]?)\.?(?:\*{0,2})\s*(.*)$", re.I)
_KHOAN_RE = re.compile(r"^(\d+[a-z]?)\.\s+(.*)$", re.I)
_DIEM_RE = re.compile(r"^([a-zđ]\d?)\)\s+(.*)$", re.I)


def _parse_target_refs(text: str, inherited: Optional[dict] = None) -> dict:
    """Parse the legal provision being amended from an instruction.

    It intentionally returns a *target scope*, not the source position in the
    amending statute. Missing fields inherit from the parent instruction.
    """
    t = _strip_md(text)
    target = dict(inherited or {})

    # Most specific → least specific.
    m = re.search(r"điểm\s+([a-zđ]\d?)\s+khoản\s+(\d+[a-z]?)\s+Điều\s+(\d+[a-z]?)", t, re.I)
    if m:
        target.update({"dieu": m.group(3), "khoan": m.group(2), "diem": m.group(1).lower()})
        return target

    m = re.search(r"(?:các\s+điểm|điểm)\s+([a-zđ]\d?(?:\s*,\s*[a-zđ]\d?)*(?:\s+và\s+[a-zđ]\d?)?)\s+khoản\s+(\d+[a-z]?)\s+Điều\s+(\d+[a-z]?)", t, re.I)
    if m:
        target.update({"dieu": m.group(3), "khoan": m.group(2)})
        target["diem_set"] = re.findall(r"[a-zđ]\d?", m.group(1).lower())
        target.pop("diem", None)
        return target

    m = re.search(r"khoản\s+(\d+[a-z]?)\s+Điều\s+(\d+[a-z]?)", t, re.I)
    if m:
        target.update({"dieu": m.group(2), "khoan": m.group(1)})
        target.pop("diem", None)
        return target

    m = re.search(r"Điều\s+(\d+[a-z]?)", t, re.I)
    if m:
        target.update({"dieu": m.group(1)})
        # A whole-article instruction resets lower levels.
        if re.search(r"(?:sửa đổi|bổ sung)\s+(?:toàn bộ\s+)?Điều\s+", t, re.I):
            target.pop("khoan", None)
            target.pop("diem", None)
        return target

    # Relative instructions, resolved from parent target.
    m = re.search(r"khoản\s+(\d+[a-z]?)", t, re.I)
    if m:
        target["khoan"] = m.group(1)
        target.pop("diem", None)

    m = re.search(r"(?:các\s+điểm|điểm)\s+([a-zđ]\d?(?:\s*,\s*[a-zđ]\d?)*(?:\s+và\s+[a-zđ]\d?)?)", t, re.I)
    if m:
        ds = re.findall(r"[a-zđ]\d?", m.group(1).lower())
        if len(ds) == 1:
            target["diem"] = ds[0]
        elif ds:
            target["diem_set"] = ds
            target.pop("diem", None)

    return target


def _starts_quote(line: str) -> bool:
    t = line.lstrip()
    return bool(re.match(r'^[“"]', t) or re.match(r'^\*{1,2}[“"]', t))


def _strip_open_quote(line: str) -> str:
    s = line.strip()
    # keep markdown around title if present; only remove legal opening quote
    s = re.sub(r'^(\*{1,2})?[“"]', lambda m: m.group(1) or "", s, count=1)
    return s.strip()


def _quote_closes(line: str) -> bool:
    """Nhận diện kết thúc khối trích dẫn sửa đổi.

    Một số file Markdown sau khi làm sạch vẫn còn ký hiệu nhấn mạnh quanh
    dấu câu, ví dụ: ”*.*. Nếu kiểm tra trực tiếp chuỗi thô thì parser sẽ
    không nhận ra dấu đóng quote và trạng thái in_quote bị tràn sang các
    khoản/điểm tiếp theo.

    Chuẩn hóa Markdown trước khi kiểm tra để các dạng:
        ”;
        ”.
        ”*;*
        ”*.*
    đều được nhận diện đúng.
    """
    s = _strip_md(line).rstrip()
    return bool(re.search(r'[”"]\s*[;.]?\s*$', s))


def _strip_close_quote(line: str) -> str:
    """Bỏ dấu đóng quote sau khi đã loại ký hiệu Markdown dư."""
    s = _strip_md(line).rstrip()
    return re.sub(
        r'[”"]\s*([;.])?\s*$',
        lambda m: (m.group(1) or ""),
        s,
    ).strip()


def _target_from_quote_first_line(first: str, fallback: dict) -> dict:
    t = _strip_md(first)
    out = dict(fallback or {})
    m = re.match(r"^Điều\s+(\d+[a-z]?)\.?(?:\s+.*)?$", t, re.I)
    if m:
        out["dieu"] = m.group(1)
        out.pop("khoan", None); out.pop("diem", None)
        return out
    m = re.match(r"^(\d+[a-z]?)\.\s+", t, re.I)
    if m:
        out["khoan"] = m.group(1); out.pop("diem", None)
        return out
    m = re.match(r"^([a-zđ]\d?)\)\s+", t, re.I)
    if m:
        out["diem"] = m.group(1).lower()
        return out
    return out


def _split_quote_into_target_units(quote_lines: list[str], target: dict, ctx: dict) -> list[dict]:
    """Convert one quoted replacement block to target legal units.

    Full-article replacement -> one unit per Khoản (or per Điểm for article
    without numbered paragraphs only when necessary). A single point/khoan
    replacement remains one target unit.
    """
    if not quote_lines:
        return []

    q = [_strip_md(x) for x in quote_lines if _strip_md(x)]
    if not q:
        return []

    target = _target_from_quote_first_line(q[0], target)

    # Drop repeated article heading from body but keep its title in metadata.
    article_title = None
    m_art = re.match(r"^Điều\s+(\d+[a-z]?)\.\s*(.*)$", q[0], re.I)
    if m_art:
        target["dieu"] = m_art.group(1)
        article_title = m_art.group(2).strip() or None
        q = q[1:]

    # A quoted block may replace several sibling points at once, e.g.
    # “b) ...; c) ...; d) ...;”. Split those into separate target units.
    point_starts = []
    for idx, line in enumerate(q):
        mp = _DIEM_RE.match(line)
        if mp:
            point_starts.append((idx, mp.group(1).lower(), mp.group(2).strip()))
    if len(point_starts) >= 2:
        out = []
        for j, (idx, d, first_body) in enumerate(point_starts):
            end = point_starts[j + 1][0] if j + 1 < len(point_starts) else len(q)
            buf = [first_body] + q[idx + 1:end]
            tu = dict(target)
            tu["diem"] = d
            tu.pop("diem_set", None)
            out.append({**ctx, **tu, "dieu_title": article_title, "level": "diem",
                        "body": " ".join(buf).strip()})
        return out

    # Single specific point replacement.
    if target.get("diem"):
        body = " ".join(q)
        body = re.sub(r"^[a-zđ]\d?\)\s*", "", body, count=1, flags=re.I).strip()
        return [{**ctx, **target, "dieu_title": article_title, "level": "diem", "body": body}]

    # Parse numbered paragraphs; each paragraph can retain child points.
    units = []
    cur_k = None
    cur_buf = []
    for line in q:
        mk = _KHOAN_RE.match(line)
        if mk:
            if cur_k is not None:
                units.append(({**ctx, **target, "khoan": cur_k, "diem": None, "dieu_title": article_title,
                               "level": "khoan", "body": " ".join(cur_buf).strip()}))
            cur_k = mk.group(1)
            cur_buf = [mk.group(2).strip()]
        else:
            cur_buf.append(line)
    if cur_k is not None:
        units.append(({**ctx, **target, "khoan": cur_k, "diem": None, "dieu_title": article_title,
                       "level": "khoan", "body": " ".join(cur_buf).strip()}))
        return units

    # If no paragraph markers, preserve explicit target level.
    body = " ".join(q).strip()
    if target.get("khoan"):
        body = re.sub(r"^\d+[a-z]?\.\s*", "", body, count=1, flags=re.I).strip()
        level = "khoan"
    else:
        level = "dieu"
    return [{**ctx, **target, "dieu_title": article_title, "level": level, "body": body}]


def parse_document(raw: str, lines: list[str], config: dict) -> tuple[list[dict], list[dict]]:
    """Return (amendment target units, source instruction units)."""
    catalog = extract_base_law_catalog(raw)

    target_units = []
    instruction_units = []

    source_dieu = None
    source_dieu_title = None
    source_khoan = None
    source_diem = None
    source_target_doc = None

    parent_target = {}
    point_target = {}
    latest_instruction = None

    in_quote = False
    quote_lines = []
    quote_target = {}
    quote_ctx = {}

    def push_instruction(text: str, level: str):
        nonlocal latest_instruction
        instruction_units.append({
            "source_dieu": source_dieu,
            "source_khoan": source_khoan,
            "source_diem": source_diem,
            "level": level,
            "text": _strip_md(text),
            "target_doc_id": source_target_doc.get("doc_id") if source_target_doc else None,
            "target_doc_no": source_target_doc.get("doc_no") if source_target_doc else None,
            "target_doc_title": source_target_doc.get("name") if source_target_doc else None,
        })
        latest_instruction = _strip_md(text)

    i = 0
    while i < len(lines):
        line = lines[i]
        plain = _strip_md(line)

        if in_quote:
            content = line
            if _quote_closes(content):
                content = _strip_close_quote(content)
                if content:
                    quote_lines.append(content)
                target_units.extend(_split_quote_into_target_units(quote_lines, quote_target, quote_ctx))
                in_quote = False
                quote_lines = []
                quote_target = {}
                quote_ctx = {}
            else:
                quote_lines.append(content)
            i += 1
            continue

        # Source article heading of the amending statute.
        ma = _ARTICLE_RE.match(line)
        if ma and (line.lstrip().startswith("#") or "**Điều" in line or re.match(r"^Điều\s+\d+", plain, re.I)):
            source_dieu = ma.group(1)
            source_dieu_title = _strip_md(ma.group(2)).strip()
            source_khoan = None
            source_diem = None
            parent_target = {}
            point_target = {}
            latest_instruction = None
            source_target_doc = resolve_target_doc(source_dieu_title, catalog)
            i += 1
            continue

        # Source khoản instruction.
        mk = _KHOAN_RE.match(plain)
        if mk:
            source_khoan = mk.group(1)
            source_diem = None
            inst = mk.group(2).strip()
            parent_target = _parse_target_refs(inst, {})
            point_target = {}
            push_instruction(plain, "source_khoan")
            # quote may be on next line (usual) or same line after colon
            i += 1
            continue

        # Source điểm instruction. It can refine target of the parent source khoản.
        md = _DIEM_RE.match(plain)
        if md:
            source_diem = md.group(1).lower()
            inst = md.group(2).strip()
            point_target = _parse_target_refs(inst, parent_target)
            push_instruction(plain, "source_diem")
            i += 1
            continue

        if _starts_quote(line):
            in_quote = True
            first = _strip_open_quote(line)
            active_target = point_target or parent_target
            quote_target = _target_from_quote_first_line(first, active_target)
            quote_ctx = {
                "source_dieu": source_dieu,
                "source_khoan": source_khoan,
                "source_diem": source_diem,
                "amendment_instruction": latest_instruction,
                "target_doc_id": source_target_doc.get("doc_id") if source_target_doc else None,
                "target_doc_no": source_target_doc.get("doc_no") if source_target_doc else None,
                "target_doc_title": source_target_doc.get("name") if source_target_doc else None,
                "is_amendment_text": True,
            }
            if _quote_closes(first):
                first = _strip_close_quote(first)
                target_units.extend(_split_quote_into_target_units([first], quote_target, quote_ctx))
                in_quote = False
                quote_target = {}; quote_ctx = {}
            else:
                quote_lines = [first] if first else []
            i += 1
            continue

        i += 1

    # Unclosed quote: preserve rather than silently lose legal text.
    if in_quote and quote_lines:
        target_units.extend(_split_quote_into_target_units(quote_lines, quote_target, quote_ctx))

    return target_units, instruction_units




def parse_source_own_units(lines: list[str], catalog: list[dict]) -> list[dict]:
    """Parse provisions that belong to the amending statute itself.

    Articles whose heading resolves to a base law (e.g. "Sửa đổi ... Luật Quy
    hoạch") are amendment containers and are skipped here. Articles such as
    "Điều khoản thi hành" and "Quy định chuyển tiếp" are retained.
    """
    out = []
    cur_dieu = None
    cur_title = None
    active = False
    cur_k = None
    cur_k_buf = []
    cur_points = []

    def flush_k():
        nonlocal cur_k, cur_k_buf, cur_points
        if not active or cur_dieu is None:
            cur_k = None; cur_k_buf = []; cur_points = []; return
        body = " ".join(cur_k_buf).strip()
        if cur_points:
            body = (body + " " if body else "") + " ".join(f"{d}) {txt}" for d, txt in cur_points)
        if body:
            out.append({"dieu": cur_dieu, "dieu_title": cur_title, "khoan": cur_k, "diem": None,
                        "level": "khoan" if cur_k else "dieu", "body": body, "is_amendment_text": False})
        cur_k = None; cur_k_buf = []; cur_points = []

    i = 0
    while i < len(lines):
        line = lines[i]
        plain = _strip_md(line)
        ma = _ARTICLE_RE.match(line)
        if ma and (line.lstrip().startswith("#") or "**Điều" in line):
            flush_k()
            cur_dieu = ma.group(1)
            cur_title = _strip_md(ma.group(2)).strip() or None
            active = resolve_target_doc(cur_title, catalog) is None
            i += 1
            continue
        if not active:
            i += 1; continue
        mk = _KHOAN_RE.match(plain)
        if mk:
            flush_k()
            cur_k = mk.group(1)
            cur_k_buf = [mk.group(2).strip()]
            i += 1; continue
        md = _DIEM_RE.match(plain)
        if md and cur_k is not None:
            # Preserve subpoints within the parent Khoản; semantic split happens later if needed.
            cur_points.append((md.group(1).lower(), md.group(2).strip()))
            i += 1; continue
        if cur_points:
            d, txt = cur_points[-1]
            cur_points[-1] = (d, (txt + " " + plain).strip())
        else:
            cur_k_buf.append(plain)
        i += 1
    flush_k()
    return out


def semantic_chunk_source(source_units: list[dict], doc_id: str, config: dict, start_id: int = 0) -> list[dict]:
    chunks = []
    prepend = bool(config.get("prepend_breadcrumb", True))
    seen = {}
    for u in source_units:
        parts = [f"Điều {u['dieu']}" + (f". {u['dieu_title']}" if u.get('dieu_title') else "")]
        if u.get("khoan"):
            parts.append(f"Khoản {u['khoan']}")
        bc = " > ".join(parts)
        body = _clean_text(u.get("body", ""))
        text = f"{bc}: {body}" if prepend else body
        segs = [f"d{u['dieu']}"]
        if u.get("khoan"):
            segs.append(f"k{u['khoan']}")
        base = f"{doc_id}#{'.'.join(segs)}"
        n = seen.get(base, 0) + 1; seen[base] = n
        pid = base if n == 1 else f"{base}-{n}"
        chunks.append({
            "chunk_id": start_id + len(chunks) + 1, "level": u.get("level", "khoan"),
            "chuong": None, "muc": None, "dieu": u.get("dieu"), "khoan": u.get("khoan"), "diem": None,
            "breadcrumb": bc, "text": text, "chunk_role": "source_provision",
            "is_amendment_text": False, "amendment_source": None, "amendment_instruction": None,
            "target_doc_id": None, "target_doc_no": None, "target_doc_title": None,
            "provision_id": pid, "provision_key": base, "char_count": len(text),
        })
    return chunks

# -----------------------------------------------------------------------------
# Chunk creation
# -----------------------------------------------------------------------------


def _target_breadcrumb(u: dict) -> str:
    parts = []
    if u.get("target_doc_title"):
        parts.append(u["target_doc_title"])
    if u.get("dieu"):
        p = f"Điều {u['dieu']}"
        if u.get("dieu_title"):
            p += f". {u['dieu_title']}"
        parts.append(p)
    if u.get("khoan"):
        parts.append(f"Khoản {u['khoan']}")
    if u.get("diem"):
        parts.append(f"Điểm {u['diem']}")
    return " > ".join(parts)


def _source_ref(u: dict) -> dict:
    return {
        "dieu": u.get("source_dieu"),
        "khoan": u.get("source_khoan"),
        "diem": u.get("source_diem"),
    }


def _target_key(u: dict) -> Optional[str]:
    root = u.get("target_doc_id")
    if not root:
        return None
    segs = []
    if u.get("dieu"):
        segs.append(f"d{u['dieu']}")
    if u.get("khoan"):
        segs.append(f"k{u['khoan']}")
    if u.get("diem"):
        segs.append(f"p{u['diem']}")
    return root + ("#" + ".".join(segs) if segs else "")


def _build_amendment_pid(doc_id: str, u: dict, seen: dict) -> str:
    src = f"amd{u.get('source_dieu') or '0'}"
    if u.get("source_khoan"):
        src += f"k{u['source_khoan']}"
    if u.get("source_diem"):
        src += f"p{u['source_diem']}"
    tgt = f"qt{u.get('dieu') or '0'}"
    if u.get("khoan"):
        tgt += f".k{u['khoan']}"
    if u.get("diem"):
        tgt += f".p{u['diem']}"
    base = f"{doc_id}#{src}.{tgt}"
    n = seen.get(base, 0) + 1
    seen[base] = n
    return base if n == 1 else f"{base}-{n}"


def semantic_chunk(target_units: list[dict], doc_id: str, config: dict) -> list[dict]:
    chunks = []
    seen = {}
    max_chars = int(config.get("max_chunk_chars", 1100))
    prepend = bool(config.get("prepend_breadcrumb", True))

    for u in target_units:
        body = _clean_text(u.get("body", ""))
        if not body:
            continue
        bc = _target_breadcrumb(u)
        text = f"{bc}: {body}" if prepend and bc else body

        # Avoid arbitrary character slicing through a legal sentence. If a target
        # Khoản is long, split only its child Điểm markers while keeping the same
        # temporal parent key when no finer target was explicitly amended.
        pieces = []
        if len(text) > max_chars and not u.get("diem"):
            # point markers inside body; require marker after start/punctuation
            ms = list(re.finditer(r"(?:(?<=^)|(?<=[;:.]))\s+([a-zđ]\d?)\)\s+", body, re.I))
            if len(ms) >= 2:
                lead = body[:ms[0].start()].strip()
                for j, m in enumerate(ms):
                    end = ms[j + 1].start() if j + 1 < len(ms) else len(body)
                    d = m.group(1).lower()
                    part = body[m.end():end].strip()
                    pieces.append((d, (lead + " " if lead else "") + f"{d}) {part}"))

        if pieces:
            for d, part in pieces:
                cu = dict(u)
                cu["diem"] = d
                full_bc = _target_breadcrumb(cu)
                ctext = f"{full_bc}: {part}" if prepend and full_bc else part
                chunks.append(_make_chunk(doc_id, cu, ctext, full_bc, seen))
        else:
            chunks.append(_make_chunk(doc_id, u, text, bc, seen))

    for i, c in enumerate(chunks, 1):
        c["chunk_id"] = i
    return chunks


def _make_chunk(doc_id: str, u: dict, text: str, breadcrumb: str, seen: dict) -> dict:
    return {
        "chunk_id": None,
        "level": "diem" if u.get("diem") else ("khoan" if u.get("khoan") else "dieu"),
        "chuong": None,
        "muc": None,
        "dieu": u.get("dieu"),
        "khoan": u.get("khoan"),
        "diem": u.get("diem"),
        "breadcrumb": breadcrumb,
        "text": text,
        "chunk_role": "amendment_text",
        "is_amendment_text": True,
        "amendment_source": _source_ref(u),
        "amendment_instruction": u.get("amendment_instruction"),
        "target_doc_id": u.get("target_doc_id"),
        "target_doc_no": u.get("target_doc_no"),
        "target_doc_title": u.get("target_doc_title"),
        "provision_id": _build_amendment_pid(doc_id, u, seen),
        # canonical temporal key: target statute, not the amending statute.
        "provision_key": _target_key(u),
        "char_count": len(text),
    }


def tag_doc_metadata(chunks: list[dict], config: dict, doc_id: str, lines: list[str]) -> list[dict]:
    meta = {
        "doc_id": doc_id,
        "doc_type": _detect_doc_type(lines),
        "doc_title": _extract_doc_title(lines),
        "hieu_luc_status": _detect_hieu_luc_status(config["input_path"]),
        "source_file": os.path.basename(config["input_path"]),
    }
    for c in chunks:
        # Keep target_doc_* separate from doc_id: doc_id is the source/amending law.
        c.update({k: v for k, v in meta.items() if k not in c})
        # Reorder with document metadata first (purely for readable JSON).
        ordered = {**meta, **c}
        c.clear(); c.update(ordered)
    return chunks


def apply_temporal(chunks: list[dict], doc_id: str, raw: str) -> list[dict]:
    """Use existing temporal_utils for dates, then restore canonical target key."""
    original_keys = [c.get("provision_key") for c in chunks]
    if tag_temporal_fields is not None:
        chunks = tag_temporal_fields(chunks, doc_id, raw)
    for c, key in zip(chunks, original_keys):
        if key:
            c["provision_key"] = key
        # valid_from belongs to the amending statute's effective date; that is
        # correct for the new target version.
    return chunks


def validate_chunks(chunks: list[dict]) -> list[str]:
    errors = []
    seen = set()

    # Dấu hiệu thường gặp khi quote bị đóng sai và parser nuốt luôn
    # "3. Sửa đổi..." / "a) Bổ sung..." vào nội dung điều khoản đích.
    leaked_instruction_re = re.compile(
        r"(?:^|\s)(?:\d+[a-z]?\.|[a-zđ]\))\s*"
        r"(?:sửa đổi|bổ sung|bãi bỏ)(?:\s*,\s*(?:bổ sung|bãi bỏ))?"
        r".{0,160}?\b(?:Điều|khoản|điểm)\s+\w+",
        re.I,
    )

    for c in chunks:
        pid = c.get("provision_id")
        if not pid:
            errors.append(f"chunk {c.get('chunk_id')}: thiếu provision_id")
        elif pid in seen:
            errors.append(f"trùng provision_id: {pid}")
        seen.add(pid)

        if c.get("is_amendment_text") and not c.get("target_doc_id"):
            errors.append(f"{pid}: không xác định target_doc_id")
        if c.get("is_amendment_text") and not c.get("dieu"):
            errors.append(f"{pid}: không xác định Điều đích")
        if c.get("is_amendment_text") and not c.get("provision_key"):
            errors.append(f"{pid}: thiếu provision_key canonical")

        if c.get("is_amendment_text"):
            body = str(c.get("text") or "")
            if leaked_instruction_re.search(body):
                errors.append(
                    f"{pid}: nghi ngờ source amendment instruction bị lẫn vào target text"
                )

    return errors


def run(config: dict) -> list[dict]:
    raw, lines = load_markdown(config)
    doc_id = get_doc_id(config, raw)
    catalog = extract_base_law_catalog(raw)
    target_units, instructions = parse_document(raw, lines, config)
    source_units = parse_source_own_units(lines, catalog)
    chunks = semantic_chunk(target_units, doc_id, config)
    source_chunks = semantic_chunk_source(source_units, doc_id, config, start_id=len(chunks))
    chunks.extend(source_chunks)
    chunks = tag_doc_metadata(chunks, config, doc_id, lines)
    chunks = apply_temporal(chunks, doc_id, raw)

    errors = validate_chunks(chunks)
    if errors:
        print("[WARN] Validation:")
        for e in errors[:30]:
            print(" -", e)
        if len(errors) > 30:
            print(f" - ... và {len(errors)-30} lỗi khác")

    print(f"Base-law catalog: {extract_base_law_catalog(raw)}")
    print(f"Amendment instructions parsed: {len(instructions)}")
    print(f"Effective target chunks: {len(chunks)}")
    return chunks


def main():
    os.makedirs(os.path.dirname(CHUNK_CONFIG["output_path"]) or ".", exist_ok=True)
    print(f"Đang bóc tách: {CHUNK_CONFIG['input_path']}")
    chunks = run(CHUNK_CONFIG)
    with open(CHUNK_CONFIG["output_path"], "w", encoding="utf-8") as f:
        json.dump(chunks, f, ensure_ascii=False, indent=2)
    print(f"Hoàn tất: {len(chunks)} chunk -> {CHUNK_CONFIG['output_path']}")


if __name__ == "__main__":
    main()
