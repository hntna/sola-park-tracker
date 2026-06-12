"""
parser.py — Bóc tách thông tin căn hộ Sola Park từ text tin rao tự do.

Chiến lược 2 lớp:
  1) Regex bắt các mẫu rõ ràng (toà G1/G2, diện tích, hướng, giá, vay...).
  2) Tin nào regex để trống trường quan trọng -> đẩy qua Gemini Flash (gemini.py).

Hàm chính: parse_listing(text) -> dict
"""

import re
import unicodedata


# ---------- Tiện ích chuẩn hoá ----------

def _strip_accents_lower(s: str) -> str:
    """Bỏ dấu + lowercase để regex hướng/khoá dễ khớp các kiểu viết.
    Lưu ý: chữ 'đ/Đ' không phải dấu thanh nên NFD không tách được -> map tay."""
    s = s.replace("đ", "d").replace("Đ", "D")
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return s.lower()


# ---------- Toà nhà (G1, G2, G3, ... GS1 ...) ----------
# Sola Park (Imperia Smart City, Tây Mỗ) đặt tên toà kiểu G + số.
_TOWER_RE = re.compile(r"\bG\s?S?\s?(\d{1,2})\b", re.IGNORECASE)

def _parse_tower(text: str):
    m = _TOWER_RE.search(text)
    if not m:
        return None
    raw = m.group(0).upper().replace(" ", "")
    return raw  # ví dụ "G3", "GS1"


# ---------- Diện tích (m2) ----------
# Bắt: "43m2", "43 m²", "43m vuong", "dt 43", "diện tích 43,5"
_AREA_RE = re.compile(
    r"(\d{2,3}(?:[.,]\d)?)\s*(?:m2|m²|m\s*vuong|met|mét|m\b)",
    re.IGNORECASE,
)

def _parse_area(text: str):
    norm = _strip_accents_lower(text)
    m = _AREA_RE.search(norm)
    if not m:
        return None
    val = float(m.group(1).replace(",", "."))
    # loại số vô lý (giá tiền lẫn vào, vd "3 ty")
    if 20 <= val <= 300:
        return val
    return None


# ---------- Layout phòng ngủ (1PN, 1PN+, 2PN, 2PN+1 ...) ----------
# "1pn", "1pn+", "2pn+1" — dấu + chỉ nhận khi đi liền (vd "2pn+1" hoặc "1pn+").
# "1pn+ 43m2": phần "+ 43" KHÔNG bị nuốt vì giữa + và 43 có dấu cách.
_LAYOUT_RE = re.compile(
    r"\b(\d)\s*pn(\+\d?)?",
    re.IGNORECASE,
)

def _parse_layout(text: str):
    norm = _strip_accents_lower(text)
    m = _LAYOUT_RE.search(norm)
    if not m:
        # thử dạng "studio"
        if "studio" in norm:
            return "Studio"
        return None
    n = m.group(1)
    plus = (m.group(2) or "")
    return f"{n}PN{plus}".upper() if plus else f"{n}PN"


# ---------- Hướng (ĐN, TN, ĐB, TB, Đ, T, N, B) ----------
# Map các kiểu viết -> mã chuẩn 2 ký tự.
_DIRECTION_MAP = {
    "dong nam": "ĐN", "dn": "ĐN", "đn": "ĐN",
    "tay nam": "TN", "tn": "TN",
    "dong bac": "ĐB", "db": "ĐB", "đb": "ĐB",
    "tay bac": "TB", "tb": "TB",
    "dong": "Đ",
    "tay": "T",
    "nam": "N",
    "bac": "B",
}

# Ưu tiên cụm 2 hướng (đông nam) trước, rồi tới viết tắt 2 ký tự, rồi 1 hướng.
# Chấp nhận cả khi KHÔNG có chữ "huong" phía trước (tin hay viết "can DN", "view dong nam").

# 1) cụm đầy đủ 2 hướng
_DIR_FULL_2_RE = re.compile(
    r"\b(dong nam|tay nam|dong bac|tay bac)\b", re.IGNORECASE
)
# 2) viết tắt 2 ký tự, nhưng phải có ngữ cảnh hướng/căn/view ở gần để tránh nhiễu
_DIR_ABBR_2_RE = re.compile(
    r"(?:huong|can|view|nha|ban\s?công|ban cong)\s*[:\-]?\s*(dn|tn|db|tb)\b",
    re.IGNORECASE,
)
# 3) "huong <1 hướng>"
_DIR_FULL_1_RE = re.compile(
    r"\bhuong\s*[:\-]?\s*(dong|tay|nam|bac)\b", re.IGNORECASE
)

def _parse_direction(text: str):
    norm = _strip_accents_lower(text)
    # 1) cụm 2 hướng đầy đủ — chắc chắn nhất
    m = _DIR_FULL_2_RE.search(norm)
    if m:
        return _DIRECTION_MAP[m.group(1)]
    # 2) viết tắt 2 ký tự kèm ngữ cảnh
    m = _DIR_ABBR_2_RE.search(norm)
    if m:
        return _DIRECTION_MAP[m.group(1).lower()]
    # 3) một hướng đơn, chỉ khi có chữ "huong" để tránh bắt nhầm "nam" trong "Việt Nam" v.v.
    m = _DIR_FULL_1_RE.search(norm)
    if m:
        return _DIRECTION_MAP[m.group(1)]
    return None


