#!/usr/bin/env python3
"""
Pinterest Profile Downloader  ⚡ API Edition
=============================================
نصب:
    pip install aiohttp aiofiles rich requests

استفاده:
    python main.py https://www.pinterest.com/jovelisher11
    python main.py https://www.pinterest.com/jovelisher11 --section saved
    python main.py https://www.pinterest.com/jovelisher11 -o ./photos -c 16
    python main.py https://www.pinterest.com/jovelisher11 --save-urls
"""

import asyncio
import aiohttp
import aiofiles
import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlparse, quote

try:
    import requests
except ImportError:
    print("pip install requests"); sys.exit(1)

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

CONCURRENT_DL  = 12
MIN_IMAGE_SIZE = 5000   # بایت — کمتر از این = خراب
CHUNK_SIZE     = 131072

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept":          "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer":         "https://www.pinterest.com/",
    "X-Requested-With":"XMLHttpRequest",
    "X-APP-VERSION":   "2f0e462",
    "X-Pinterest-AppState": "active",
}

IMG_HEADERS = {
    "User-Agent": HEADERS["User-Agent"],
    "Referer":    "https://www.pinterest.com/",
    "Accept":     "image/webp,image/apng,image/*,*/*;q=0.8",
    "Sec-Fetch-Dest": "image",
    "Sec-Fetch-Mode": "no-cors",
    "Sec-Fetch-Site": "cross-site",
}

# ══════════════════════════════════════════════════════
#  ابزار
# ══════════════════════════════════════════════════════

def get_username(url: str) -> str:
    return urlparse(url.rstrip("/")).path.strip("/").split("/")[0]

def sanitize(name: str) -> str:
    return re.sub(r'[\\/*?:"<>|]', "_", (name or "pin").strip())[:80] or "pin"

def best_urls(url: str) -> list:
    """لیست URL از بهترین کیفیت به پایین"""
    base = re.sub(r'/\d+x\d*/', '/736x/', url).split('?')[0]
    orig = base.replace('/736x/', '/originals/')
    s474 = base.replace('/736x/', '/474x/')
    seen, result = set(), []
    for u in [orig, base, s474, url.split('?')[0]]:
        if u not in seen:
            seen.add(u); result.append(u)
    return result

def get_ext(url: str) -> str:
    ext = os.path.splitext(urlparse(url).path)[1].lower()
    return ext if ext in ('.jpg','.jpeg','.png','.gif','.webp','.mp4') else '.jpg'

def extract_pins_from_json(data, found: dict):
    """استخراج بازگشتی پین از هر JSON"""
    if isinstance(data, list):
        for item in data:
            extract_pins_from_json(item, found)
        return
    if not isinstance(data, dict):
        return

    pid  = str(data.get("id", ""))
    imgs = data.get("images", {})
    if pid and pid.isdigit() and imgs:
        url = (
            (imgs.get("736x") or {}).get("url") or
            (imgs.get("474x") or {}).get("url") or
            (imgs.get("236x") or {}).get("url") or ""
        )
        if url and pid not in found:
            found[pid] = {
                "pin_id": pid,
                "url":    url,
                "title":  sanitize(data.get("title") or data.get("description") or f"pin_{pid}"),
                "pin_url": f"https://www.pinterest.com/pin/{pid}/",
            }
            return   # پیدا شد، نیازی به بازگشت عمیق‌تر نیست

    for v in data.values():
        if isinstance(v, (dict, list)):
            extract_pins_from_json(v, found)


# ══════════════════════════════════════════════════════
#  اسکرپر از طریق API مستقیم
# ══════════════════════════════════════════════════════

