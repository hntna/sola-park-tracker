# Sola Park Tracker

Theo dõi giá căn hộ dự án Sola Park (Imperia Smart City, Tây Mỗ) từ Facebook Group + web BĐS.

**Kiến trúc:** Crawler (GitHub Actions, chạy theo lịch) → bóc tách (regex + Gemini) → Firestore → Frontend tĩnh (GitHub Pages) chỉ đọc và lọc.

```
crawler/         # chạy ngầm bằng GitHub Actions — KHÔNG ở GitHub Pages
  parser.py            # bóc tách regex (toà/dt/hướng/tầng/giá/vay)
  gemini.py            # gọi Gemini Flash cho tin khó regex không xử được
  source_facebook.py   # lấy bài group qua Apify
  source_web.py        # lấy tin từ web BĐS công khai (cần chỉnh selector)
  store.py             # ghi Firestore + khử trùng lặp
  main.py              # điều phối: nguồn -> parse -> ghi
.github/workflows/crawl.yml   # cron 3 lần/ngày
```

---

## A. Dựng Firebase (làm 1 lần)

1. Vào https://console.firebase.google.com → **Add project** → đặt tên (vd `sola-tracker`). Tắt Google Analytics cho gọn.
2. Vào **Build → Firestore Database → Create database** → chọn **Production mode** → vùng `asia-southeast1` (Singapore, gần VN nhất).
3. **Lấy service account** (để crawler ghi dữ liệu):
   - Project settings (bánh răng) → tab **Service accounts** → **Generate new private key** → tải file JSON về.
   - Mở file JSON, **copy toàn bộ nội dung**. Đây là giá trị cho secret `FIREBASE_SA_JSON`. **Không commit file này.**
4. **Lấy config cho frontend** (để web đọc dữ liệu):
   - Project settings → mục **Your apps** → bấm icon `</>` (Web) → đăng ký app → copy đoạn `firebaseConfig {...}`. Cái này nhúng vào frontend được (nó là public config, an toàn — bảo mật do Rules lo, xem dưới).
5. **Đặt Security Rules** (Firestore → tab Rules) để **ai cũng đọc được, chỉ service account ghi được**:

```
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {
    // Chỉ cho phép đọc public trên collection listings
    match /listings/{document=**} {
      allow read: if true;
      allow write: if false;
    }
    // Chặn toàn bộ các quyền truy cập khác để bảo mật
    match /{document=**} {
      allow read, write: if false;
    }
  }
}
```

> Service account (crawler) dùng quyền admin nên không bị rule chặn. Client web chỉ đọc.

---

## B. Dựng Apify cho nguồn Facebook (làm 1 lần)

> ⚠️ Dùng **tài khoản Facebook PHỤ** đã là thành viên các group. Scraping vi phạm ToS của Facebook, tài khoản có rủi ro bị khóa — đừng dùng tài khoản chính.

1. **Tài khoản phụ vào group:** đăng nhập FB phụ, xin vào các group Sola Park / Imperia Smart City. Chờ được duyệt.
2. **Lấy cookie:**
   - Trên trình duyệt đang đăng nhập FB phụ, cài extension **EditThisCookie** (hoặc dùng DevTools → Application → Cookies → facebook.com).
   - Export toàn bộ cookie facebook.com ra JSON.
3. **Tạo tài khoản Apify:** https://console.apify.com (có free tier ~$5 credit/tháng).
   - Lấy **API token**: Settings → Integrations → copy. Đây là secret `APIFY_TOKEN`.
4. **Chọn actor & cấu hình cookie:**
   - Tìm trong Apify Store một actor kiểu *Facebook Groups Scraper* (vd `apify/facebook-groups-scraper` hoặc actor tương đương hỗ trợ cookie auth).
   - Mở actor → tab **Input** → dán cookie đã export vào trường `cookies`, bật **Use Apify Proxy** (tránh chặn IP).
   - Ghi lại **actor id** (dạng `owner~actor-name`) cho biến `APIFY_ACTOR_ID`.
   - **Đọc kỹ tab Input Schema của actor** để biết tên trường đúng (startUrls / resultsLimit / maxPosts...). Nếu khác với `source_facebook.py`, chỉnh hàm `_actor_input()` cho khớp.
