#!/usr/bin/env python3
"""
Pinterest Profile Downloader  ⚡ v4 (stealth fixed)
=====================================================
نصب:
    pip install playwright aiohttp aiofiles rich playwright-stealth
    playwright install chromium

استفاده:
    python main.py https://www.pinterest.com/miwits
    python main.py https://www.pinterest.com/miwits --section saved
    python main.py https://www.pinterest.com/miwits -o ./photos -c 16
    python main.py https://www.pinterest.com/miwits --show-browser
    python main.py https://www.pinterest.com/miwits --save-urls
"""

import asyncio
import aiohttp
import aiofiles
import argparse
import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

try:
    from playwright.async_api import async_playwright, TimeoutError as PWTimeout
except ImportError:
    print("pip install playwright && playwright install chromium")
    sys.exit(1)

# ── playwright-stealth: پشتیبانی از هر دو نسخه v1 و v2 ──────────
HAS_STEALTH    = False
STEALTH_V2     = False
stealth_async  = None
StealthClass   = None

try:
    from playwright_stealth import Stealth as StealthClass  # v2
    HAS_STEALTH = True
    STEALTH_V2  = True
except ImportError:
    pass

if not HAS_STEALTH:
    try:
        from playwright_stealth import stealth_async          # v1
        HAS_STEALTH = True
        STEALTH_V2  = False
    except ImportError:
        pass

try:
    from rich.console import Console
    from rich.progress import (
        Progress, SpinnerColumn, BarColumn,
        TextColumn, FileSizeColumn, TransferSpeedColumn, TimeRemainingColumn
    )
    from rich.panel import Panel
    from rich.text import Text
    from rich.table import Table
    from rich import box
    from rich.theme import Theme
    RICH = True
except ImportError:
    RICH = False

# ══════════════════════════════════════════════════════
#  تنظیمات
# ══════════════════════════════════════════════════════

DARK_THEME = Theme({
    "info": "bold cyan", "success": "bold green",
    "warning": "bold yellow", "error": "bold red", "dim": "grey50",
}) if RICH else None

SECTIONS = {
    "created": "_created/",
    "saved":   "",
    "boards":  "boards/",
}

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)

IMG_HEADERS = {
    "User-Agent":     UA,
    "Referer":        "https://www.pinterest.com/",
    "Accept":         "image/webp,image/apng,image/*,*/*;q=0.8",
    "Sec-Fetch-Dest": "image",
    "Sec-Fetch-Mode": "no-cors",
    "Sec-Fetch-Site": "cross-site",
}

SCROLL_PAUSE  = 2.0
MAX_SCROLLS   = 150
NO_CHANGE_MAX = 5
CONCURRENT_DL = 16
MIN_IMAGE_SIZE = 5000

# JS برای مخفی کردن bot fingerprints — حتی بدون playwright-stealth
STEALTH_JS = """
() => {
    // webdriver
    Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
    // plugins
    Object.defineProperty(navigator, 'plugins', {
        get: () => {
            const arr = [1,2,3,4,5];
            arr.__proto__ = PluginArray.prototype;
            return arr;
        }
    });
    // languages
    Object.defineProperty(navigator, 'languages', {get: () => ['en-US','en']});
    // chrome runtime
    if (!window.chrome) window.chrome = {};
    if (!window.chrome.runtime) window.chrome.runtime = {};
    // permissions
    const origQuery = window.navigator.permissions && window.navigator.permissions.query;
    if (origQuery) {
        window.navigator.permissions.query = (params) =>
            params.name === 'notifications'
                ? Promise.resolve({state: Notification.permission})
                : origQuery(params);
    }
    // iframe contentWindow
    const iframeProto = HTMLIFrameElement.prototype;
    const origGetter = Object.getOwnPropertyDescriptor(iframeProto, 'contentWindow');
    if (origGetter) {
        Object.defineProperty(iframeProto, 'contentWindow', {
            get: function() {
                const win = origGetter.get.call(this);
                if (win && win.navigator) {
                    Object.defineProperty(win.navigator, 'webdriver', {get: () => undefined});
                }
                return win;
            }
        });
    }
}
"""


