# 🖼 Pinterest Profile Downloader ⚡

دانلود خودکار تمام پین‌های یک پروفایل پینترست — بدون browser، بدون Playwright، فقط با API مستقیم.

---

## ✨ ویژگی‌ها

- **بدون browser** — مستقیم از Pinterest API داده می‌گیره
- **async download** — تا ۱۶ دانلود همزمان
- **Pagination کامل** — تمام پین‌ها، نه فقط اولین batch
- **چند لایه fallback** — HTML → API → Regex
- **کیفیت بالا** — اولویت با `originals` و `736x`
- **Skip تکراری** — فایل‌های قبلاً دانلود شده رد می‌شن
- **Dark mode UI** — رابط ترمینال با Rich
- **Debug mode** — نمایش جواب‌های خام API

---

## 📦 نصب

```bash
git clone https://github.com/YOUR_USERNAME/pinterest-downloader.git
cd pinterest-downloader
python -m venv env
env\Scripts\activate        # Windows
# source env/bin/activate   # Linux/macOS
pip install -r requirements.txt
```

---

## 🚀 استفاده

```bash
# دانلود پین‌های created (پیش‌فرض)
python main.py https://www.pinterest.com/jovelisher11

# دانلود پین‌های saved
python main.py https://www.pinterest.com/jovelisher11 --section saved

# مسیر خروجی دلخواه
python main.py https://www.pinterest.com/jovelisher11 -o ./my_photos

# افزایش سرعت (دانلود همزمان بیشتر)
python main.py https://www.pinterest.com/jovelisher11 -c 20

# ذخیره لیست URL ها در JSON
python main.py https://www.pinterest.com/jovelisher11 --save-urls

# دیباگ (نمایش جواب API)
python main.py https://www.pinterest.com/jovelisher11 --debug
```

### آرگومان‌ها

| آرگومان | کوتاه | پیش‌فرض | توضیح |
|---------|-------|---------|-------|
| `profile_url` | — | — | URL پروفایل پینترست |
| `--section` | `-s` | `created` | بخش: `created` / `saved` / `boards` |
| `--output` | `-o` | `pinterest_USER_SECTION` | مسیر ذخیره‌سازی |
| `--concurrent` | `-c` | `16` | تعداد دانلودهای همزمان |
| `--save-urls` | — | `False` | ذخیره URL ها در `pins.json` |
| `--debug` | — | `False` | نمایش خروجی خام API |

---

## 📁 ساختار خروجی

```
pinterest_jovelisher11_created/
├── pin_title_123456789.jpg
├── pin_title_987654321.jpg
├── ...
└── pins.json   ← فقط با --save-urls
```

---

## ⚙️ نحوه کار

```
پروفایل URL
    │
    ▼
① init_session()   ← گرفتن cookie + CSRF از صفحه HTML
    │
    ▼
② pins_from_html() ← استخراج batch اول از __PWS_DATA__
    │
    ▼
③ api_page() loop  ← pagination با UserPinsResource API
    │
    ▼
④ Downloader.run() ← دانلود async با aiohttp
```

---

## 🛠 عیب‌یابی

| مشکل | راه‌حل |
|------|--------|
| `No pins found` | با `--debug` اجرا کن و خروجی رو بررسی کن |
| پروفایل خصوصی | این ابزار فقط پروفایل‌های عمومی رو پشتیبانی می‌کنه |
| خطای ۴۰۳ | Pinterest ممکنه IP رو موقتاً block کرده باشه، چند دقیقه صبر کن |
| فایل‌های خالی | `MIN_IMAGE_SIZE` رو در کد کاهش بده (پیش‌فرض: 5000 بایت) |

---

## 📋 Requirements

```
aiohttp>=3.9.0
aiofiles>=23.2.0
requests>=2.31.0
urllib3>=2.0.0
rich>=13.7.0
```

---

## ⚠️ نکات

- این ابزار فقط برای **پروفایل‌های عمومی** کار می‌کنه
- استفاده بیش از حد ممکنه منجر به rate limit از طرف Pinterest بشه
- با `-c` بیشتر از ۲۰ احتیاط کن

---

## 📄 License

MIT