# ---------- Loại tầng (thấp / trung / cao) + số tầng ----------
def _parse_floor_band(text: str):
    norm = _strip_accents_lower(text)
    if re.search(r"\btang\s*(thap|low)\b", norm):
        return "thấp"
    if re.search(r"\btang\s*(trung|mid|giua)\b", norm):
        return "trung"
    if re.search(r"\btang\s*(cao|high|dep)\b", norm):
        return "cao"
    return None

_FLOOR_NO_RE = re.compile(r"\btang\s*(\d{1,2})\b", re.IGNORECASE)

def _parse_floor_no(text: str):
    norm = _strip_accents_lower(text)
    m = _FLOOR_NO_RE.search(norm)
    if m:
        n = int(m.group(1))
        if 1 <= n <= 60:
            return n
    return None


# ---------- Giá (quy ra tỷ) ----------
# Bắt: "3 tỷ 250", "3,25 tỷ", "3ty250", "3.2 tỉ", "3 tỷ 2", "giá 3250 triệu"
_PRICE_TY_RE = re.compile(
    r"(\d{1,2})\s*(?:ty|tỷ|tỉ)\s*(\d{1,3})?",
    re.IGNORECASE,
)
_PRICE_TY_DECIMAL_RE = re.compile(
    r"(\d{1,2}[.,]\d{1,3})\s*(?:ty|tỷ|tỉ)",
    re.IGNORECASE,
)
_PRICE_TRIEU_RE = re.compile(
    r"(\d{3,5})\s*(?:tr|trieu|triệu)",
    re.IGNORECASE,
)

def _parse_price_bil(text: str):
    norm = _strip_accents_lower(text)

    # dạng "3,25 ty" / "3.2 ty"
    m = _PRICE_TY_DECIMAL_RE.search(norm)
    if m:
        return round(float(m.group(1).replace(",", ".")), 3)

    # dạng "3 ty 250" / "3 ty 2" / "3 ty"
    m = _PRICE_TY_RE.search(norm)
    if m:
        ty = int(m.group(1))
        tail = m.group(2)
        if tail is None:
            return float(ty)
        # "3 ty 2"  -> 3.2  ; "3 ty 250" -> 3.25 ; "3 ty 25" -> 3.25
        if len(tail) == 1:      # 2 -> 0.2
            frac = int(tail) / 10
        elif len(tail) == 2:    # 25 -> 0.25
            frac = int(tail) / 100
        else:                   # 250 -> 0.250
            frac = int(tail) / 1000
        return round(ty + frac, 3)

    # dạng "3250 trieu"
    m = _PRICE_TRIEU_RE.search(norm)
    if m:
        return round(int(m.group(1)) / 1000, 3)

    return None


# ---------- Hình thức vay / giải ngân ----------
def _parse_payment_terms(text: str):
    norm = _strip_accents_lower(text)
    parts = []
    # vay X%
    for m in re.finditer(r"vay\s*(\d{1,3})\s*%", norm):
        parts.append(f"vay {m.group(1)}%")
    # giải ngân X%
    for m in re.finditer(r"giai ngan\s*(\d{1,3})\s*%", norm):
        parts.append(f"giải ngân {m.group(1)}%")
    # ân hạn gốc / lãi
    if "an han" in norm:
        parts.append("ân hạn gốc/lãi")
    # hỗ trợ lãi suất
    if re.search(r"ho tro (lai|ls)", norm):
        parts.append("hỗ trợ lãi suất")
    return " / ".join(dict.fromkeys(parts)) if parts else None


# ---------- Hàm tổng ----------

# Các trường "quan trọng" — nếu thiếu thì nên nhờ Gemini bù.
_IMPORTANT = ("tower", "area_m2", "price_bil")

def parse_listing(text: str) -> dict:
    """Trả về dict các trường đã bóc được bằng regex.
    Trường nào không bắt được sẽ là None."""
    if not text:
        text = ""
    return {
        "tower": _parse_tower(text),
        "area_m2": _parse_area(text),
        "layout": _parse_layout(text),
        "direction": _parse_direction(text),
        "floor_band": _parse_floor_band(text),
        "floor_no": _parse_floor_no(text),
        "price_bil": _parse_price_bil(text),
        "payment_terms": _parse_payment_terms(text),
    }


def needs_llm(parsed: dict) -> bool:
    """True nếu thiếu trường quan trọng -> nên gọi Gemini bù."""
    return any(parsed.get(k) is None for k in _IMPORTANT)


def merge_parsed(regex_result: dict, llm_result: dict) -> dict:
    """Ưu tiên kết quả regex (chắc chắn hơn), Gemini chỉ điền vào chỗ trống."""
    out = dict(regex_result)
    for k, v in (llm_result or {}).items():
        if out.get(k) is None and v is not None:
            out[k] = v
    return out


# ---------- Test nhanh khi chạy trực tiếp ----------
if __name__ == "__main__":
    samples = [
        "G3 - 1pn+ 43m vuong hướng ĐN tầng đẹp 3ty250 bao sang tên vay 70%🔥",
        "Cần bán căn G1 diện tích 55,2 m2 2PN hướng Tây Nam tầng trung giá 3,9 tỷ giải ngân 5%",
        "GS2 studio 30m2 tầng cao 2 tỷ 1 ân hạn gốc lãi 24 tháng",
        "Bán gấp 1PN 43m2 G3 hướng đông nam giá 3250 triệu hỗ trợ vay 50%",
    ]
    import json
    for s in samples:
        r = parse_listing(s)
        print(json.dumps(r, ensure_ascii=False))
        print("  -> needs_llm:", needs_llm(r))