# ══════════════════════════════════════════════════════
#  ابزار
# ══════════════════════════════════════════════════════

def get_username(url: str) -> str:
    return urlparse(url.rstrip("/")).path.strip("/").split("/")[0]

def section_url(profile: str, section: str) -> str:
    return profile.rstrip("/") + "/" + SECTIONS.get(section, "_created/")

def sanitize(name: str) -> str:
    return re.sub(r'[\\/*?:"<>|]', "_", (name or "pin").strip())[:80] or "pin"

def best_urls(url: str) -> list:
    clean = url.split('?')[0]
    orig  = re.sub(r'/\d+x\d*/', '/originals/', clean)
    s736  = re.sub(r'/\d+x\d*/', '/736x/',      clean)
    s474  = re.sub(r'/\d+x\d*/', '/474x/',      clean)
    seen, out = set(), []
    for u in [orig, s736, s474, clean]:
        if u and u not in seen:
            seen.add(u); out.append(u)
    return out

def get_ext(url: str) -> str:
    ext = os.path.splitext(urlparse(url.split('?')[0]).path)[1].lower()
    return ext if ext in ('.jpg','.jpeg','.png','.gif','.webp') else '.jpg'

def harvest_json(data, pins: dict):
    if isinstance(data, list):
        for item in data: harvest_json(item, pins)
        return
    if not isinstance(data, dict): return
    pid  = str(data.get("id", ""))
    imgs = data.get("images", {})
    if pid and pid.isdigit() and imgs and isinstance(imgs, dict):
        url = (
            (imgs.get("originals") or {}).get("url") or
            (imgs.get("736x")      or {}).get("url") or
            (imgs.get("474x")      or {}).get("url") or
            (imgs.get("236x")      or {}).get("url") or ""
        )
        if url and "pinimg.com" in url and pid not in pins:
            pins[pid] = {
                "pin_id": pid,
                "url":    url,
                "title":  sanitize(data.get("title") or data.get("description") or f"pin_{pid}"),
            }
            return
    for v in data.values():
        if isinstance(v, (dict, list)):
            harvest_json(v, pins)


# ══════════════════════════════════════════════════════
#  اسکرپر
# ══════════════════════════════════════════════════════

