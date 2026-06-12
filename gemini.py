"""
gemini.py — Gọi Google AI Studio (Gemini Flash) để bóc tách tin rao khó.

Chỉ được gọi khi parser.needs_llm() == True, để tiết kiệm quota free tier.
Key đọc từ biến môi trường GEMINI_API_KEY (đặt trong GitHub Secrets / .env local).
KHÔNG bao giờ hardcode key vào file này.

Model mặc định: gemini-2.5-flash-lite (nhanh, free tier, đủ cho việc parse).
"""

import os
import json
import time
import urllib.request
import urllib.error


_model_str = os.environ.get("GEMINI_MODEL", "").strip()
GEMINI_MODEL = _model_str if _model_str else "gemini-2.5-flash-lite"
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

_ENDPOINT = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "{model}:generateContent"
)

# Prompt yêu cầu Gemini trả về DUY NHẤT một JSON, không markdown, không giải thích.
_SYSTEM_PROMPT = """Bạn là bộ trích xuất thông tin bất động sản. \
Cho một tin rao bán căn hộ dự án Sola Park (Imperia Smart City, Tây Mỗ, Hà Nội), \
hãy trích xuất CHÍNH XÁC các trường dưới đây. Chỉ trả về MỘT object JSON, \
không kèm markdown, không kèm giải thích, không kèm dấu ```.

Các trường (dùng null nếu tin không nêu rõ):
- tower: mã toà, ví dụ "G1","G2","G3","GS1". Giữ nguyên định dạng G + số.
- area_m2: diện tích (số, đơn vị m2). Ví dụ 43 hoặc 55.2
- layout: cấu hình phòng, ví dụ "1PN","1PN+","2PN","2PN+1","Studio"
- direction: hướng căn, chuẩn hoá thành một trong: "Đ","T","N","B","ĐN","TN","ĐB","TB"
- floor_band: loại tầng, một trong: "thấp","trung","cao" (suy luận: tầng đẹp/view = cao). null nếu không rõ.
- floor_no: số tầng cụ thể nếu nêu (số nguyên), không thì null
- price_bil: giá bán quy ra TỶ đồng (số). "3 tỷ 250" -> 3.25 ; "3250 triệu" -> 3.25
- payment_terms: tóm tắt hình thức vay/giải ngân/ân hạn, ví dụ "vay 70% / giải ngân 5%". null nếu không có.

Chỉ trả JSON."""


def _build_payload(text: str) -> dict:
    return {
        "system_instruction": {"parts": [{"text": _SYSTEM_PROMPT}]},
        "contents": [{"parts": [{"text": f"Tin rao:\n{text}"}]}],
        "generationConfig": {
            "temperature": 0,
            "responseMimeType": "application/json",
        },
    }


def _strip_code_fence(s: str) -> str:
    s = s.strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[1] if "\n" in s else s
        s = s.rsplit("```", 1)[0]
    return s.strip()


_disable_gemini = False

def parse_with_gemini(text: str, max_retries: int = 3) -> dict:
    """Gọi Gemini, trả dict các trường. Trả {} nếu lỗi/không có key."""
    global _disable_gemini
    if _disable_gemini or not GEMINI_API_KEY:
        # Không có key hoặc đã hết quota -> bỏ qua
        return {}

    url = _ENDPOINT.format(model=GEMINI_MODEL)
    data = json.dumps(_build_payload(text)).encode("utf-8")

    for attempt in range(max_retries):
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": GEMINI_API_KEY,
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            # Lấy text trả về
            cand = body.get("candidates", [])
            if not cand:
                return {}
            parts = cand[0].get("content", {}).get("parts", [])
            raw = "".join(p.get("text", "") for p in parts)
            raw = _strip_code_fence(raw)
            parsed = json.loads(raw)
            return _normalize(parsed)
        except urllib.error.HTTPError as e:
            err_text = e.read().decode('utf-8')
            # 429 = hết quota tạm thời -> chờ rồi thử lại
            if e.code == 429:
                if "exceeded your current quota" in err_text:
                    print("[gemini] API Key đã cạn kiệt Quota. Tạm thời vô hiệu hoá Gemini để code chạy tiếp.")
                    _disable_gemini = True
                    return {}
                if attempt < max_retries - 1:
                    wait = 2 ** attempt * 5
                    print(f"[gemini] 429, chờ {wait}s rồi thử lại...")
                    time.sleep(wait)
                    continue
            print(f"[gemini] HTTPError {e.code}: {err_text[:200]}")
            return {}
        except Exception as e:
            print(f"[gemini] lỗi: {e}")
            return {}
    return {}


_ALLOWED_DIR = {"Đ", "T", "N", "B", "ĐN", "TN", "ĐB", "TB"}
_ALLOWED_BAND = {"thấp", "trung", "cao"}

def _normalize(d: dict) -> dict:
    """Ép kiểu + lọc giá trị bất thường do model trả."""
    out = {}
    out["tower"] = d.get("tower") or None
    try:
        out["area_m2"] = float(d["area_m2"]) if d.get("area_m2") is not None else None
        if out["area_m2"] is not None and not (20 <= out["area_m2"] <= 300):
            out["area_m2"] = None
    except (ValueError, TypeError):
        out["area_m2"] = None
    out["layout"] = d.get("layout") or None
    dirv = d.get("direction")
    out["direction"] = dirv if dirv in _ALLOWED_DIR else None
    band = d.get("floor_band")
    out["floor_band"] = band if band in _ALLOWED_BAND else None
    try:
        out["floor_no"] = int(d["floor_no"]) if d.get("floor_no") is not None else None
    except (ValueError, TypeError):
        out["floor_no"] = None
    try:
        out["price_bil"] = round(float(d["price_bil"]), 3) if d.get("price_bil") is not None else None
        if out["price_bil"] is not None and not (0.3 <= out["price_bil"] <= 100):
            out["price_bil"] = None
    except (ValueError, TypeError):
        out["price_bil"] = None
    out["payment_terms"] = d.get("payment_terms") or None
    return out


if __name__ == "__main__":
    # Test thủ công: cần đặt GEMINI_API_KEY trong môi trường.
    sample = "Chính chủ nhượng lại căn góc toà 3 bên trái, ban công lớn, full nội thất, deal tốt nhất thị trường, giá thương lượng mạnh cho khách thiện chí, LH ngay"
    print("Có key:", bool(GEMINI_API_KEY))
    print(json.dumps(parse_with_gemini(sample), ensure_ascii=False, indent=2))