class PinterestAPI:
    """
    استفاده از Pinterest resource API بدون نیاز به browser
    endpoint: /resource/UserPinsResource/get/
    """

    BASE = "https://www.pinterest.com"

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self.con = Console(theme=DARK_THEME) if RICH else None

    def log(self, msg, style="info"):
        if self.con:
            self.con.print(f"  {msg}", style=style)
        else:
            print(f"  {msg}")

    def _get_bookmarks(self, username: str, section: str, bookmark: str = None) -> dict:
        """
        یک صفحه از پین‌ها رو می‌گیره
        bookmark = cursor برای صفحه بعدی
        """
        # section_id های مختلف
        section_map = {
            "created": None,   # UserPinsResource
            "saved":   None,   # UserPinsResource با type=saved
        }

        if section == "created":
            resource = "UserPinsResource"
            options = {
                "username": username,
                "field_set_key": "grid_item",
                "is_own_profile_pins": False,
                "privacy_filter": "all",
                "pin_filter": "None",
            }
        else:
            resource = "UserPinsResource"
            options = {
                "username":       username,
                "field_set_key":  "grid_item",
                "pin_filter":     "None",
            }

        if bookmark:
            options["bookmarks"] = [bookmark]

        params = {
            "source_url": f"/{username}/",
            "data": json.dumps({"options": options, "context": {}}),
            "_": int(time.time() * 1000),
        }

        url = f"{self.BASE}/resource/{resource}/get/"
        try:
            r = self.session.get(url, params=params, timeout=15)
            if r.status_code == 200:
                return r.json()
        except Exception as e:
            self.log(f"API error: {e}", "error")
        return {}

    def _get_created_via_source(self, username: str, bookmark: str = None) -> dict:
        """
        دریافت پین‌های created از endpoint اختصاصی
        """
        options = {
            "username":       username,
            "field_set_key":  "grid_item",
        }
        if bookmark:
            options["bookmarks"] = [bookmark]

        params = {
            "source_url": f"/{username}/_created/",
            "data": json.dumps({"options": options, "context": {}}),
            "_": int(time.time() * 1000),
        }
        url = f"{self.BASE}/resource/UserPinsResource/get/"
        try:
            r = self.session.get(url, params=params, timeout=15)
            if r.status_code == 200:
                return r.json()
        except Exception as e:
            self.log(f"API error: {e}", "error")
        return {}

    def _scrape_html_fallback(self, username: str, section: str) -> dict:
        """
        fallback: استخراج JSON از HTML صفحه پروفایل
        Pinterest اولین batch رو داخل HTML قرار می‌ده
        """
        section_suffix = {"created": "_created/", "saved": "", "boards": "boards/"}.get(section, "_created/")
        url = f"{self.BASE}/{username}/{section_suffix}"
        self.log(f"HTML fallback: {url}", "dim")
        try:
            r = self.session.get(url, timeout=20)
            if r.status_code != 200:
                return {}
            html = r.text

            # Pinterest داده‌ها رو داخل window.__initialState__ یا JSON-LD قرار می‌ده
            found = {}

            # روش ۱: initial redux state
            m = re.search(r'__PWS_DATA__\s*=\s*({.+?})\s*</script>', html, re.S)
            if m:
                try:
                    data = json.loads(m.group(1))
                    extract_pins_from_json(data, found)
                except Exception:
                    pass

            # روش ۲: جستجوی مستقیم URL های pinimg در HTML
            if not found:
                img_urls = re.findall(
                    r'"id"\s*:\s*"(\d+)"[^}]{0,500}?"url"\s*:\s*"(https://i\.pinimg\.com/[^"]+)"',
                    html
                )
                for pid, img_url in img_urls:
                    if pid not in found:
                        found[pid] = {
                            "pin_id": pid,
                            "url":    img_url,
                            "title":  f"pin_{pid}",
                            "pin_url": f"https://www.pinterest.com/pin/{pid}/",
                        }

            # روش ۳: هر URL pinimg در صفحه
            if not found:
                raw_urls = re.findall(r'https://i\.pinimg\.com/\d+x\d*/[a-f0-9/]+\.jpg', html)
                for i, u in enumerate(set(raw_urls)):
                    pid = str(i)
                    found[pid] = {"pin_id": pid, "url": u, "title": f"pin_{i}", "pin_url": ""}

            return found
        except Exception as e:
            self.log(f"HTML fallback error: {e}", "error")
            return {}

    def collect_all_pins(self, username: str, section: str) -> list[dict]:
        """
        جمع‌آوری همه پین‌ها با pagination
        """
        self.log(f"[bold]User:[/] {username}  [bold]Section:[/] {section}")
        all_pins: dict = {}
        bookmark = None
        page = 0

        while True:
            page += 1
            self.log(f"   Page {page} | Pins so far: [bold green]{len(all_pins)}[/]", "dim")

            if section == "created":
                resp = self._get_created_via_source(username, bookmark)
            else:
                resp = self._get_bookmarks(username, section, bookmark)

            if not resp:
                break

            # استخراج پین‌ها
            before = len(all_pins)
            extract_pins_from_json(resp, all_pins)

            # استخراج bookmark برای صفحه بعد
            try:
                bm_list = (
                    resp.get("resource_response", {})
                        .get("bookmark") or
                    resp.get("resource", {})
                        .get("options", {})
                        .get("bookmarks", [None])
                )
                if isinstance(bm_list, list):
                    bookmark = bm_list[0] if bm_list else None
                elif isinstance(bm_list, str):
                    bookmark = bm_list
                else:
                    bookmark = None
            except Exception:
                bookmark = None

            # شرط توقف
            if bookmark in (None, "", "-end-") or len(all_pins) == before:
                break

            time.sleep(0.3)  # کمی صبر بین درخواست‌ها

        # اگه API چیزی نداد، HTML fallback
        if not all_pins:
            self.log("API returned nothing, trying HTML fallback...", "warning")
            all_pins = self._scrape_html_fallback(username, section)

        self.log(f"[bold green]{len(all_pins)}[/] pins collected")
        return list(all_pins.values())


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
        if self.con:
            self.con.print(f"  {msg}", style=style)
        else:
            print(f"  {msg}")

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
                    tid = prog.add_task("Downloading...", total=len(pins))
                    await asyncio.gather(*[self._dl(session, sem, p, prog, tid) for p in pins])
            else:
                await asyncio.gather(*[self._dl(session, sem, p) for p in pins])

    async def _dl(self, session, sem, pin, prog=None, tid=None):
        def adv():
            if prog: prog.advance(tid)

        url   = pin.get("url", "")
        title = pin.get("title", "pin")
        pid   = pin.get("pin_id", str(hash(url)))

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
                            # فایل خیلی کوچیکه، URL بعدی رو امتحان کن
                except Exception:
                    pass
            self.fail += 1; adv()