class PinterestScraper:
    def __init__(self, dark: bool = True, headless: bool = True):
        self.dark     = dark
        self.headless = headless
        self.con      = Console(theme=DARK_THEME) if RICH else None

    def log(self, msg, style="info"):
        if self.con: self.con.print(f"  {msg}", style=style)
        else: print(f"  {msg}")

    async def scrape(self, profile_url: str, section: str) -> list[dict]:
        target = section_url(profile_url, section)
        self.log(f"🌐 [bold]{target}[/bold]")

        if HAS_STEALTH:
            ver = "v2 (Stealth class)" if STEALTH_V2 else "v1 (stealth_async)"
            self.log(f"🛡  playwright-stealth فعال — {ver}", "success")
        else:
            self.log("⚠  playwright-stealth نصب نیست! → pip install playwright-stealth", "warning")

        pins: dict[str, dict] = {}

        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=self.headless,
                args=[
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-blink-features=AutomationControlled",
                    "--disable-web-security",
                    "--lang=en-US",
                ]
            )

            ctx = await browser.new_context(
                user_agent=UA,
                viewport={"width": 1920, "height": 1080},
                locale="en-US",
                timezone_id="America/New_York",
                extra_http_headers={
                    "Accept-Language": "en-US,en;q=0.9",
                    "sec-ch-ua":          '"Chromium";v="122", "Not(A:Brand";v="24", "Google Chrome";v="122"',
                    "sec-ch-ua-mobile":   "?0",
                    "sec-ch-ua-platform": '"Windows"',
                },
            )

            # stealth JS — همیشه اجرا می‌شه (حتی بدون کتابخانه)
            await ctx.add_init_script(STEALTH_JS)

            page = await ctx.new_page()

            # playwright-stealth v2
            if HAS_STEALTH and STEALTH_V2 and StealthClass:
                try:
                    stealth = StealthClass()
                    await stealth.use_async(page)
                except Exception as e:
                    self.log(f"stealth v2 error: {e}", "warning")

            # playwright-stealth v1
            elif HAS_STEALTH and not STEALTH_V2 and stealth_async:
                try:
                    await stealth_async(page)
                except Exception as e:
                    self.log(f"stealth v1 error: {e}", "warning")

            # ── رهگیری همه JSON responses ────────────────────────
            async def on_response(resp):
                try:
                    if "pinimg.com" in resp.url:
                        return
                    ct = resp.headers.get("content-type", "")
                    if "json" not in ct:
                        return
                    text = await resp.text()
                    if '"images"' not in text:
                        return
                    data = json.loads(text)
                    before = len(pins)
                    harvest_json(data, pins)
                    gained = len(pins) - before
                    if gained > 0:
                        self.log(f"   [API] +{gained}  →  جمع: [bold green]{len(pins)}[/]", "dim")
                except Exception:
                    pass

            page.on("response", on_response)

            # بلاک فقط چیزهای واقعاً سنگین — عکس‌ها بلاک نمی‌شن!
            BLOCK_TYPES = {"font", "media", "websocket"}
            BLOCK_KWORDS = {"doubleclick.net", "google-analytics.com", "googletagmanager.com"}

            async def router(route):
                rt  = route.request.resource_type
                url = route.request.url
                if rt in BLOCK_TYPES or any(b in url for b in BLOCK_KWORDS):
                    await route.abort()
                else:
                    await route.continue_()

            await page.route("**/*", router)

            # ── بارگذاری صفحه ────────────────────────────────────
            try:
                self.log("⏳ بارگذاری صفحه...", "dim")
                await page.goto(target, wait_until="networkidle", timeout=35000)
                await asyncio.sleep(3)
            except PWTimeout:
                self.log("⏱ Timeout — ادامه...", "warning")
            except Exception as e:
                self.log(f"⚠ {e}", "warning")

            title_txt = await page.title()
            self.log(f"📄 {title_txt}", "dim")

            # Dark mode
            if self.dark:
                try:
                    await page.evaluate("""
                        document.documentElement.style.filter = 'invert(1) hue-rotate(180deg)';
                        document.querySelectorAll('img,video').forEach(
                            el => el.style.filter = 'invert(1) hue-rotate(180deg)'
                        );
                    """)
                except Exception:
                    pass

            # DOM scan قبل از اسکرول
            await self._dom_scan(page, pins)

            # ── اسکرول ───────────────────────────────────────────
            self.log("📜 اسکرول برای بارگذاری پین‌ها...")
            prev, no_change = 0, 0

            for i in range(MAX_SCROLLS):
                await page.evaluate(
                    "window.scrollTo({top: document.body.scrollHeight, behavior: 'smooth'})"
                )
                await asyncio.sleep(SCROLL_PAUSE)
                await self._dom_scan(page, pins)

                count = len(pins)
                self.log(f"   Scroll {i+1:03d} | Pins: [bold green]{count}[/]", "dim")

                if count == prev:
                    no_change += 1
                    if no_change >= NO_CHANGE_MAX:
                        self.log("✅ به انتهای صفحه رسیدیم", "success")
                        break
                else:
                    no_change = 0
                prev = count

            await browser.close()

        result = list(pins.values())
        self.log(f"🔍 مجموع: [bold green]{len(result)}[/] پین یافت شد")
        return result

    async def _dom_scan(self, page, pins: dict):
        try:
            items = await page.evaluate("""() => {
                const out = [];
                const seen = new Set();

                document.querySelectorAll('a[href*="/pin/"]').forEach(a => {
                    if (seen.has(a.href)) return;
                    const img = a.querySelector('img');
                    if (!img) return;
                    let src = img.src || img.currentSrc || '';
                    if (!src && img.srcset)
                        src = img.srcset.split(',').pop().trim().split(' ')[0];
                    if (!src) src = img.dataset.src || img.dataset.lazySrc || '';
                    if (src && src.includes('pinimg.com')) {
                        seen.add(a.href);
                        out.push({ href: a.href, src, alt: img.alt || '' });
                    }
                });

                document.querySelectorAll('img[src*="pinimg.com"]').forEach(img => {
                    const a = img.closest('a[href*="/pin/"]');
                    if (!a || seen.has(a.href)) return;
                    const src = img.src || img.currentSrc || '';
                    if (src) { seen.add(a.href); out.push({ href: a.href, src, alt: img.alt || '' }); }
                });

                return out;
            }""")

            for item in (items or []):
                src  = item.get("src", "")
                href = item.get("href", "")
                alt  = item.get("alt", "")
                if not src or "pinimg.com" not in src:
                    continue
                m = re.search(r'/pin/(\d+)', href)
                if not m:
                    continue
                pid = m.group(1)
                if pid not in pins:
                    url_736 = re.sub(r'/\d+x\d*/', '/736x/', src.split('?')[0])
                    pins[pid] = {
                        "pin_id": pid,
                        "url":    url_736,
                        "title":  sanitize(alt) or f"pin_{pid}",
                    }
        except Exception:
            pass


