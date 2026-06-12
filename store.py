"""
store.py — Ghi listing vào Firestore + khử trùng lặp.

Dùng firebase-admin với service account (đường dẫn trong GOOGLE_APPLICATION_CREDENTIALS
hoặc nội dung JSON trong biến FIREBASE_SA_JSON — tiện cho GitHub Actions Secrets).

Khử trùng lặp 2 lớp:
  - dup_hash: hash của text gốc -> chặn đăng lại y hệt.
  - logic_key: tower|area|direction|floor_band|price_bil -> cùng 1 căn dù khác lời.
    Nếu logic_key đã tồn tại trong N ngày gần đây: cập nhật (giữ tin mới nhất,
    tăng seen_count, ghi nhận thêm 1 nguồn/url) thay vì tạo bản ghi mới.
"""

import os
import json
import hashlib
from datetime import datetime, timezone, timedelta

import firebase_admin
from firebase_admin import credentials, firestore


COLLECTION = "listings"
DEDUP_WINDOW_DAYS = 7  # cùng logic_key trong 7 ngày coi là một căn

_db = None


def _init():
    global _db
    if _db is not None:
        return _db
    if not firebase_admin._apps:
        sa_json = os.environ.get("FIREBASE_SA_JSON")
        if sa_json:
            cred = credentials.Certificate(json.loads(sa_json))
        else:
            # fallback: GOOGLE_APPLICATION_CREDENTIALS trỏ tới file
            cred = credentials.ApplicationDefault()
        firebase_admin.initialize_app(cred)
    _db = firestore.client()
    return _db


def make_dup_hash(text: str) -> str:
    return hashlib.sha256((text or "").strip().encode("utf-8")).hexdigest()[:16]


def make_logic_key(rec: dict) -> str | None:
    """Khoá logic để gộp cùng một căn. Cần tối thiểu tower + area + price."""
    if not (rec.get("tower") and rec.get("area_m2") and rec.get("price_bil")):
        return None
    parts = [
        str(rec.get("tower")),
        f"{float(rec['area_m2']):.1f}",
        str(rec.get("direction") or "?"),
        str(rec.get("floor_band") or "?"),
        f"{float(rec['price_bil']):.2f}",
    ]
    return "|".join(parts)


def upsert_listing(rec: dict) -> str:
    """Ghi hoặc cập nhật 1 listing. Trả về: 'inserted' | 'dup_text' | 'merged'."""
    db = _init()
    col = db.collection(COLLECTION)

    dup_hash = rec.get("dup_hash") or make_dup_hash(rec.get("raw_text", ""))
    rec["dup_hash"] = dup_hash

    # 1) chặn text trùng y hệt
    same_text = list(col.where("dup_hash", "==", dup_hash).limit(1).stream())
    if same_text:
        return "dup_text"

    # 2) gộp theo logic_key trong cửa sổ thời gian
    logic_key = make_logic_key(rec)
    rec["logic_key"] = logic_key
    if logic_key:
        cutoff = datetime.now(timezone.utc) - timedelta(days=DEDUP_WINDOW_DAYS)
        existing = list(
            col.where("logic_key", "==", logic_key)
               .where("last_seen", ">=", cutoff)
               .limit(1)
               .stream()
        )
        if existing:
            doc = existing[0]
            data = doc.to_dict()
            urls = set(data.get("urls", []))
            if rec.get("url"):
                urls.add(rec["url"])
            doc.reference.update({
                "last_seen": firestore.SERVER_TIMESTAMP,
                "seen_count": (data.get("seen_count", 1) + 1),
                "urls": list(urls),
                # giữ tin mới nhất làm bản hiển thị chính
                "raw_text": rec.get("raw_text", data.get("raw_text")),
                "posted_at": rec.get("posted_at", data.get("posted_at")),
                "payment_terms": rec.get("payment_terms") or data.get("payment_terms"),
            })
            return "merged"

    # 3) tạo mới
    rec.setdefault("urls", [rec["url"]] if rec.get("url") else [])
    rec["seen_count"] = 1
    rec["first_seen"] = firestore.SERVER_TIMESTAMP
    rec["last_seen"] = firestore.SERVER_TIMESTAMP
    col.add(rec)
    return "inserted"


if __name__ == "__main__":
    # Test khử trùng lặp logic (không cần Firestore thật)
    a = {"tower": "G3", "area_m2": 43.0, "direction": "ĐN",
         "floor_band": "cao", "price_bil": 3.25, "raw_text": "abc"}
    print("logic_key:", make_logic_key(a))
    print("dup_hash :", make_dup_hash("abc"))
