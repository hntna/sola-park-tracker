"""
source_facebook.py — Lấy bài từ Facebook Group (kín) qua Apify.

KHÔNG tự scrape Facebook. Gọi một Apify actor đã xử lý sẵn anti-bot/proxy.
Cookie của tài khoản FB PHỤ được lưu trong CẤU HÌNH APIFY (không nằm ở đây).
Token Apify đọc từ biến môi trường APIFY_TOKEN (GitHub Secrets).

Luồng:
  1) POST run-sync-get-dataset-items: chạy actor + lấy luôn kết quả.
  2) Chuẩn hoá mỗi item -> {raw_text, url, posted_at, source}.

Lưu ý: mỗi actor có schema input khác nhau. Đặt:
  - APIFY_ACTOR_ID : id actor bạn chọn (vd "apify~facebook-groups-scraper")
  - GROUP_URLS     : danh sách URL group, phân tách bởi dấu phẩy
Cookie cấu hình trực tiếp trong actor trên Apify Console (trường "cookies"),
hoặc truyền qua input nếu bạn muốn (xem biến FB_COOKIES_JSON, tùy chọn).
"""

import os
import json
import urllib.request
import urllib.error
from datetime import datetime, timezone


APIFY_TOKEN = os.environ.get("APIFY_TOKEN", "")
APIFY_ACTOR_ID = os.environ.get("APIFY_ACTOR_ID", "apify~facebook-groups-scraper")
GROUP_URLS = [u.strip() for u in os.environ.get("GROUP_URLS", "").split(",") if u.strip()]
MAX_POSTS = int(os.environ.get("FB_MAX_POSTS", "50"))
# Tùy chọn: nếu actor nhận cookie qua input thay vì cấu hình sẵn.
FB_COOKIES_JSON = os.environ.get("FB_COOKIES_JSON", "")


def _actor_input() -> dict:
    """Input gửi cho actor. Tên trường có thể phải chỉnh theo actor cụ thể bạn dùng
    (đọc tab Input Schema của actor trên Apify để biết tên đúng)."""
    inp = {
        "startUrls": [{"url": u} for u in GROUP_URLS],
        "resultsLimit": MAX_POSTS,
        # nhiều actor dùng tên khác: "maxPosts", "maxItems"... chỉnh nếu cần
    }
    if FB_COOKIES_JSON:
        try:
            inp["cookies"] = json.loads(FB_COOKIES_JSON)
        except json.JSONDecodeError:
            print("[fb] FB_COOKIES_JSON không phải JSON hợp lệ, bỏ qua.")
    return inp


def fetch_facebook_posts() -> list[dict]:
    """Chạy actor đồng bộ và trả danh sách bài đã chuẩn hoá."""
    if not APIFY_TOKEN:
        print("[fb] thiếu APIFY_TOKEN, bỏ qua nguồn Facebook.")
        return []
    if not GROUP_URLS:
        print("[fb] chưa cấu hình GROUP_URLS, bỏ qua nguồn Facebook.")
        return []

    url = (
        f"https://api.apify.com/v2/acts/{APIFY_ACTOR_ID}"
        f"/run-sync-get-dataset-items?token={APIFY_TOKEN}"
    )
    data = json.dumps(_actor_input()).encode("utf-8")
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        # actor có thể chạy lâu -> timeout rộng
        with urllib.request.urlopen(req, timeout=300) as resp:
            items = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        print(f"[fb] Apify HTTPError {e.code}: {e.read().decode('utf-8')[:300]}")
        return []
    except Exception as e:
        print(f"[fb] lỗi gọi Apify: {e}")
        return []

    out = []
    for it in items:
        norm = _normalize_item(it)
        if norm and norm["raw_text"]:
            out.append(norm)
    print(f"[fb] lấy được {len(out)} bài từ {len(GROUP_URLS)} group.")
    return out


def _normalize_item(it: dict) -> dict | None:
    """Chuẩn hoá item Apify -> schema chung. Tên trường khác nhau giữa các actor,
    nên thử nhiều khả năng."""
    text = (
        it.get("text")
        or it.get("postText")
        or it.get("message")
        or it.get("content")
        or ""
    )
    url = (
        it.get("url")
        or it.get("postUrl")
        or it.get("permalink")
        or it.get("link")
        or ""
    )
    # thời gian đăng: thử epoch hoặc ISO
    posted = None
    ts = it.get("time") or it.get("timestamp") or it.get("publishedAt") or it.get("date")
    if isinstance(ts, (int, float)):
        posted = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
    elif isinstance(ts, str) and ts:
        posted = ts
    return {
        "raw_text": text.strip(),
        "url": url,
        "posted_at": posted,
        "source": "facebook",
    }


if __name__ == "__main__":
    print("APIFY_TOKEN set:", bool(APIFY_TOKEN))
    print("GROUP_URLS:", GROUP_URLS)
    for p in fetch_facebook_posts()[:3]:
        print(p)