# ══════════════════════════════════════════════════════
#  دانلودر async
# ══════════════════════════════════════════════════════

class Downloader:
    def __init__(self, out: Path, concurrent: int = CONCURRENT_DL):
        self.out = out
        self.concurrent = concurrent
        self.out.mkdir(parents=True, exist_ok=True)
        self.con = Console(theme=DARK_THEME) if RICH else None
        self.ok = self.skip = self.fail = 0

    def log(self, msg, style="info"):
        if self.con: self.con.print(f"  {msg}", style=style)
        else: print(f"  {msg}")

    async def run(self, pins: list[dict]):
        sem  = asyncio.Semaphore(self.concurrent)
        conn = aiohttp.TCPConnector(limit=self.concurrent, ssl=False, ttl_dns_cache=300)
        tout = aiohttp.ClientTimeout(total=60, connect=10, sock_read=30)

        async with aiohttp.ClientSession(
            connector=conn, timeout=tout, headers=IMG_HEADERS
        ) as session:
            if RICH and self.con:
                with Progress(
                    SpinnerColumn(style="cyan"),
                    TextColumn("[progress.description]{task.description}"),
                    BarColumn(bar_width=35, style="cyan", complete_style="green"),
                    TextColumn("[bold]{task.completed}/{task.total}[/]"),
                    FileSizeColumn(),
                    TransferSpeedColumn(),
                    TimeRemainingColumn(),
                    console=self.con, expand=True,
                ) as prog:
                    tid = prog.add_task("📥 دانلود...", total=len(pins))
                    await asyncio.gather(*[
                        self._dl(session, sem, pin, prog, tid) for pin in pins
                    ])
            else:
                await asyncio.gather(*[self._dl(session, sem, pin) for pin in pins])

    async def _dl(self, session, sem, pin, prog=None, tid=None):
        def adv():
            if prog: prog.advance(tid)

        url   = pin.get("url", "")
        title = pin.get("title", "pin")
        pid   = pin.get("pin_id", "")

        if not url or not url.startswith("http"):
            self.skip += 1; adv(); return

        ext   = get_ext(url)
        fname = f"{sanitize(title)}_{pid}{ext}"
        fpath = self.out / fname

        if fpath.exists() and fpath.stat().st_size > MIN_IMAGE_SIZE:
            self.skip += 1; adv(); return

        candidates = best_urls(url)

        async with sem:
            for try_url in candidates:
                try:
                    async with session.get(try_url) as r:
                        if r.status == 200:
                            data = await r.read()
                            if len(data) > MIN_IMAGE_SIZE:
                                async with aiofiles.open(fpath, "wb") as f:
                                    await f.write(data)
                                self.ok += 1; adv(); return
                except Exception:
                    pass
            self.fail += 1; adv()


