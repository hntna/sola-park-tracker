"""
main.py — Điều phối toàn bộ pipeline crawl Sola Park.

Luồng:
  1) Lấy tin từ 2 nguồn: Facebook (Apify) + Web BĐS.
  2) Mỗi tin: parse regex -> nếu thiếu trường quan trọng thì gọi Gemini bù.
  3) Khử trùng lặp + ghi Firestore.

Chạy:
  python main.py            # chạy cả 2 nguồn
  python main.py --web      # chỉ web
  python main.py --fb       # chỉ facebook
  python main.py --dry      # không ghi Firestore, chỉ in ra (test parse)

Biến môi trường cần (đặt trong .env local hoặc GitHub Secrets):
  GEMINI_API_KEY, APIFY_TOKEN, APIFY_ACTOR_ID, GROUP_URLS, FIREBASE_SA_JSON
"""

import sys
import json
from datetime import datetime, timezone

import parser as P
import gemini as G
from source_facebook import fetch_facebook_posts
from source_web import crawl_all_web


def enrich(post: dict) -> dict:
    """post = {raw_text, url, posted_at, source}. Trả record đầy đủ để ghi."""
    text = post.get("raw_text", "")
    regex_res = P.parse_listing(text)

    if P.needs_llm(regex_res):
        llm_res = G.parse_with_gemini(text)
        fields = P.merge_parsed(regex_res, llm_res)
        used_llm = bool(llm_res)
    else:
        fields = regex_res
        used_llm = False

    rec = dict(fields)
    rec.update({
        "raw_text": text,
        "url": post.get("url", ""),
        "posted_at": post.get("posted_at"),
        "source": post.get("source", "unknown"),
        "parsed_by": "regex+gemini" if used_llm else "regex",
        "crawled_at": datetime.now(timezone.utc).isoformat(),
    })
    return rec


def run(do_web=True, do_fb=True, dry=False):
    posts = []
    if do_fb:
        posts += fetch_facebook_posts()
    if do_web:
        posts += crawl_all_web()

    print(f"\nTổng cộng {len(posts)} tin thô. Bắt đầu bóc tách...\n")

    records = [enrich(p) for p in posts]

    if dry:
        for r in records:
            print(json.dumps(r, ensure_ascii=False))
        print(f"\n[DRY RUN] {len(records)} record — không ghi Firestore.")
        return

    # chỉ import store khi thực sự ghi (tránh đòi firebase-admin lúc dry-run)
    from store import upsert_listing, make_dup_hash
    stats = {"inserted": 0, "dup_text": 0, "merged": 0}
    for r in records:
        r["dup_hash"] = make_dup_hash(r["raw_text"])
        status = upsert_listing(r)
        stats[status] = stats.get(status, 0) + 1
    print(f"\nKết quả ghi: {stats}")


if __name__ == "__main__":
    args = set(sys.argv[1:])
    dry = "--dry" in args
    only_web = "--web" in args
    only_fb = "--fb" in args
    if only_web:
        run(do_web=True, do_fb=False, dry=dry)
    elif only_fb:
        run(do_web=False, do_fb=True, dry=dry)
    else:
        run(do_web=True, do_fb=True, dry=dry)