# ══════════════════════════════════════════════════════
#  UI
# ══════════════════════════════════════════════════════

def show_banner(con):
    if not con:
        print("=" * 46 + "\n  Pinterest Downloader ⚡\n" + "=" * 46); return
    t = Text()
    t.append("  ╔══════════════════════════════════╗\n", "bold magenta")
    t.append("  ║  🖼  Pinterest Downloader  ⚡     ║\n", "bold cyan")
    t.append("  ║  دانلودر پروفایل پینترست         ║\n", "bold white")
    t.append("  ╚══════════════════════════════════╝",   "bold magenta")
    con.print(t); con.print()

def show_summary(con, dl: Downloader):
    if not con:
        print(f"\nDone:{dl.ok}  Skipped:{dl.skip}  Failed:{dl.fail}  Path:{dl.out}"); return
    t = Table(box=box.ROUNDED, style="cyan", title="📊 Result")
    t.add_column("Status", style="bold")
    t.add_column("Count",  justify="right", style="bold")
    t.add_row("✅ Downloaded",    f"[green]{dl.ok}[/]")
    t.add_row("⏭  Already had",  f"[yellow]{dl.skip}[/]")
    t.add_row("❌ Failed",        f"[red]{dl.fail}[/]")
    t.add_row("📁 Output",        f"[cyan]{dl.out}[/]")
    con.print(t)


# ══════════════════════════════════════════════════════
#  main
# ══════════════════════════════════════════════════════

async def main():
    ap = argparse.ArgumentParser(description="Pinterest Profile Downloader")
    ap.add_argument("profile_url")
    ap.add_argument("--section",    "-s", choices=["created","saved","boards"], default="created")
    ap.add_argument("--output",     "-o", default=None)
    ap.add_argument("--concurrent", "-c", type=int, default=CONCURRENT_DL)
    ap.add_argument("--save-urls",        action="store_true")
    args = ap.parse_args()

    con = Console(theme=DARK_THEME) if RICH else None
    show_banner(con)

    username = get_username(args.profile_url)
    out_dir  = Path(args.output or f"pinterest_{username}_{args.section}")

    if con:
        con.print(Panel(
            f"[cyan]Profile:[/]    [bold]{args.profile_url}[/]\n"
            f"[cyan]Section:[/]    [bold]{args.section}[/]\n"
            f"[cyan]Output:[/]     [bold]{out_dir}[/]\n"
            f"[cyan]Concurrent:[/] [bold]{args.concurrent}[/]",
            title="Settings", border_style="magenta"
        ))

    # اسکرپ
    api  = PinterestAPI()
    pins = api.collect_all_pins(username, args.section)

    if not pins:
        msg = "No pins found! Profile might be private or username is wrong."
        (con.print(f"[bold red]{msg}[/]") if con else print(msg))
        return

    # ذخیره JSON
    if args.save_urls:
        out_dir.mkdir(parents=True, exist_ok=True)
        jp = out_dir / "pins.json"
        json.dump(pins, open(str(jp), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        msg = f"URLs saved: {jp}"
        (con.print(f"  [cyan]{msg}[/]") if con else print(msg))

    # دانلود
    dl = Downloader(out_dir, concurrent=args.concurrent)
    await dl.run(pins)
    show_summary(con, dl)


if __name__ == "__main__":
    asyncio.run(main())