# ══════════════════════════════════════════════════════
#  UI
# ══════════════════════════════════════════════════════

def show_banner(con):
    if not con:
        print("=" * 46 + "\n  Pinterest Downloader ⚡ v4\n" + "=" * 46); return
    t = Text()
    t.append("  ╔══════════════════════════════════╗\n", "bold magenta")
    t.append("  ║  🖼  Pinterest Downloader  ⚡  v4 ║\n", "bold cyan")
    t.append("  ║  دانلودر پروفایل پینترست         ║\n", "bold white")
    t.append("  ╚══════════════════════════════════╝",   "bold magenta")
    con.print(t); con.print()

def show_summary(con, dl: Downloader):
    if not con:
        print(f"\nDone:{dl.ok}  Skipped:{dl.skip}  Failed:{dl.fail}  Path:{dl.out}"); return
    t = Table(box=box.ROUNDED, style="cyan", title="📊 نتیجه دانلود")
    t.add_column("وضعیت", style="bold")
    t.add_column("تعداد", justify="right", style="bold")
    t.add_row("✅ دانلود شد",   f"[green]{dl.ok}[/]")
    t.add_row("⏭  قبلاً بود",  f"[yellow]{dl.skip}[/]")
    t.add_row("❌ خطا",         f"[red]{dl.fail}[/]")
    t.add_row("📁 مسیر ذخیره", f"[cyan]{dl.out}[/]")
    con.print(t)


# ══════════════════════════════════════════════════════
#  main
# ══════════════════════════════════════════════════════

async def main():
    ap = argparse.ArgumentParser(description="Pinterest Downloader v4")
    ap.add_argument("profile_url")
    ap.add_argument("--section",    "-s", choices=["created","saved","boards"], default="created")
    ap.add_argument("--output",     "-o", default=None)
    ap.add_argument("--concurrent", "-c", type=int, default=CONCURRENT_DL)
    ap.add_argument("--no-dark",          action="store_true")
    ap.add_argument("--show-browser",     action="store_true")
    ap.add_argument("--save-urls",        action="store_true")
    args = ap.parse_args()

    dark = not args.no_dark
    con  = Console(theme=DARK_THEME) if RICH else None
    show_banner(con)

    username = get_username(args.profile_url)
    out_dir  = Path(args.output or f"pinterest_{username}_{args.section}")

    if con:
        con.print(Panel(
            f"[cyan]Profile:[/]    [bold]{args.profile_url}[/]\n"
            f"[cyan]Section:[/]    [bold]{args.section}[/]\n"
            f"[cyan]Output:[/]     [bold]{out_dir}[/]\n"
            f"[cyan]Concurrent:[/] [bold]{args.concurrent}[/]  "
            f"[cyan]Dark:[/] [bold]{'✓' if dark else '✗'}[/]",
            title="⚙️  Settings", border_style="magenta"
        ))

    scraper = PinterestScraper(dark=dark, headless=not args.show_browser)
    pins    = await scraper.scrape(args.profile_url, args.section)

    if not pins:
        msg = "❌ پین پیدا نشد! با --show-browser اجرا کن تا بررسی بشه"
        (con.print(f"[bold red]{msg}[/]") if con else print(msg))
        return

    if args.save_urls:
        out_dir.mkdir(parents=True, exist_ok=True)
        jp = out_dir / "pins.json"
        json.dump(pins, open(str(jp), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        (con.print(f"  💾 [cyan]{jp}[/]") if con else print(f"Saved: {jp}"))

    dl = Downloader(out_dir, concurrent=args.concurrent)
    await dl.run(pins)
    show_summary(con, dl)


if __name__ == "__main__":
    asyncio.run(main())