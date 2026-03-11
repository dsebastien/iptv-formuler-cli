#!/usr/bin/env python3
"""
Formuler IPTV Remote Control via ADB

Usage:
  ./formuler-remote.py [--json] [device_ip] [command] [args...]

Examples:
  ./formuler-remote.py                                  # interactive mode
  ./formuler-remote.py tune TF1                          # tune live channel
  ./formuler-remote.py play-movie batman                 # search & play a movie
  ./formuler-remote.py play-series "breaking bad" 1 4    # play S1E4
  ./formuler-remote.py search-vod batman                 # search movies on device
  ./formuler-remote.py search-series "walking dead"      # search series on device
  ./formuler-remote.py star                              # toggle star on current page
  ./formuler-remote.py star-vod batman                   # find movie & toggle star
  ./formuler-remote.py section vod                       # switch to VOD section
  ./formuler-remote.py stop-vod                          # stop with confirmation
  ./formuler-remote.py --json categories                 # JSON output for scripting
  ./formuler-remote.py macro morning                     # run a saved macro

Prerequisites:
  1. Install ADB: sudo pacman -S android-tools
  2. Enable ADB on Formuler: Settings > Developer Options > ADB Debugging > ON
  3. Find device IP: Settings > Network (on the Formuler)
"""

import datetime
import json
import os
import re
import subprocess
import sys
import shutil
import threading
import time
import readline  # arrow-key history in interactive mode
from pathlib import Path

# ──────────────────────── Color Support ────────────────────────


class _C:
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    CYAN = "\033[36m"
    MAGENTA = "\033[35m"
    RESET = "\033[0m"


if not sys.stdout.isatty() or os.environ.get("NO_COLOR"):
    for _attr in ("BOLD", "DIM", "RED", "GREEN", "YELLOW", "BLUE", "CYAN", "MAGENTA", "RESET"):
        setattr(_C, _attr, "")


# ──────────────────────── Config ────────────────────────

CONFIG_DIR = Path.home() / ".config" / "formuler-remote"
CONFIG_FILE = CONFIG_DIR / "config.toml"
CONFIG_JSON = CONFIG_DIR / "config.json"


def _load_config() -> dict:
    if CONFIG_FILE.exists():
        try:
            import tomllib
            with open(CONFIG_FILE, "rb") as f:
                return tomllib.load(f)
        except ImportError:
            pass
    if CONFIG_JSON.exists():
        try:
            with open(CONFIG_JSON) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {}


CONFIG = _load_config()

# ──────────────────────── Constants ────────────────────────

ADB_PORT = CONFIG.get("device", {}).get("port", 5555)
DEFAULT_IP = CONFIG.get("device", {}).get("ip", "192.168.0.100")
MOL3_PKG = "tv.formuler.mol3.real"
CACHE_DIR = Path.home() / ".cache" / "formuler-remote"
CHANNELS_CACHE = CACHE_DIR / "channels.json"
FULL_CHANNELS_CACHE = CACHE_DIR / "full_channels.json"

JSON_MODE = False

KEYS = {
    "power": 26, "home": 3, "back": 4, "menu": 82,
    "up": 19, "down": 20, "left": 21, "right": 22,
    "ok": 66, "select": 23,
    "play": 126, "pause": 127, "play-pause": 85, "stop": 86,
    "rewind": 89, "fast-forward": 90, "next": 87, "previous": 88,
    "mute": 164, "volume-up": 24, "volume-down": 25,
    "channel-up": 166, "channel-down": 167,
    "info": 165, "guide": 172,
    "record": 130, "delete": 112, "tab": 61,
    "wakeup": 224, "sleep": 223,
    "0": 7, "1": 8, "2": 9, "3": 10, "4": 11,
    "5": 12, "6": 13, "7": 14, "8": 15, "9": 16,
}

CATEGORIES = {
    1: "Live History", 3: "VOD History", 4: "Favorites",
    5: "Series History", 6: "Series Favorites", 7: "VOD Favorites",
}

MOL3_SECTIONS = {
    "live": 0, "tv": 0, "vod": 1, "movies": 1, "series": 2,
    "radio": 3, "radios": 3, "matchday": 4, "recordings": 5,
    "schedule": 6, "content": 7, "notifications": 8, "settings": 9,
}

KNOWN_APPS = {
    "mytvonline": MOL3_PKG, "mytv": MOL3_PKG, "mol3": MOL3_PKG,
    "youtube": "com.google.android.youtube.tv",
    "netflix": "com.netflix.ninja",
    "plex": "com.plexapp.android",
    "kodi": "org.xbmc.kodi",
    "vlc": "org.videolan.vlc",
    "prime": "com.amazon.amazonvideo.livingroom",
    "disney": "com.disney.disneyplus",
    "settings": "com.android.tv.settings",
}