5. **Chạy thử actor 1 lần trên Console** với 1 group URL để chắc cookie hợp lệ và ra dữ liệu.

> Để cookie **trong cấu hình actor trên Apify** là cách gọn và an toàn nhất. Chỉ khi muốn truyền cookie qua input mới dùng secret `FB_COOKIES_JSON`.

---

## C. Lấy key Gemini (làm 1 lần)

1. Vào https://aistudio.google.com/apikey → **Create API key** (miễn phí, không cần thẻ).
2. Copy key → đây là secret `GEMINI_API_KEY`.
3. Model mặc định `gemini-2.5-flash-lite` đủ dùng. Free tier giới hạn ~vài chục request/phút, hàng trăm/ngày — crawler chạy 3 lần/ngày nằm gọn trong hạn mức.

> Lưu ý: dữ liệu free tier có thể được Google dùng để cải thiện sản phẩm. Tin rao công khai nên không sao.

---

## D. Chạy thử LOCAL

```bash
cd crawler
cp .env.example .env          # rồi điền giá trị thật vào .env
pip install -r requirements.txt

# nạp .env vào môi trường (Linux/macOS)
export $(grep -v '^#' .env | xargs)

# Test parse, KHÔNG ghi Firestore, KHÔNG cần Apify/Firebase:
python main.py --web --dry    # thử nguồn web (nhớ chỉnh selector trước)

# Chạy thật 1 nguồn:
python main.py --fb           # chỉ facebook (cần Apify + cookie)
python main.py --web          # chỉ web
python main.py                # cả hai
```

---

## E. Đưa lên GitHub Actions (tự động theo lịch)

1. Push toàn bộ repo lên GitHub.
2. Vào **Settings → Secrets and variables → Actions**:
   - Tab **Secrets** (giá trị nhạy cảm): `GEMINI_API_KEY`, `APIFY_TOKEN`, `FIREBASE_SA_JSON`, (tùy chọn) `FB_COOKIES_JSON`.
   - Tab **Variables** (không nhạy cảm): `GEMINI_MODEL`, `APIFY_ACTOR_ID`, `GROUP_URLS`, `FB_MAX_POSTS`.
3. Vào tab **Actions** → chọn workflow *Crawl Sola Park listings* → **Run workflow** để chạy tay lần đầu kiểm tra.
4. Sau đó nó tự chạy theo cron (7h/13h/21h giờ VN). Chỉnh giờ trong `.github/workflows/crawl.yml`.

---

## F. Việc còn lại: Frontend (GitHub Pages)

Phần hiển thị/lọc sẽ dùng Firebase JS SDK đọc collection `listings`, có filter theo
toà / diện tích / hướng / loại tầng, và hiển thị: ngày đăng, thông tin căn, giá,
hình thức vay, URL. Mình sẽ làm bước này sau khi crawler đã chạy ra dữ liệu thật.

## Trường dữ liệu trong Firestore (`listings`)

| field | nghĩa |
|---|---|
| `posted_at` | thời gian đăng (ISO) |
| `tower` | toà G1/G2/G3/GS1... |
| `area_m2` | diện tích |
| `layout` | 1PN / 1PN+ / 2PN / Studio... |
| `direction` | hướng (ĐN/TN/ĐB/TB/Đ/T/N/B) |
| `floor_band` | thấp / trung / cao |
| `floor_no` | số tầng (nếu có) |
| `price_bil` | giá quy ra tỷ |
| `payment_terms` | vay/giải ngân/ân hạn |
| `source` | facebook / batdongsan... |
| `url` / `urls` | link tin (gộp nhiều nếu trùng) |
| `seen_count` | số lần bắt gặp căn này |
| `raw_text` | text gốc để đối chiếu |
| `parsed_by` | regex / regex+gemini |
| `first_seen`, `last_seen` | mốc thời gian |
