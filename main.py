#!/usr/bin/env python3
"""
Pinterest Profile Downloader  ⚡
=================================
نصب:
    pip install aiohttp aiofiles rich requests

استفاده:
    python main.py https://www.pinterest.com/jovelisher11
    python main.py https://www.pinterest.com/jovelisher11 --section saved
    python main.py https://www.pinterest.com/jovelisher11 -o ./photos -c 16
    python main.py https://www.pinterest.com/jovelisher11 --debug
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
from urllib.parse import urlparse

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
    from rich.syntax import Syntax
    from rich import box
    from rich.theme import Theme
    RICH = True
except ImportError:
    RICH = False

# ══════════════════════════════════════════════════════
DARK_THEME = Theme({
    "info": "bold cyan", "success": "bold green",
    "warning": "bold yellow", "error": "bold red", "dim": "grey50",
}) if RICH else None

CONCURRENT_DL  = 12
MIN_IMAGE_SIZE = 5000
SECTIONS = {"created": "_created/", "saved": "", "boards": "boards/"}

# هدرهای کاملاً شبیه مرورگر واقعی
BROWSER_HEADERS = {
    "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection":      "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest":  "document",
    "Sec-Fetch-Mode":  "navigate",
    "Sec-Fetch-Site":  "none",
    "Sec-Fetch-User":  "?1",
    "sec-ch-ua":       '"Chromium";v="122", "Not(A:Brand";v="24", "Google Chrome";v="122"',
    "sec-ch-ua-mobile":"?0",
    "sec-ch-ua-platform": '"Windows"',
}

API_HEADERS = {
    "User-Agent":      BROWSER_HEADERS["User-Agent"],
    "Accept":          "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "X-Requested-With":"XMLHttpRequest",
    "X-APP-VERSION":   "2f0e462",
    "X-Pinterest-AppState": "active",
    "Referer":         "https://www.pinterest.com/",
    "sec-ch-ua":       BROWSER_HEADERS["sec-ch-ua"],
    "sec-ch-ua-mobile":"?0",
    "sec-ch-ua-platform": '"Windows"',
    "Sec-Fetch-Dest":  "empty",
    "Sec-Fetch-Mode":  "cors",
    "Sec-Fetch-Site":  "same-origin",
}

IMG_HEADERS = {
    "User-Agent": BROWSER_HEADERS["User-Agent"],
    "Referer":    "https://www.pinterest.com/",
    "Accept":     "image/webp,image/apng,image/*,*/*;q=0.8",
    "Sec-Fetch-Dest": "image",
    "Sec-Fetch-Mode": "no-cors",
    "Sec-Fetch-Site": "cross-site",
}

# ══════════════════════════════════════════════════════
def get_username(url):
    return urlparse(url.rstrip("/")).path.strip("/").split("/")[0]

def sanitize(name):
    return re.sub(r'[\\/*?:"<>|]', "_", (name or "pin").strip())[:80] or "pin"

def best_urls(url):
    base = re.sub(r'/\d+x\d*/', '/736x/', url).split('?')[0]
    orig = base.replace('/736x/', '/originals/')
    s474 = base.replace('/736x/', '/474x/')
    seen, out = set(), []
    for u in [orig, base, s474, url.split('?')[0]]:
        if u not in seen: seen.add(u); out.append(u)
    return out

def get_ext(url):
    ext = os.path.splitext(urlparse(url).path)[1].lower()
    return ext if ext in ('.jpg','.jpeg','.png','.gif','.webp','.mp4') else '.jpg'

def extract_pins(data, found):
    if isinstance(data, list):
        for i in data: extract_pins(i, found)
        return
    if not isinstance(data, dict): return

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
                "pin_id":  pid,
                "url":     url,
                "title":   sanitize(data.get("title") or data.get("description") or f"pin_{pid}"),
                "pin_url": f"https://www.pinterest.com/pin/{pid}/",
            }
            return

    for v in data.values():
        if isinstance(v, (dict, list)): extract_pins(v, found)


# ══════════════════════════════════════════════════════
#  اسکرپر
# ══════════════════════════════════════════════════════

class PinterestScraper:
    BASE = "https://www.pinterest.com"

    def __init__(self, debug=False):
        self.debug = debug
        self.con   = Console(theme=DARK_THEME) if RICH else None
        self.sess  = requests.Session()
        self.sess.headers.update(BROWSER_HEADERS)

    def log(self, msg, style="info"):
        if self.con: self.con.print(f"  {msg}", style=style)
        else: print(f"  {msg}")

    def dbg(self, label, data):
        if not self.debug: return
        if self.con:
            if isinstance(data, (dict, list)):
                txt = json.dumps(data, ensure_ascii=False, indent=2)[:3000]
                self.con.print(f"\n[bold yellow]── {label} ──[/]")
                self.con.print(Syntax(txt, "json", theme="monokai"))
            else:
                self.con.print(f"\n[bold yellow]── {label} ──[/]\n{str(data)[:2000]}")
        else:
            print(f"\n── {label} ──\n{str(data)[:2000]}")

    # ── مرحله ۱: گرفتن session و cookie از صفحه اصلی ──────────────

    def init_session(self, username, section):
        suffix = SECTIONS.get(section, "_created/")
        url    = f"{self.BASE}/{username}/{suffix}"
        self.log(f"Getting session from [bold]{url}[/]")
        try:
            r = self.sess.get(url, timeout=20)
            self.log(f"Status: {r.status_code} | Cookies: {dict(r.cookies)}", "dim")
            self.dbg("HTML snippet (first 2000 chars)", r.text[:2000])

            # آپدیت کردن API headers با کوکی‌های گرفته‌شده
            self.sess.headers.update(API_HEADERS)

            # استخراج CSRFToken از کوکی یا HTML
            csrf = r.cookies.get("csrftoken", "")
            if not csrf:
                m = re.search(r'"csrftoken"\s*:\s*"([^"]+)"', r.text)
                if m: csrf = m.group(1)
            if csrf:
                self.sess.headers.update({"X-CSRFToken": csrf})
                self.log(f"CSRF: {csrf[:20]}...", "dim")

            # استخراج app version
            m = re.search(r'"appVersion"\s*:\s*"([^"]+)"', r.text)
            if m:
                self.sess.headers.update({"X-APP-VERSION": m.group(1)})
                self.log(f"App version: {m.group(1)}", "dim")

            return r.text
        except Exception as e:
            self.log(f"Session init error: {e}", "error")
            return ""

    # ── مرحله ۲: استخراج پین‌های اولیه از HTML ────────────────────

    def pins_from_html(self, html):
        found = {}
        if not html: return found

        # روش ۱: __PWS_DATA__
        for pattern in [
            r'<script id="__PWS_DATA__"[^>]*>({.+?})</script>',
            r'__PWS_DATA__\s*=\s*({.+?})(?:</script>|;)',
            r'P\.start\.start\(({.+?})\)',
        ]:
            m = re.search(pattern, html, re.S)
            if m:
                try:
                    data = json.loads(m.group(1))
                    extract_pins(data, found)
                    self.log(f"HTML __PWS_DATA__: {len(found)} pins", "dim")
                    if found: return found
                except Exception as e:
                    self.dbg(f"JSON parse error ({pattern[:30]})", str(e))

        # روش ۲: هر JSON که حاوی "images" و "id" باشه
        for m in re.finditer(r'\{"id"\s*:\s*"\d{10,}"[^}]{20,}"images"[^}]{10,}\}', html):
            try:
                data = json.loads(m.group(0) + "}")
                extract_pins(data, found)
            except Exception:
                pass

        # روش ۳: regex مستقیم برای URL های pinimg
        if not found:
            self.log("Trying direct regex for pinimg URLs...", "dim")
            pattern = r'"id"\s*:\s*"(\d{10,})"[^}]{0,800}?"url"\s*:\s*"(https://i\.pinimg\.com/[^"]+)"'
            for pid, img_url in re.findall(pattern, html):
                if pid not in found:
                    found[pid] = {"pin_id": pid, "url": img_url,
                                  "title": f"pin_{pid}", "pin_url": f"{self.BASE}/pin/{pid}/"}

        self.log(f"HTML extraction: {len(found)} pins", "dim")
        return found

    # ── مرحله ۳: API pagination ────────────────────────────────────

    def api_page(self, username, section, bookmark=None):
        """یک صفحه از Pinterest Resource API"""
        source = f"/{username}/{SECTIONS.get(section, '_created/')}"

        options = {
            "username":       username,
            "field_set_key":  "grid_item",
            "pin_filter":     "None",
            "privacy_filter": "all",
        }
        if section == "created":
            options["is_own_profile_pins"] = False
        if bookmark:
            options["bookmarks"] = [bookmark]

        payload = json.dumps({"options": options, "context": {}})
        params  = {"source_url": source, "data": payload, "_": int(time.time()*1000)}

        try:
            r = self.sess.get(
                f"{self.BASE}/resource/UserPinsResource/get/",
                params=params, timeout=15
            )
            self.log(f"API status: {r.status_code}", "dim")
            self.dbg(f"API response (page bm={bookmark})", r.text[:3000])

            if r.status_code == 200:
                return r.json()
        except Exception as e:
            self.log(f"API error: {e}", "error")
        return {}

    # ── جمع‌آوری کامل ─────────────────────────────────────────────

    def collect(self, username, section):
        self.log(f"[bold]{username}[/] / [bold]{section}[/]")
        all_pins = {}

        # مرحله ۱: session + HTML
        html = self.init_session(username, section)
        html_pins = self.pins_from_html(html)
        all_pins.update(html_pins)
        self.log(f"After HTML: [bold green]{len(all_pins)}[/] pins")

        # مرحله ۲: API pagination
        bookmark = None
        page = 0
        while True:
            page += 1
            resp = self.api_page(username, section, bookmark)
            if not resp:
                self.log("No API response, stopping", "warning")
                break

            before = len(all_pins)
            extract_pins(resp, all_pins)
            after = len(all_pins)
            self.log(f"   API page {page}: +{after-before} new | Total: [bold green]{after}[/]", "dim")

            # پیدا کردن bookmark
            try:
                rr = resp.get("resource_response", {})
                bm = rr.get("bookmark")
                if not bm:
                    bm = resp.get("resource", {}).get("options", {}).get("bookmarks", [None])
                    if isinstance(bm, list): bm = bm[0] if bm else None
            except Exception:
                bm = None

            if bm in (None, "", "-end-") or after == before:
                break
            bookmark = bm
            time.sleep(0.4)

        self.log(f"[bold green]{len(all_pins)}[/] total pins collected")
        return list(all_pins.values())


# ══════════════════════════════════════════════════════
#  دانلودر
# ══════════════════════════════════════════════════════

class Downloader:
    def __init__(self, out, concurrent=CONCURRENT_DL):
        self.out = Path(out)
        self.concurrent = concurrent
        self.out.mkdir(parents=True, exist_ok=True)
        self.con = Console(theme=DARK_THEME) if RICH else None
        self.ok = self.skip = self.fail = 0

    async def run(self, pins):
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
                    FileSizeColumn(), TransferSpeedColumn(), TimeRemainingColumn(),
                    console=self.con, expand=True,
                ) as prog:
                    tid = prog.add_task("Downloading...", total=len(pins))
                    await asyncio.gather(*[self._dl(session, sem, p, prog, tid) for p in pins])
            else:
                await asyncio.gather(*[self._dl(session, sem, p) for p in pins])

    async def _dl(self, session, sem, pin, prog=None, tid=None):
        def adv():
            if prog: prog.advance(tid)

        url, title, pid = pin.get("url",""), pin.get("title","pin"), pin.get("pin_id","0")
        if not url or not url.startswith("http"):
            self.skip += 1; adv(); return

        fpath = self.out / f"{sanitize(title)}_{pid}{get_ext(url)}"
        if fpath.exists() and fpath.stat().st_size > MIN_IMAGE_SIZE:
            self.skip += 1; adv(); return

        async with sem:
            for try_url in best_urls(url):
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
        print("=" * 46 + "\n  Pinterest Downloader\n" + "=" * 46); return
    t = Text()
    t.append("  ╔══════════════════════════════════╗\n", "bold magenta")
    t.append("  ║  🖼  Pinterest Downloader  ⚡     ║\n", "bold cyan")
    t.append("  ║  دانلودر پروفایل پینترست         ║\n", "bold white")
    t.append("  ╚══════════════════════════════════╝",   "bold magenta")
    con.print(t); con.print()

def show_summary(con, dl):
    if not con:
        print(f"\nDone:{dl.ok}  Skipped:{dl.skip}  Failed:{dl.fail}  Path:{dl.out}"); return
    t = Table(box=box.ROUNDED, style="cyan", title="📊 Result")
    t.add_column("Status", style="bold"); t.add_column("Count", justify="right", style="bold")
    t.add_row("✅ Downloaded",    f"[green]{dl.ok}[/]")
    t.add_row("⏭  Already had",  f"[yellow]{dl.skip}[/]")
    t.add_row("❌ Failed",        f"[red]{dl.fail}[/]")
    t.add_row("📁 Output",        f"[cyan]{dl.out}[/]")
    con.print(t)


# ══════════════════════════════════════════════════════
async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("profile_url")
    ap.add_argument("--section",    "-s", choices=["created","saved","boards"], default="created")
    ap.add_argument("--output",     "-o", default=None)
    ap.add_argument("--concurrent", "-c", type=int, default=CONCURRENT_DL)
    ap.add_argument("--save-urls",        action="store_true")
    ap.add_argument("--debug",            action="store_true", help="نمایش جواب‌های خام API")
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
            f"[cyan]Concurrent:[/] [bold]{args.concurrent}[/]  "
            f"[cyan]Debug:[/] [bold]{'on' if args.debug else 'off'}[/]",
            title="Settings", border_style="magenta"
        ))

    scraper = PinterestScraper(debug=args.debug)
    pins    = scraper.collect(username, args.section)

    if not pins:
        msg = "No pins found!\nRun with --debug to see raw API responses."
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