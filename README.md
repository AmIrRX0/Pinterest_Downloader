# 🖼 Pinterest Profile Downloader ⚡

Automatically download all pins from a Pinterest profile — no browser, no Playwright, just direct API access.

---

## ✨ Features

- **Browser-less** — Direct data extraction from Pinterest API
- **Async download** — Up to 16 concurrent downloads
- **Full pagination** — All pins, not just the first batch
- **Multi-layer fallback** — HTML → API → Regex
- **High quality** — Prioritizes `originals` and `736x`
- **Skip duplicates** — Previously downloaded files are skipped
- **Dark mode UI** — Terminal interface with Rich
- **Debug mode** — Raw API responses display

---

## 📦 Installation

```bash
git clone https://github.com/YOUR_USERNAME/pinterest-downloader.git
cd pinterest-downloader
python -m venv env
env\Scripts\activate        # Windows
# source env/bin/activate   # Linux/macOS
pip install -r requirements.txt
```

---

## 🚀 Usage

```bash
# Download created pins (default)
python v1.py https://www.pinterest.com/jovelisher11

# Download saved pins
python v1.py https://www.pinterest.com/jovelisher11 --section saved

# Custom output path
python v1.py https://www.pinterest.com/jovelisher11 -o ./my_photos

# Increase speed (more concurrent downloads)
python v1.py https://www.pinterest.com/jovelisher11 -c 20

# Save URLs list in JSON
python v1.py https://www.pinterest.com/jovelisher11 --save-urls

# Debug (show API responses)
python v1.py https://www.pinterest.com/jovelisher11 --debug
```

### Arguments

| Argument | Short | Default | Description |
|----------|-------|---------|-------------|
| `profile_url` | — | — | Pinterest profile URL |
| `--section` | `-s` | `created` | Section: `created` / `saved` / `boards` |
| `--output` | `-o` | `pinterest_USER_SECTION` | Save directory path |
| `--concurrent` | `-c` | `16` | Number of concurrent downloads |
| `--save-urls` | — | `False` | Save URLs in `pins.json` |
| `--debug` | — | `False` | Show raw API output |

---

## 📁 Output Structure

```
pinterest_jovelisher11_created/
├── pin_title_123456789.jpg
├── pin_title_987654321.jpg
├── ...
└── pins.json   ← Only with --save-urls
```

---

## ⚙️ How It Works

```
Profile URL
    │
    ▼
① init_session()   ← Get cookie + CSRF from HTML page
    │
    ▼
② pins_from_html() ← Extract first batch from __PWS_DATA__
    │
    ▼
③ api_page() loop  ← Pagination with UserPinsResource API
    │
    ▼
④ Downloader.run() ← Async download with aiohttp
```

---

## 🛠 Troubleshooting

| Problem | Solution |
|---------|----------|
| `No pins found` | Run with `--debug` and check the output |
| Private profile | This tool only supports public profiles |
| 403 error | Pinterest may have temporarily blocked your IP, wait a few minutes |
| Empty files | Reduce `MIN_IMAGE_SIZE` in code (default: 5000 bytes) |

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

## ⚠️ Notes

- This tool only works for **public profiles**
- Excessive use may lead to rate limiting by Pinterest
- Be careful with `-c` values above 20

---

## 📄 License

MIT