SEARCH_PREFIXES = (
    list("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
    + list("0123456789")
    + ["|BE|", "|FR|", "|NL|", "|UK|", "|US|", "|DE|", "|ES|", "|IT|", "|PT|"]
)


# ──────────────────────── Output Helpers ────────────────────────


def output(data, human_text: str = ""):
    if JSON_MODE:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        print(human_text or str(data))


def info(msg: str):
    if not JSON_MODE:
        print(f"{_C.GREEN}{msg}{_C.RESET}")


def warn(msg: str):
    if not JSON_MODE:
        print(f"{_C.YELLOW}{msg}{_C.RESET}")


def error(msg: str):
    if not JSON_MODE:
        print(f"{_C.RED}{msg}{_C.RESET}")
    else:
        print(json.dumps({"error": msg}), file=sys.stderr)


def _notify(title: str, body: str = ""):
    if shutil.which("notify-send"):
        subprocess.Popen(
            ["notify-send", "-a", "Formuler Remote", title, body],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )


# ══════════════════════════════════════════════════════════════
#  ADB TRANSPORT
# ══════════════════════════════════════════════════════════════

_current_ip: str = ""


def run_adb(*args: str, timeout: int = 10) -> tuple[int, str]:
    try:
        result = subprocess.run(
            ["adb", *args], capture_output=True, text=True, timeout=timeout
        )
        return result.returncode, (result.stdout + result.stderr).strip()
    except subprocess.TimeoutExpired:
        return 1, "timeout"
    except FileNotFoundError:
        return 1, "adb not found"


def tgt(ip: str) -> str:
    return f"{ip}:{ADB_PORT}"


def adb(ip: str, *args: str, timeout: int = 10) -> tuple[int, str]:
    """Run ADB command with auto-reconnect on connection loss."""
    code, out = run_adb("-s", tgt(ip), *args, timeout=timeout)
    if code != 0 and ("error: device" in out.lower() or "not found" in out.lower()
                       or "offline" in out.lower()):
        warn("Connection lost. Reconnecting...")
        if connect(ip, quiet=True):
            code, out = run_adb("-s", tgt(ip), *args, timeout=timeout)
    return code, out


def connect(ip: str, quiet: bool = False) -> bool:
    global _current_ip
    code, out = run_adb("connect", tgt(ip))
    if "connected" in out.lower():
        _current_ip = ip
        if not quiet:
            info(f"Connected to {tgt(ip)}")
        return True
    error(f"Failed to connect: {out}")
    return False


def key(ip: str, name: str) -> bool:
    if name not in KEYS:
        error(f"Unknown key: {name}")
        return False
    adb(ip, "shell", "input", "keyevent", str(KEYS[name]))
    return True


def keys(ip: str, *names: str, delay: float = 0.25):
    for n in names:
        key(ip, n)
        time.sleep(delay)


def text_input(ip: str, t: str) -> bool:
    code, _ = adb(ip, "shell", "input", "text", t.replace(" ", "%s"))
    return code == 0


def wait(seconds: float = 1.0):
    time.sleep(seconds)


# ══════════════════════════════════════════════════════════════
#  APP MANAGEMENT
# ══════════════════════════════════════════════════════════════

def is_mytv_foreground(ip: str) -> bool:
    code, out = adb(ip, "shell", "dumpsys", "activity", "recents", timeout=5)
    for line in out.splitlines():
        if "Recent #0" in line or "topActivity" in line:
            if MOL3_PKG in line:
                return True
            break
    return False


def ensure_mytv(ip: str):
    if not is_mytv_foreground(ip):
        warn("Launching MyTVOnline...")
        adb(ip, "shell", "monkey", "-p", MOL3_PKG,
            "-c", "android.intent.category.LAUNCHER", "1")
        wait(3)


def open_app(ip: str, package: str):
    code, out = adb(ip, "shell", "monkey", "-p", package,
                    "-c", "android.intent.category.LAUNCHER", "1")
    if code != 0 or "No activities found" in out:
        error(f"Error launching {package}: {out}")
    else:
        info(f"Launched {package}")


def list_apps(ip: str):
    code, out = adb(ip, "shell", "pm", "list", "packages", "-3")
    if code == 0:
        pkgs = sorted(l.replace("package:", "") for l in out.splitlines() if l.startswith("package:"))
        if JSON_MODE:
            output(pkgs)
        else:
            for pkg in pkgs:
                print(f"  {pkg}")


# ══════════════════════════════════════════════════════════════
#  SECTION NAVIGATION
# ══════════════════════════════════════════════════════════════

def go_to_section(ip: str, section: str) -> bool:
    section = section.lower()
    if section not in MOL3_SECTIONS:
        error(f"Unknown section: {section}")
        print(f"Available: {', '.join(sorted(set(MOL3_SECTIONS.keys())))}")
        return False

    ensure_mytv(ip)
    key(ip, "menu")
    wait(0.5)
    for _ in range(MOL3_SECTIONS[section]):
        key(ip, "down")
        wait(0.2)
    key(ip, "ok")
    wait(1.5)
    info(f"Switched to: {section}")
    return True


# ══════════════════════════════════════════════════════════════
#  IN-APP SEARCH
# ══════════════════════════════════════════════════════════════

def open_search(ip: str, section: str = "vod"):
    go_to_section(ip, section)
    key(ip, "right")
    wait(0.3)
    for _ in range(10):
        key(ip, "up")
        wait(0.15)
    key(ip, "ok")
    wait(1)


def do_search(ip: str, query: str, section: str = "vod"):
    open_search(ip, section)
    text_input(ip, query)
    wait(0.5)
    key(ip, "ok")
    wait(2)
    info(f"Searched for '{query}' in {section}")


def select_first_result(ip: str):
    key(ip, "down")
    wait(0.3)
    key(ip, "ok")
    wait(2)


# ══════════════════════════════════════════════════════════════
#  PLAYBACK CONTROL
# ══════════════════════════════════════════════════════════════

def stop_playback(ip: str):
    key(ip, "stop")
    wait(1)
    key(ip, "up")
    wait(0.2)
    key(ip, "ok")
    info("Playback stopped.")


# ══════════════════════════════════════════════════════════════
#  PLAY MOVIE
# ══════════════════════════════════════════════════════════════

def play_movie(ip: str, query: str):
    do_search(ip, query, section="vod")
    select_first_result(ip)
    key(ip, "ok")
    wait(1)
    info(f"Playing movie: '{query}'")
    _notify("Formuler Remote", f"Playing: {query}")


# ══════════════════════════════════════════════════════════════
#  PLAY SERIES EPISODE
# ══════════════════════════════════════════════════════════════

def play_series(ip: str, query: str, season: int = 1, episode: int = 1):
    do_search(ip, query, section="series")
    select_first_result(ip)

    # Navigate to "Tous les épisodes" (last button before Star)
    keys(ip, "right", "right", "right", delay=0.2)
    wait(0.2)
    key(ip, "left")  # back from Star
    wait(0.2)
    key(ip, "ok")    # open episodes browser
    wait(2)

    if season > 1:
        for _ in range(season - 1):
            key(ip, "down")
            wait(0.3)
        wait(0.5)

    key(ip, "right")
    wait(0.3)

    if episode > 1:
        for _ in range(episode - 1):
            key(ip, "down")
            wait(0.3)

    key(ip, "ok")
    wait(1)
    label = f"'{query}' S{season:02d}E{episode:02d}"
    info(f"Playing {label}")
    _notify("Formuler Remote", f"Playing: {label}")


# ══════════════════════════════════════════════════════════════
#  STAR / FAVORITE TOGGLE
# ══════════════════════════════════════════════════════════════

def toggle_star(ip: str):
    keys(ip, "right", "right", "right", "right", delay=0.15)
    wait(0.2)
    key(ip, "ok")
    wait(0.5)
    keys(ip, "left", "left", "left", "left", delay=0.15)
    info("Star toggled.")


def star_search(ip: str, query: str, content_type: str = "vod"):
    do_search(ip, query, section=content_type)
    select_first_result(ip)
    toggle_star(ip)
    key(ip, "back")
    wait(0.5)
    info(f"Toggled star for '{query}'")


# ══════════════════════════════════════════════════════════════
#  CONTENT PROVIDERS
# ══════════════════════════════════════════════════════════════

def _parse_content_rows(raw: str) -> list[dict]:
    rows = []
    for line in raw.splitlines():
        if not line.startswith("Row:"):
            continue
        row = {}
        data = re.sub(r"^Row:\s+\d+\s+", "", line)
        for match in re.finditer(r"(\w+)=(.*?)(?=, \w+=|$)", data):
            k, v = match.group(1), match.group(2).strip()
            row[k] = None if v == "NULL" else v
        rows.append(row)
    return rows


def fetch_channels(ip: str) -> list[dict]:
    if not JSON_MODE:
        print("Fetching channels from device...", end="", flush=True)
    code, out = adb(
        ip, "shell", "content", "query",
        "--uri", "content://formuler.media.tv/preview_program",
        "--projection", "title:content_id:channel_id:poster_art_uri:intent_uri:short_description",
        timeout=30
    )
    if code != 0:
        if not JSON_MODE:
            print()
        return []
    channels = []
    for row in _parse_content_rows(out):
        title = row.get("title", "")
        content_id = row.get("content_id", "")
        if not title or title == content_id:
            continue
        cat_id = int(row.get("channel_id", 0))
        channels.append({
            "title": title, "content_id": content_id,
            "category_id": cat_id, "category": CATEGORIES.get(cat_id, "Unknown"),
            "logo": row.get("poster_art_uri"), "intent": row.get("intent_uri"),
            "description": row.get("short_description"),
        })
    if not JSON_MODE:
        print(f" {len(channels)} entries")
    return channels


def search_provider(ip: str, query: str) -> list[dict]:
    code, out = adb(
        ip, "shell", "content", "query",
        "--uri", f"content://tv.formuler.mol3.real.searchProvider/search_suggest_query/{query}",
        timeout=15
    )
    if code != 0:
        return []
    results = []
    for row in _parse_content_rows(out):
        t = row.get("suggest_text_1", "")
        intent_data = row.get("suggest_intent_data", "")
        num_m = re.match(r"^(\d+)\.\s+(.+)", t)
        uid_m = re.search(r"uniqueId=([^&]+)", intent_data) if intent_data else None
        results.append({
            "number": num_m.group(1) if num_m else None,
            "title": num_m.group(2) if num_m else t,
            "unique_id": uid_m.group(1) if uid_m else None,
            "logo": row.get("suggest_result_card_image"),
        })
    return results


def get_channels(ip: str, force_refresh: bool = False) -> list[dict]:
    if not force_refresh and CHANNELS_CACHE.exists():
        with open(CHANNELS_CACHE) as f:
            return json.load(f)
    channels = fetch_channels(ip)
    if channels:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        with open(CHANNELS_CACHE, "w") as f:
            json.dump(channels, f, indent=2, ensure_ascii=False)
        info(f"Cached {len(channels)} channels/entries")
    return channels


# ══════════════════════════════════════════════════════════════
#  FULL CHANNEL ENUMERATION (Phase 7)
# ══════════════════════════════════════════════════════════════

def enumerate_channels(ip: str) -> list[dict]:
    seen_ids: set[str] = set()
    all_channels: list[dict] = []
    total = len(SEARCH_PREFIXES)
    for i, prefix in enumerate(SEARCH_PREFIXES):
        if not JSON_MODE:
            print(f"\r  Enumerating channels... {i + 1}/{total} (found {len(all_channels)})", end="", flush=True)
        results = search_provider(ip, prefix)
        for r in results:
            uid = r.get("unique_id")
            if uid and uid not in seen_ids:
                seen_ids.add(uid)
                all_channels.append(r)
    if not JSON_MODE:
        print(f"\r  Enumerated {len(all_channels)} unique channels from {total} queries.     ")
    all_channels.sort(key=lambda c: int(c["number"]) if c.get("number") and c["number"].isdigit() else 99999)
    return all_channels


def get_full_channels(ip: str, force_refresh: bool = False) -> list[dict]:
    max_age = CONFIG.get("cache", {}).get("channels_max_age_hours", 24)
    if not force_refresh and FULL_CHANNELS_CACHE.exists():
        age_hours = (time.time() - FULL_CHANNELS_CACHE.stat().st_mtime) / 3600
        if age_hours < max_age:
            with open(FULL_CHANNELS_CACHE) as f:
                return json.load(f)
        warn(f"Channel cache stale ({age_hours:.0f}h old). Refreshing...")

    channels = enumerate_channels(ip)
    if channels:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        with open(FULL_CHANNELS_CACHE, "w") as f:
            json.dump(channels, f, indent=2, ensure_ascii=False)
        info(f"Cached {len(channels)} channels")
    return channels


def channel_by_number(ip: str, number: str) -> dict | None:
    for ch in get_full_channels(ip):
        if ch.get("number") == number:
            return ch
    return None


# ══════════════════════════════════════════════════════════════
#  LIVE TV COMMANDS
# ══════════════════════════════════════════════════════════════

def tune_by_intent(ip: str, intent_uri: str) -> bool:
    comp = re.search(r"component=([^;]+)", intent_uri)
    ct = re.search(r"i\.channel_type=(\d+)", intent_uri)
    gid = re.search(r"S\.group_id=([^;]+)", intent_uri)
    uid = re.search(r"S\.unique_channel_id=([^;]+)", intent_uri)
    if not comp:
        return False
    cmd = ["shell", "am", "start", "-n", comp.group(1)]
    if ct:  cmd += ["--ei", "channel_type", ct.group(1)]
    if gid: cmd += ["--es", "group_id", gid.group(1)]
    if uid: cmd += ["--es", "unique_channel_id", uid.group(1)]
    code, _ = adb(ip, *cmd)
    return code == 0


def _tune_by_uid(ip: str, unique_id: str) -> bool:
    return tune_by_intent(
        ip,
        f"intent:#Intent;component={MOL3_PKG}/tv.formuler.mol3.deeplink.SchemeLinkActivity;"
        f"i.channel_type=5;S.group_id=32768_0_0;S.unique_channel_id={unique_id};end"
    )


def cmd_tune(ip: str, query: str):
    # Try full channel cache first
    if FULL_CHANNELS_CACHE.exists():
        with open(FULL_CHANNELS_CACHE) as f:
            full = json.load(f)
        # Try exact channel number
        if query.isdigit():
            for ch in full:
                if ch.get("number") == query:
                    info(f"Tuning to: {ch['title']} (#{query})")
                    _notify("Formuler Remote", f"Tuning: {ch['title']}")
                    if ch.get("unique_id"):
                        _tune_by_uid(ip, ch["unique_id"])
                    return
        # Try name match in full cache
        terms = query.lower().split()
        full_matches = [c for c in full if all(t in c["title"].lower() for t in terms)]
        if len(full_matches) == 1 or (full_matches and all(m["title"] == full_matches[0]["title"] for m in full_matches)):
            ch = full_matches[0]
            info(f"Tuning to: {ch['title']}")
            _notify("Formuler Remote", f"Tuning: {ch['title']}")
            if ch.get("unique_id"):
                _tune_by_uid(ip, ch["unique_id"])
            return
        if full_matches:
            _show_tune_choices(ip, full_matches, is_full=True)
            return

    # Fallback to favorites/history cache
    channels = get_channels(ip)
    terms = query.lower().split()
    matches = [c for c in channels if all(t in c["title"].lower() for t in terms)]
    live = [m for m in matches if m["category"] in ("Favorites", "Live History")]
    if live:
        matches = live

    if not matches:
        results = search_provider(ip, query)
        if results:
            r = results[0]
            info(f"Tuning to: {r['title']}")
            _notify("Formuler Remote", f"Tuning: {r['title']}")
            if r.get("unique_id"):
                _tune_by_uid(ip, r["unique_id"])
                return
            error("No unique ID found")
        else:
            error(f"No channel matching '{query}'")
        return

    if len(matches) == 1 or all(m["title"] == matches[0]["title"] for m in matches):
        ch = matches[0]
        info(f"Tuning to: {ch['title']}")
        _notify("Formuler Remote", f"Tuning: {ch['title']}")
        if ch.get("intent"):
            tune_by_intent(ip, ch["intent"])
        return

    _show_tune_choices(ip, matches, is_full=False)


def _show_tune_choices(ip: str, matches: list[dict], is_full: bool):
    if JSON_MODE:
        output(matches[:15])
        return
    print(f"Found {len(matches)} matches:")
    for i, ch in enumerate(matches[:15]):
        marker = f"{_C.BOLD}>> " if i == 0 else "   "
        cat = f" [{ch.get('category', '')}]" if ch.get("category") else ""
        num = f" #{ch['number']}" if ch.get("number") else ""
        print(f"  {marker}{i + 1}. {ch['title']}{num}{_C.DIM}{cat}{_C.RESET}")
    try:
        choice = input(f"Select [1-{min(len(matches), 15)}] or Enter for #1: ").strip()
    except (EOFError, KeyboardInterrupt):
        return
    idx = int(choice) - 1 if choice.isdigit() else 0
    if 0 <= idx < len(matches):
        ch = matches[idx]
        info(f"Tuning to: {ch['title']}")
        _notify("Formuler Remote", f"Tuning: {ch['title']}")
        if is_full and ch.get("unique_id"):
            _tune_by_uid(ip, ch["unique_id"])
        elif ch.get("intent"):
            tune_by_intent(ip, ch["intent"])


def cmd_search(ip: str, query: str):
    channels = get_channels(ip)
    terms = query.lower().split()
    cached = [c for c in channels if all(t in c["title"].lower() for t in terms)]
    device = search_provider(ip, query)

    if JSON_MODE:
        output({"favorites_history": cached[:20], "live_channels": device})
        return

    if cached:
        print(f"\n  {_C.CYAN}Favorites/history{_C.RESET} ({len(cached)} matches):")
        for ch in cached[:20]:
            print(f"    {_C.DIM}[{ch['category']:<18}]{_C.RESET} {ch['title']}")
    if device:
        print(f"\n  {_C.CYAN}Full channel list{_C.RESET} ({len(device)} matches):")
        for r in device:
            num = f"{r['number']:>4}. " if r.get("number") else "      "
            print(f"    {num}{r['title']}")
    if not cached and not device:
        warn("  No results found.")


def cmd_list(ip: str, filter_text: str = ""):
    channels = get_channels(ip)
    filtered = channels
    if filter_text:
        terms = filter_text.lower().split()
        filtered = [c for c in filtered if all(t in c["title"].lower() for t in terms)]

    if JSON_MODE:
        output(filtered or [])
        return

    if not filtered:
        warn("No matches. Searching device...")
        for r in search_provider(ip, filter_text):
            num = f"{r['number']:>4}. " if r.get("number") else "      "
            print(f"  {num}{r['title']}")
        return
    for ch in filtered:
        print(f"  {_C.DIM}[{ch['category']:<18}]{_C.RESET} {ch['title']}")


def cmd_list_all(ip: str, filter_text: str = ""):
    channels = get_full_channels(ip)
    if filter_text:
        terms = filter_text.lower().split()
        channels = [c for c in channels if all(t in c["title"].lower() for t in terms)]

    if JSON_MODE:
        output(channels)
        return

    for ch in channels:
        num = f"{ch['number']:>4}. " if ch.get("number") else "      "
        print(f"  {num}{ch['title']}")
    print(f"\n  {_C.DIM}Total: {len(channels)} channels{_C.RESET}")


def cmd_channel_info(ip: str, number: str):
    ch = channel_by_number(ip, number)
    if not ch:
        error(f"Channel #{number} not found. Run 'refresh-all' to build the full database.")
        return
    if JSON_MODE:
        output(ch)
        return
    print(f"  {_C.BOLD}#{ch.get('number', '?')} {ch['title']}{_C.RESET}")
    if ch.get("unique_id"):
        print(f"  Unique ID: {ch['unique_id']}")
    if ch.get("logo"):
        print(f"  Logo: {ch['logo']}")


def cmd_categories(ip: str):
    counts: dict[str, int] = {}
    for ch in get_channels(ip):
        counts[ch["category"]] = counts.get(ch["category"], 0) + 1

    if JSON_MODE:
        output(counts)
        return

    for cat, n in sorted(counts.items()):
        print(f"  {_C.CYAN}{cat}{_C.RESET}: {n}")


# ══════════════════════════════════════════════════════════════
#  VOD / SERIES BROWSING (Phase 9)
# ══════════════════════════════════════════════════════════════

def cmd_browse(ip: str, section: str):
    go_to_section(ip, section)
    info(f"Browsing {section}. Use arrow keys to navigate, 'back' to return.")


def cmd_episodes(ip: str, query: str):
    do_search(ip, query, section="series")
    select_first_result(ip)
    keys(ip, "right", "right", "right", delay=0.2)
    wait(0.2)
    key(ip, "left")
    wait(0.2)
    key(ip, "ok")
    wait(2)
    screenshot(ip, f"/tmp/formuler-episodes.png")
    info(f"Episode browser open for '{query}'. Screenshot saved to /tmp/formuler-episodes.png")
    print("Navigate with arrow keys. 'back' to return.")


def cmd_resume(ip: str, content_type: str = "vod"):
    channels = get_channels(ip, force_refresh=True)
    history_cat = {"vod": "VOD History", "series": "Series History", "live": "Live History"}
    cat_name = history_cat.get(content_type, "")
    hist = [c for c in channels if c["category"] == cat_name]
    if not hist:
        error(f"No {content_type} history found.")
        return

    last = hist[0]
    if JSON_MODE:
        output(last)
        return

    info(f"Resuming: {last['title']}")
    _notify("Formuler Remote", f"Resuming: {last['title']}")

    if content_type == "live" and last.get("intent"):
        tune_by_intent(ip, last["intent"])
    else:
        do_search(ip, last["title"], section=content_type)
        select_first_result(ip)
        key(ip, "ok")  # Reprendre / Regarder


def cmd_info(ip: str, query: str, content_type: str = ""):
    channels = get_channels(ip)
    terms = query.lower().split()
    matches = [c for c in channels if all(t in c["title"].lower() for t in terms)]
    if content_type:
        cat_filter = {"vod": ("VOD History", "VOD Favorites"),
                      "series": ("Series History", "Series Favorites"),
                      "live": ("Favorites", "Live History")}
        allowed = cat_filter.get(content_type, ())
        if allowed:
            filtered = [m for m in matches if m["category"] in allowed]
            if filtered:
                matches = filtered

    if not matches:
        error(f"No match for '{query}' in local database.")
        return

    if JSON_MODE:
        output(matches[:10])
        return

    for m in matches[:5]:
        print(f"\n  {_C.BOLD}{m['title']}{_C.RESET}")
        print(f"  Category: {_C.CYAN}{m['category']}{_C.RESET}")
        if m.get("description"):
            print(f"  {m['description']}")
        if m.get("logo"):
            print(f"  {_C.DIM}Logo: {m['logo']}{_C.RESET}")


# ══════════════════════════════════════════════════════════════
#  EPG (Phase 8)
# ══════════════════════════════════════════════════════════════

def cmd_epg(ip: str, channel: str = ""):
    if channel:
        cmd_tune(ip, channel)
        wait(3)
    key(ip, "info")
    wait(1)
    screenshot(ip, "/tmp/formuler-epg.png")
    info("EPG info screenshot saved to /tmp/formuler-epg.png")
    key(ip, "info")  # dismiss


def cmd_guide(ip: str):
    ensure_mytv(ip)
    key(ip, "guide")
    wait(2)
    screenshot(ip, "/tmp/formuler-guide.png")
    info("EPG guide screenshot saved to /tmp/formuler-guide.png")


def cmd_search_epg(ip: str, query: str):
    open_search(ip, "live")
    text_input(ip, query)
    wait(0.5)
    key(ip, "ok")
    wait(2)
    # Navigate to "Programme TV" tab (second tab)
    key(ip, "right")
    wait(0.5)
    key(ip, "ok")
    wait(1)
    info(f"Showing EPG results for '{query}'. Navigate with arrows.")


def cmd_now_playing(ip: str):
    """Try to capture what's currently playing from logcat."""
    adb(ip, "shell", "logcat", "-c")
    key(ip, "info")
    wait(2)
    code, out = adb(ip, "shell", "logcat", "-d", "-s", "FormulerExo:*", "MOL-App:*", timeout=10)
    key(ip, "info")  # dismiss

    lines = [l for l in out.splitlines() if l.strip() and not l.startswith("-----")]
    if JSON_MODE:
        output({"logcat_lines": lines[:50]})
    elif lines:
        info("Recent player/app log entries:")
        for l in lines[:20]:
            print(f"  {_C.DIM}{l}{_C.RESET}")
    else:
        warn("No player log entries found.")


# ══════════════════════════════════════════════════════════════
#  MACROS (Phase 10)
# ══════════════════════════════════════════════════════════════

def get_macros() -> dict[str, str]:
    return CONFIG.get("macros", {})


def run_macro(ip: str, name: str):
    macros = get_macros()
    if name not in macros:
        error(f"Unknown macro: {name}")
        if macros:
            print(f"Available: {', '.join(sorted(macros.keys()))}")
        else:
            warn("No macros defined. Add [macros] section to config file.")
        return
    info(f"Running macro: {name}")
    for step in macros[name].split(";"):
        step = step.strip()
        if not step:
            continue
        if step.startswith("wait "):
            try:
                wait(float(step.split()[1]))
            except (ValueError, IndexError):
                wait(1)
        else:
            dispatch(ip, step)


def cmd_macros(ip: str):
    macros = get_macros()
    if JSON_MODE:
        output(macros)
        return
    if not macros:
        warn("No macros defined. Add [macros] section to your config file:")
        print(f"  {_C.DIM}{CONFIG_FILE}{_C.RESET}")
        print(f'  [macros]')
        print(f'  morning = "open mytv; wait 3; tune BFM TV"')
        return
    for name, cmds in sorted(macros.items()):
        print(f"  {_C.BOLD}{name}{_C.RESET}: {_C.DIM}{cmds}{_C.RESET}")


# ══════════════════════════════════════════════════════════════
#  TIMED ACTIONS (Phase 10)
# ══════════════════════════════════════════════════════════════

_timers: list[dict] = []  # {"timer": Timer, "time": str, "command": str}


def cmd_at(ip: str, time_str: str, command: str):
    try:
        h, m = map(int, time_str.split(":"))
    except ValueError:
        error("Time format: HH:MM (e.g., 20:30)")
        return

    now = datetime.datetime.now()
    target = now.replace(hour=h, minute=m, second=0, microsecond=0)
    if target <= now:
        target += datetime.timedelta(days=1)
    delay = (target - now).total_seconds()

    def fire():
        print(f"\n{_C.YELLOW}[Timer]{_C.RESET} Executing: {command}")
        dispatch(ip, command)
        if not JSON_MODE:
            print(f"{_C.BLUE}remote>{_C.RESET} ", end="", flush=True)

    t = threading.Timer(delay, fire)
    t.daemon = True
    t.start()
    _timers.append({"timer": t, "time": target.strftime("%H:%M"), "command": command})
    info(f"Scheduled '{command}' at {target.strftime('%H:%M')} ({delay / 60:.0f}min from now)")


def cmd_timers():
    active = [t for t in _timers if t["timer"].is_alive()]
    if JSON_MODE:
        output([{"time": t["time"], "command": t["command"]} for t in active])
        return
    if not active:
        warn("No pending timers.")
        return
    for i, t in enumerate(active):
        print(f"  {i + 1}. {_C.BOLD}{t['time']}{_C.RESET} → {t['command']}")


def cmd_cancel_timer(index: int):
    active = [t for t in _timers if t["timer"].is_alive()]
    if 0 <= index < len(active):
        active[index]["timer"].cancel()
        info(f"Cancelled: {active[index]['command']}")
    else:
        error(f"Invalid timer index. Use 'timers' to see list.")


# ══════════════════════════════════════════════════════════════
#  ADVANCED REMOTE (Phase 10)
# ══════════════════════════════════════════════════════════════

def cmd_repeat(ip: str, key_name: str, count: int, delay_ms: float = 250):
    delay_s = delay_ms / 1000
    for i in range(count):
        key(ip, key_name)
        if i < count - 1:
            time.sleep(delay_s)
    info(f"Pressed {key_name} x{count}")


def cmd_cec(ip: str, action: str):
    action = action.lower()
    if action == "on":
        key(ip, "wakeup")
        info("CEC: Wake up / Power on")
    elif action == "off":
        key(ip, "sleep")
        info("CEC: Sleep / Power off")
    elif action == "standby":
        key(ip, "power")
        info("CEC: Standby toggle")
    else:
        error(f"Unknown CEC action: {action}. Use: on, off, standby")


def cmd_record_screen(ip: str, duration: int = 30, path: str = "/tmp/formuler-recording.mp4"):
    remote = "/sdcard/recording.mp4"
    info(f"Recording for {duration}s... (video surfaces will be green due to DRM)")
    try:
        adb(ip, "shell", "screenrecord", "--time-limit", str(duration), remote,
            timeout=duration + 10)
    except Exception:
        pass
    adb(ip, "pull", remote, path, timeout=30)
    adb(ip, "shell", "rm", remote)
    info(f"Recording saved to {path}")


# ══════════════════════════════════════════════════════════════
#  MISC
# ══════════════════════════════════════════════════════════════

def go_to_channel_number(ip: str, number: str):
    for d in number:
        key(ip, d)
    key(ip, "ok")


def screenshot(ip: str, path: str = "/tmp/formuler-screenshot.png"):
    remote = "/sdcard/screenshot.png"
    adb(ip, "shell", "screencap", "-p", remote)
    run_adb("-s", tgt(ip), "pull", remote, path)
    adb(ip, "shell", "rm", remote)
    info(f"Screenshot saved to {path}")


def cmd_status(ip: str):
    code, model = adb(ip, "shell", "getprop", "ro.product.model")
    _, version = adb(ip, "shell", "getprop", "ro.build.version.release")
    _, uptime = adb(ip, "shell", "uptime")
    _, fg = adb(ip, "shell", "dumpsys", "activity", "recents", timeout=5)

    top_app = "unknown"
    for line in fg.splitlines():
        if "Recent #0" in line or "topActivity" in line:
            m = re.search(r"com\.\S+|tv\.\S+", line)
            if m:
                top_app = m.group(0).split("/")[0]
            break

    data = {
        "model": model.strip() if code == 0 else "unknown",
        "android": version.strip(),
        "uptime": uptime.strip(),
        "foreground_app": top_app,
        "ip": ip,
    }
    if JSON_MODE:
        output(data)
    else:
        print(f"  {_C.BOLD}Model{_C.RESET}: {data['model']}")
        print(f"  {_C.BOLD}Android{_C.RESET}: {data['android']}")
        print(f"  {_C.BOLD}Uptime{_C.RESET}: {data['uptime']}")
        print(f"  {_C.BOLD}Foreground{_C.RESET}: {data['foreground_app']}")
        print(f"  {_C.BOLD}IP{_C.RESET}: {data['ip']}:{ADB_PORT}")


# ══════════════════════════════════════════════════════════════
#  HELP
# ══════════════════════════════════════════════════════════════

HELP_TEXT = f"""
{_C.BOLD}Commands:{_C.RESET}
  {_C.CYAN}NAVIGATION{_C.RESET}       up, down, left, right, ok, back, home, menu
  {_C.CYAN}PLAYBACK{_C.RESET}         play, pause, play-pause, stop, rewind, fast-forward
  {_C.CYAN}CHANNELS{_C.RESET}         channel-up, channel-down, channel <number>
  {_C.CYAN}VOLUME{_C.RESET}           volume-up, volume-down, mute

  {_C.CYAN}SECTIONS{_C.RESET}
    section <name>                  switch section (live/vod/series/radio/recordings)
    browse <section>                open section for manual browsing

  {_C.CYAN}LIVE TV{_C.RESET}
    tune <name|number>              tune by name or channel number
    search <query>                  search local DB + device provider
    list [filter]                   list channels (e.g. 'list BE')
    list-all [filter]               list all enumerated channels
    channel-info <number>           show channel details
    categories                      show category counts

  {_C.CYAN}VOD (Movies){_C.RESET}
    search-vod <query>              search movies on device UI
    play-movie <query>              search & play first match
    stop-vod                        stop with confirmation (Up + OK)

  {_C.CYAN}SERIES (TV Shows){_C.RESET}
    search-series <query>           search series on device UI
    play-series <query> [S] [E]     search & play episode (default S1E1)
    episodes <query>                open episode browser + screenshot
    stop-vod                        stop with confirmation

  {_C.CYAN}BROWSING{_C.RESET}
    resume [vod|series|live]        resume last watched
    info <query>                    show details from local database

  {_C.CYAN}EPG{_C.RESET}
    epg [channel]                   show EPG info overlay + screenshot
    guide                           open full EPG guide + screenshot
    search-epg <query>              search EPG program listings
    now-playing                     capture player log entries

  {_C.CYAN}FAVORITES{_C.RESET}
    star                            toggle star on current detail page
    star-vod <query>                find movie & toggle star
    star-series <query>             find series & toggle star

  {_C.CYAN}MACROS & TIMERS{_C.RESET}
    macro <name>                    run a saved macro
    macros                          list available macros
    at <HH:MM> <command>            schedule a command
    timers                          list pending timers
    cancel-timer <index>            cancel a timer

  {_C.CYAN}ADVANCED{_C.RESET}
    repeat <key> <count>            press key N times
    cec <on|off|standby>            TV power via CEC
    record [duration] [path]        screen record (default 30s)

  {_C.CYAN}GENERAL{_C.RESET}
    type <text>                     type text on device
    open <app>                      launch app (youtube/netflix/prime/mytv/...)
    apps                            list installed apps
    screenshot [path]               capture screen
    status                          show device info
    reboot                          reboot device
    refresh                         reload favorites/history cache
    refresh-all                     rebuild full channel database
    keys                            list all key names
    help                            show this help
    quit / exit                     disconnect
"""


# ══════════════════════════════════════════════════════════════
#  UNIFIED DISPATCH
# ══════════════════════════════════════════════════════════════

def _parse_series_args(args: list[str]) -> tuple[str, int, int]:
    season, episode = 1, 1
    query_parts = list(args)
    if len(query_parts) >= 2 and query_parts[-1].isdigit() and query_parts[-2].isdigit():
        episode = int(query_parts.pop())
        season = int(query_parts.pop())
    elif len(query_parts) >= 1 and query_parts[-1].isdigit():
        season = int(query_parts.pop())
    return " ".join(query_parts), season, episode


def dispatch(ip: str, raw: str) -> bool:
    """Execute a single command. Returns False to quit REPL."""
    parts = raw.strip().split()
    if not parts:
        return True
    cmd = parts[0].lower()
    args = parts[1:]
    atxt = " ".join(args)

    # Quit
    if cmd in ("quit", "exit", "q"):
        return False

    # Help
    elif cmd == "help":
        print(HELP_TEXT)
    elif cmd == "keys":
        if JSON_MODE:
            output(sorted(KEYS.keys()))
        else:
            print(", ".join(sorted(KEYS.keys())))

    # Sections
    elif cmd == "section" and atxt:
        go_to_section(ip, atxt)
    elif cmd == "browse" and atxt:
        cmd_browse(ip, atxt)

    # Live TV
    elif cmd == "channel" and args:
        go_to_channel_number(ip, args[0])
    elif cmd == "tune" and atxt:
        cmd_tune(ip, atxt)
    elif cmd == "search" and atxt:
        cmd_search(ip, atxt)
    elif cmd == "list":
        cmd_list(ip, atxt)
    elif cmd == "list-all":
        cmd_list_all(ip, atxt)
    elif cmd == "channel-info" and args:
        cmd_channel_info(ip, args[0])
    elif cmd == "categories":
        cmd_categories(ip)
    elif cmd == "refresh":
        get_channels(ip, force_refresh=True)
    elif cmd == "refresh-all":
        get_full_channels(ip, force_refresh=True)

    # VOD
    elif cmd == "search-vod" and atxt:
        do_search(ip, atxt, section="vod")
    elif cmd == "play-movie" and atxt:
        play_movie(ip, atxt)
    elif cmd == "stop-vod":
        stop_playback(ip)

    # Series
    elif cmd == "search-series" and atxt:
        do_search(ip, atxt, section="series")
    elif cmd == "play-series" and args:
        q, s, e = _parse_series_args(args)
        play_series(ip, q, s, e)
    elif cmd == "episodes" and atxt:
        cmd_episodes(ip, atxt)

    # Browsing
    elif cmd == "resume":
        cmd_resume(ip, args[0] if args else "vod")
    elif cmd == "info" and atxt:
        cmd_info(ip, atxt)

    # EPG
    elif cmd == "epg":
        cmd_epg(ip, atxt)
    elif cmd == "guide":
        cmd_guide(ip)
    elif cmd == "search-epg" and atxt:
        cmd_search_epg(ip, atxt)
    elif cmd == "now-playing":
        cmd_now_playing(ip)

    # Favorites
    elif cmd == "star" and not args:
        toggle_star(ip)
    elif cmd == "star-vod" and atxt:
        star_search(ip, atxt, "vod")
    elif cmd == "star-series" and atxt:
        star_search(ip, atxt, "series")

    # Macros & Timers
    elif cmd == "macro" and atxt:
        run_macro(ip, atxt)
    elif cmd == "macros":
        cmd_macros(ip)
    elif cmd == "at" and len(args) >= 2:
        cmd_at(ip, args[0], " ".join(args[1:]))
    elif cmd == "timers":
        cmd_timers()
    elif cmd == "cancel-timer" and args and args[0].isdigit():
        cmd_cancel_timer(int(args[0]) - 1)

    # Advanced
    elif cmd == "repeat" and len(args) >= 2 and args[1].isdigit():
        cmd_repeat(ip, args[0], int(args[1]))
    elif cmd == "cec" and args:
        cmd_cec(ip, args[0])
    elif cmd == "record":
        dur = int(args[0]) if args and args[0].isdigit() else 30
        path = args[1] if len(args) > 1 else "/tmp/formuler-recording.mp4"
        cmd_record_screen(ip, dur, path)

    # Text / direct key
    elif cmd == "type" and args:
        text_input(ip, " ".join(args))
    elif cmd == "key" and args:
        key(ip, args[0])

    # Apps
    elif cmd == "open" and args:
        open_app(ip, KNOWN_APPS.get(args[0].lower(), args[0]))
    elif cmd == "apps":
        list_apps(ip)

    # Misc
    elif cmd == "screenshot":
        screenshot(ip, args[0] if args else "/tmp/formuler-screenshot.png")
    elif cmd == "status":
        cmd_status(ip)
    elif cmd == "reboot":
        try:
            if input("Reboot device? [y/N] ").strip().lower() == "y":
                adb(ip, "shell", "reboot")
                info("Rebooting...")
        except (EOFError, KeyboardInterrupt):
            pass

    # Direct key (any known key name)
    elif cmd in KEYS:
        key(ip, cmd)

    # Macro shortcut (check if command matches a macro name)
    elif cmd in get_macros():
        run_macro(ip, cmd)

    else:
        error(f"Unknown: {cmd}. Type 'help'.")

    return True


# ══════════════════════════════════════════════════════════════
#  TAB COMPLETION
# ══════════════════════════════════════════════════════════════

def _make_completer(ip: str):
    commands = [
        "tune", "search", "list", "list-all", "channel-info", "categories",
        "section", "browse", "channel",
        "search-vod", "play-movie", "stop-vod",
        "search-series", "play-series", "episodes",
        "resume", "info",
        "epg", "guide", "search-epg", "now-playing",
        "star", "star-vod", "star-series",
        "macro", "macros", "at", "timers", "cancel-timer",
        "repeat", "cec", "record",
        "type", "key", "open", "apps",
        "screenshot", "status", "reboot", "refresh", "refresh-all",
        "keys", "help", "quit", "exit",
    ]
    commands += list(KEYS.keys())
    commands += list(get_macros().keys())
    all_commands = sorted(set(commands))

    section_names = sorted(set(MOL3_SECTIONS.keys()))
    app_names = sorted(KNOWN_APPS.keys())

    # Load channel names for tune completion
    channel_names: list[str] = []
    if CHANNELS_CACHE.exists():
        try:
            with open(CHANNELS_CACHE) as f:
                channel_names = list(set(c["title"] for c in json.load(f)))
        except (json.JSONDecodeError, KeyError):
            pass

    def completer(text: str, state: int):
        line = readline.get_line_buffer().lstrip()
        parts = line.split()
        text_lower = text.lower()

        if len(parts) <= 1 and not line.endswith(" "):
            options = [c for c in all_commands if c.startswith(text_lower)]
        elif parts[0] in ("tune", "search"):
            options = [n for n in channel_names if n.lower().startswith(text_lower)]
        elif parts[0] == "open":
            options = [a for a in app_names if a.startswith(text_lower)]
        elif parts[0] in ("section", "browse"):
            options = [s for s in section_names if s.startswith(text_lower)]
        elif parts[0] == "macro":
            options = [m for m in get_macros() if m.startswith(text_lower)]
        elif parts[0] == "cec":
            options = [a for a in ("on", "off", "standby") if a.startswith(text_lower)]
        elif parts[0] == "resume":
            options = [t for t in ("vod", "series", "live") if t.startswith(text_lower)]
        elif parts[0] in ("key", "repeat"):
            options = [k for k in KEYS if k.startswith(text_lower)]
        else:
            options = []

        return options[state] if state < len(options) else None

    return completer


# ══════════════════════════════════════════════════════════════
#  INTERACTIVE REPL
# ══════════════════════════════════════════════════════════════

def interactive(ip: str):
    channels = get_channels(ip)
    if channels:
        print(f"Channel database: {_C.BOLD}{len(channels)}{_C.RESET} entries")

    # Setup tab completion
    readline.set_completer(_make_completer(ip))
    readline.parse_and_bind("tab: complete")
    readline.set_completer_delims(" ")

    # Setup history file
    history_file = CACHE_DIR / "history"
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        readline.read_history_file(history_file)
    except FileNotFoundError:
        pass

    print(HELP_TEXT)

    prompt = f"{_C.BLUE}remote>{_C.RESET} "
    while True:
        try:
            raw = input(prompt).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not raw:
            continue
        if not dispatch(ip, raw):
            break

    try:
        readline.write_history_file(history_file)
    except OSError:
        pass

    # Cancel pending timers
    for t in _timers:
        t["timer"].cancel()

    run_adb("disconnect", tgt(ip))
    info("Disconnected.")


# ══════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════

def main():
    global JSON_MODE

    if not shutil.which("adb"):
        print("Error: adb not found. Install with: sudo pacman -S android-tools")
        sys.exit(1)

    # Parse --json flag
    argv = [a for a in sys.argv[1:] if a != "--json"]
    if len(argv) != len(sys.argv[1:]):
        JSON_MODE = True

    ip = DEFAULT_IP
    off = 0
    if argv and re.match(r"\d+\.\d+\.\d+\.\d+", argv[0]):
        ip = argv[0]
        off = 1

    if not connect(ip, quiet=JSON_MODE):
        sys.exit(1)

    remaining = argv[off:]
    if not remaining:
        interactive(ip)
        return

    cmd_str = " ".join(remaining)
    dispatch(ip, cmd_str)
    run_adb("disconnect", tgt(ip))


if __name__ == "__main__":
    main()
