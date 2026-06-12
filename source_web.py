"""
source_web.py — Lấy tin Sola Park từ các trang BĐS công khai.

Đây là KHUNG mẫu. Mỗi trang có HTML khác nhau nên selector cần chỉnh theo thực tế
(mở trang, F12, xem class của tiêu đề/giá/link). Mình để sẵn 1 ví dụ với
requests + BeautifulSoup và chỗ chú thích rõ cần sửa gì.

Nếu trang render bằng JavaScript (nội dung không có trong HTML thô), cần Playwright
thay cho requests — xem ghi chú cuối file.
"""

import os
import time
import urllib.parse
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup


HEADERS = {
    # Giả lập trình duyệt để tránh bị chặn ngay. Vẫn nên lịch sự: delay giữa request.
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "vi,en;q=0.9",
}

# Từ khoá tìm dự án. Sola Park = phân khu thuộc Imperia Smart City / Vinhomes Smart City.
SEARCH_TERMS = ["sola park", "imperia smart city", "sola imperia"]

REQUEST_DELAY_SEC = 2.0  # lịch sự, tránh dồn dập


def _fetch_html(url: str) -> str | None:
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        r.raise_for_status()
        return r.text
    except requests.RequestException as e:
        print(f"[web] lỗi tải {url}: {e}")
        return None


def crawl_batdongsan() -> list[dict]:
    """VÍ DỤ cho batdongsan.com.vn. Selector dưới đây là MINH HOẠ — bạn phải mở
    trang kết quả tìm kiếm thật, F12, và thay '.js__card', '.re__card-title'... cho khớp."""
    results = []
    base = "https://batdongsan.com.vn/ban-can-ho-chung-cu"
    for term in SEARCH_TERMS:
        q = urllib.parse.quote(term)
        url = f"{base}?keyword={q}"  # cú pháp tìm kiếm có thể khác, chỉnh theo trang
        html = _fetch_html(url)
        time.sleep(REQUEST_DELAY_SEC)
        if not html:
            continue
        soup = BeautifulSoup(html, "html.parser")

        # ----- CHỖ CẦN CHỈNH THEO HTML THẬT -----
        cards = soup.select(".js__card")  # <- thay bằng class card thật
        for c in cards:
            title_el = c.select_one(".re__card-title")     # tiêu đề
            price_el = c.select_one(".re__card-config-price")  # giá
            link_el = c.select_one("a[href]")               # link
            desc_el = c.select_one(".re__card-description")  # mô tả

            title = title_el.get_text(" ", strip=True) if title_el else ""
            price = price_el.get_text(" ", strip=True) if price_el else ""
            desc = desc_el.get_text(" ", strip=True) if desc_el else ""
            href = link_el["href"] if link_el else ""
            if href and href.startswith("/"):
                href = "https://batdongsan.com.vn" + href

            # gộp tiêu đề + giá + mô tả làm text để parser bóc tách
            raw_text = " ".join([title, price, desc]).strip()
            if not raw_text:
                continue
            results.append({
                "raw_text": raw_text,
                "url": href,
                "posted_at": None,  # nếu lấy được ngày đăng thì điền ISO ở đây
                "source": "batdongsan",
            })
        # -----------------------------------------
    print(f"[web] batdongsan: {len(results)} tin (sau khi chỉnh selector).")
    return results


def crawl_all_web() -> list[dict]:
    """Gọi tất cả nguồn web. Thêm hàm crawl_nhatot(), crawl_alonhadat()... tương tự."""
    out = []
    out += crawl_batdongsan()
    # out += crawl_nhatot()   # viết tương tự khi cần
    return out


if __name__ == "__main__":
    for r in crawl_all_web()[:5]:
        print(r)

# ----------------------------------------------------------------------------
# GHI CHÚ: nếu trang dùng JavaScript (HTML thô trống), thay _fetch_html bằng
# Playwright:
#
#   from playwright.sync_api import sync_playwright
#   def _fetch_html_js(url):
#       with sync_playwright() as p:
#           b = p.chromium.launch()
#           page = b.new_page()
#           page.goto(url, wait_until="networkidle")
#           html = page.content()
#           b.close()
#           return html
#
# Cài: pip install playwright && playwright install chromium
# ----------------------------------------------------------------------------
