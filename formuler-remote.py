#!/usr/bin/env python3
"""
Formuler IPTV Remote Control via ADB

Usage:
  ./formuler-remote.py [flags] [device_ip_or_hostname] [command] [args...]

Flags:
  --json     Output structured JSON ({"ok": bool, "data"|"error": ...})
  --yes      Skip confirmation prompts (for automation)
  --first    Auto-select first match instead of prompting

Device IP resolution (first match wins):
  1. CLI argument:        ./formuler-remote.py 192.168.0.100 tune TF1
  2. Environment variable: FORMULER_IP=192.168.0.100
  3. .env file:           FORMULER_IP=192.168.0.100  (in ./ or ~/.config/formuler-remote/)
  4. Config file:         [device] ip = "192.168.0.100"

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
  ./formuler-remote.py --json --first tune TF1           # agent-friendly: JSON + auto-select
  ./formuler-remote.py --json commands                   # list all commands as JSON schema
  ./formuler-remote.py --yes reboot                      # skip confirmation prompts
  ./formuler-remote.py macro morning                     # run a saved macro

Prerequisites:
  1. Install ADB: sudo pacman -S android-tools
  2. Enable ADB on Formuler: Settings > Developer Options > ADB Debugging > ON
  3. Find device IP: Settings > Network (on the Formuler)
"""

__version__ = "1.1.0"

import datetime
import json
import os
import re
import subprocess
import sys
import shutil
import threading
import time
import unicodedata
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


def _load_env(path: Path) -> dict[str, str]:
    """Load KEY=VALUE pairs from a .env file."""
    env: dict[str, str] = {}
    if not path.exists():
        return env
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            k, _, v = line.partition("=")
            env[k.strip()] = v.strip().strip("'\"")
    return env


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


# Load .env from project dir or config dir
_dotenv = _load_env(Path(".env"))
_dotenv.update(_load_env(CONFIG_DIR / ".env"))

CONFIG = _load_config()

# ──────────────────────── Constants ────────────────────────

ADB_PORT = CONFIG.get("device", {}).get("port", 5555)
# IP resolution order: FORMULER_IP env var > .env file > config file
DEFAULT_IP = (
    os.environ.get("FORMULER_IP")
    or _dotenv.get("FORMULER_IP")
    or CONFIG.get("device", {}).get("ip", "")
)
MOL3_PKG = "tv.formuler.mol3.real"
CACHE_DIR = Path.home() / ".cache" / "formuler-remote"
CHANNELS_CACHE = CACHE_DIR / "channels.json"
FULL_CHANNELS_CACHE = CACHE_DIR / "full_channels.json"
TUNE_HISTORY_FILE = CACHE_DIR / "tune_history.json"

JSON_MODE = False
AUTO_YES = False
AUTO_FIRST = False
VERBOSE = False
DRY_RUN = False
ADB_TIMEOUT = 10

# Configurable timing (overridable via [timing] in config)
_timing = CONFIG.get("timing", {})
NAV_DELAY = float(_timing.get("nav_delay", 0.25))
LOAD_DELAY = float(_timing.get("load_delay", 2.0))
SEARCH_DELAY = float(_timing.get("search_delay", 1.5))

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


# ──────────────────────── Fuzzy Matching ────────────────────────


def _normalize(s: str) -> str:
    """Strip accents, lowercase, collapse whitespace."""
    nfkd = unicodedata.normalize("NFKD", s)
    stripped = "".join(c for c in nfkd if unicodedata.category(c) != "Mn")
    return " ".join(stripped.lower().split())


def _fuzzy_match(query: str, candidates: list[dict], key: str = "title") -> list[dict]:
    """Match query against candidates with tiered matching.

    Priority: exact > starts-with > all-tokens-contained > spaces-removed containment.
    Within each tier, shorter titles are preferred (e.g., "TF1" before "TF1 SERIES HD").
    """
    nq = _normalize(query)
    nq_nospace = nq.replace(" ", "")
    tokens = nq.split()

    exact, starts, contains, spaceless = [], [], [], []
    for item in candidates:
        val = item.get(key, "")
        nv = _normalize(val)
        nv_nospace = nv.replace(" ", "")
        if nv == nq:
            exact.append(item)
        elif nv.startswith(nq):
            starts.append(item)
        elif all(t in nv for t in tokens):
            contains.append(item)
        elif nq_nospace in nv_nospace:
            spaceless.append(item)

    # Within each tier, prefer shorter titles (more specific matches first)
    _by_len = lambda items: sorted(items, key=lambda x: len(x.get(key, "")))
    return _by_len(exact) + _by_len(starts) + _by_len(contains) + _by_len(spaceless)


# ──────────────────────── Command Registry ────────────────────────
# Machine-readable command schema for AI agents and scripting

COMMANDS = {
    # Navigation
    "up": {"args": "", "desc": "Navigate up"},
    "down": {"args": "", "desc": "Navigate down"},
    "left": {"args": "", "desc": "Navigate left"},
    "right": {"args": "", "desc": "Navigate right"},
    "ok": {"args": "", "desc": "Confirm / Enter"},
    "back": {"args": "", "desc": "Go back"},
    "home": {"args": "", "desc": "Go to home screen"},
    "menu": {"args": "", "desc": "Open menu"},
    # Playback
    "play": {"args": "", "desc": "Start playback"},
    "pause": {"args": "", "desc": "Pause playback"},
    "play-pause": {"args": "", "desc": "Toggle play/pause"},
    "stop": {"args": "", "desc": "Stop playback"},
    "rewind": {"args": "", "desc": "Rewind"},
    "fast-forward": {"args": "", "desc": "Fast forward"},
    # Volume
    "volume-up": {"args": "", "desc": "Volume up"},
    "volume-down": {"args": "", "desc": "Volume down"},
    "mute": {"args": "", "desc": "Toggle mute"},
    # Channels
    "channel-up": {"args": "", "desc": "Next channel"},
    "channel-down": {"args": "", "desc": "Previous channel"},
    "channel": {"args": "<number>", "desc": "Go to channel number using digit keys"},
    # Sections
    "section": {"args": "<name>", "desc": "Switch section (live/vod/series/radio/recordings/settings)"},
    "browse": {"args": "<section>", "desc": "Open section for manual browsing"},
    # Live TV
    "tune": {"args": "<name|number>", "desc": "Tune channel by name or number. Auto-selects first match with --first"},
    "search": {"args": "<query>", "desc": "Search channels in local DB and device provider"},
    "list": {"args": "[filter]", "desc": "List channels from favorites/history cache"},
    "list-all": {"args": "[filter]", "desc": "List all enumerated channels (requires refresh-all first)"},
    "channel-info": {"args": "<number>", "desc": "Show details for a channel number"},
    "last": {"args": "", "desc": "Retune the last tuned channel"},
    "prev": {"args": "", "desc": "Swap to previous channel (recall)"},
    "tune-history": {"args": "[count]", "desc": "Show recent tune history with timestamps"},
    "categories": {"args": "", "desc": "Show content category counts"},
    "refresh": {"args": "", "desc": "Reload favorites/history cache from device"},
    "refresh-all": {"args": "", "desc": "Rebuild full channel database (slow, scans A-Z)"},
    # VOD
    "search-vod": {"args": "<query>", "desc": "Search movies on device UI"},
    "play-movie": {"args": "<query>", "desc": "Search and play first matching movie"},
    "stop-vod": {"args": "", "desc": "Stop VOD playback with confirmation dialog"},
    # Series
    "search-series": {"args": "<query>", "desc": "Search series on device UI"},
    "play-series": {"args": "<query> [season] [episode]", "desc": "Play series episode (default S1E1)"},
    "episodes": {"args": "<query>", "desc": "Open episode browser and take screenshot"},
    # Browsing
    "resume": {"args": "[vod|series|live]", "desc": "Resume last watched content from history"},
    "info": {"args": "<query>", "desc": "Show content details from local database"},
    # EPG
    "epg": {"args": "[channel]", "desc": "Show EPG info overlay and take screenshot"},
    "guide": {"args": "", "desc": "Open full EPG guide and take screenshot"},
    "search-epg": {"args": "<query>", "desc": "Search EPG program listings"},
    "now-playing": {"args": "", "desc": "Capture player log entries from logcat"},
    # Favorites
    "star": {"args": "", "desc": "Toggle star/favorite on current detail page"},
    "star-vod": {"args": "<query>", "desc": "Find movie and toggle star"},
    "star-series": {"args": "<query>", "desc": "Find series and toggle star"},
    # Macros & Timers
    "macro": {"args": "<name>", "desc": "Run a saved macro from config"},
    "macros": {"args": "", "desc": "List available macros"},
    "at": {"args": "<HH:MM> <command>", "desc": "Schedule a command at a specific time"},
    "timers": {"args": "", "desc": "List pending scheduled timers"},
    "cancel-timer": {"args": "<index>", "desc": "Cancel a pending timer by index"},
    "sleep-timer": {"args": "<minutes>", "desc": "Auto-off: stop playback + CEC standby after N minutes"},
    "sleep-at": {"args": "<HH:MM>", "desc": "Auto-off at specific time"},
    "sleep-cancel": {"args": "", "desc": "Cancel pending sleep timer"},
    # Advanced
    "repeat": {"args": "<key> <count>", "desc": "Press a key N times"},
    "cec": {"args": "<on|off|standby>", "desc": "TV power control via CEC pass-through"},
    "record": {"args": "[duration] [path]", "desc": "Screen record (default 30s)"},
    # General
    "type": {"args": "<text>", "desc": "Type text on device keyboard"},
    "key": {"args": "<keyname>", "desc": "Send a single key event"},
    "open": {"args": "<app>", "desc": "Launch app (youtube/netflix/prime/mytv/plex/kodi/vlc/disney/settings)"},
    "apps": {"args": "", "desc": "List installed third-party apps"},
    "screenshot": {"args": "[path]", "desc": "Capture screen to file (default /tmp/formuler-screenshot.png)"},
    "status": {"args": "", "desc": "Show device info (model, Android version, uptime, foreground app)"},
    "reboot": {"args": "", "desc": "Reboot device (requires --yes to skip confirmation)"},
    "export-m3u": {"args": "[path]", "desc": "Export channel lineup as M3U playlist (metadata only, no stream URLs)"},
    "wake": {"args": "", "desc": "CEC wakeup + launch MyTVOnline"},
    "power-off": {"args": "", "desc": "CEC sleep + disconnect"},
    "history": {"args": "[count]", "desc": "Show recent command history"},
    "watch": {"args": "[interval] [dir]", "desc": "Take screenshot every N seconds (default 5)"},
    "ping": {"args": "", "desc": "Check device connectivity (adb shell echo pong)"},
    "commands": {"args": "", "desc": "List all commands with args and descriptions (JSON schema)"},
    "keys": {"args": "", "desc": "List all remote key names"},
    "help": {"args": "", "desc": "Show help text"},
}


# ──────────────────────── Output Helpers ────────────────────────

_exit_code = 0


def _json_out(data: dict):
    print(json.dumps(data, ensure_ascii=False, indent=2))


def output(data, human_text: str = ""):
    if JSON_MODE:
        _json_out({"ok": True, "data": data})
    else:
        print(human_text or str(data))


def output_ok(msg: str = "", data=None):
    if JSON_MODE:
        _json_out({"ok": True, "message": msg, **({"data": data} if data is not None else {})})
    elif msg:
        print(f"{_C.GREEN}{msg}{_C.RESET}")


def output_err(msg: str, data=None):
    global _exit_code
    _exit_code = 1
    if JSON_MODE:
        _json_out({"ok": False, "error": msg, **({"data": data} if data is not None else {})})
    else:
        print(f"{_C.RED}{msg}{_C.RESET}")


def info(msg: str):
    if not JSON_MODE:
        print(f"{_C.GREEN}{msg}{_C.RESET}")


def warn(msg: str):
    if not JSON_MODE:
        print(f"{_C.YELLOW}{msg}{_C.RESET}")


def error(msg: str):
    global _exit_code
    _exit_code = 1
    if not JSON_MODE:
        print(f"{_C.RED}{msg}{_C.RESET}")
    else:
        _json_out({"ok": False, "error": msg})


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
    if DRY_RUN:
        print(f"[dry-run] adb {' '.join(args)}", file=sys.stderr)
        return 0, ""
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


def adb(ip: str, *args: str, timeout: int = 0) -> tuple[int, str]:
    """Run ADB command with auto-reconnect on connection loss."""
    if timeout == 0:
        timeout = ADB_TIMEOUT
    if VERBOSE:
        print(f"[debug] adb -s {tgt(ip)} {' '.join(args)}", file=sys.stderr)
    code, out = run_adb("-s", tgt(ip), *args, timeout=timeout)
    if code != 0 and ("error: device" in out.lower() or "not found" in out.lower()
                       or "offline" in out.lower()):
        warn("Connection lost. Reconnecting...")
        if connect(ip, quiet=True):
            code, out = run_adb("-s", tgt(ip), *args, timeout=timeout)
    if VERBOSE:
        print(f"[debug] exit={code}", file=sys.stderr)
    return code, out


_TRANSIENT_ERRORS = ("timeout", "device busy", "closed", "connection reset", "broken pipe")


def _adb_retry(ip: str, *args: str, timeout: int = 10, max_attempts: int = 3) -> tuple[int, str]:
    """Run ADB command with exponential backoff retry on transient errors."""
    delays = [0.5, 1.0, 2.0]
    for attempt in range(max_attempts):
        code, out = adb(ip, *args, timeout=timeout)
        if code == 0:
            return code, out
        out_lower = out.lower()
        if not any(err in out_lower for err in _TRANSIENT_ERRORS):
            return code, out  # non-transient error, don't retry
        if attempt < max_attempts - 1:
            delay = delays[min(attempt, len(delays) - 1)]
            warn(f"Transient error (attempt {attempt + 1}/{max_attempts}), retrying in {delay}s...")
            time.sleep(delay)
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
    code, out = adb(ip, "shell", "input", "keyevent", str(KEYS[name]))
    if code != 0:
        output_err(f"Key '{name}' failed: {out}")
        return False
    return True


def keys(ip: str, *names: str, delay: float = 0):
    if delay == 0:
        delay = NAV_DELAY
    for n in names:
        key(ip, n)
        time.sleep(delay)


def text_input(ip: str, t: str) -> bool:
    # Quote the text properly for the Android shell — %s is the space escape for ADB input
    escaped = t.replace(" ", "%s")
    code, _ = adb(ip, "shell", f"input text '{escaped}'")
    return code == 0


def ui_dump(ip: str) -> str:
    """Dump UI hierarchy and return XML string."""
    adb(ip, "shell", "uiautomator", "dump", "/sdcard/ui.xml", timeout=10)
    code, out = run_adb("-s", tgt(ip), "pull", "/sdcard/ui.xml", "/tmp/formuler-ui.xml")
    if code != 0:
        return ""
    try:
        return Path("/tmp/formuler-ui.xml").read_text()
    except OSError:
        return ""


def ui_focused_text(ip: str) -> list[str]:
    """Return text content of the currently focused UI element."""
    import xml.etree.ElementTree as ET
    xml_str = ui_dump(ip)
    if not xml_str:
        return []
    try:
        root = ET.fromstring(xml_str)
    except ET.ParseError:
        return []
    texts = []
    for node in root.iter("node"):
        if node.get("focused") == "true":
            for n in node.iter("node"):
                t = n.get("text", "")
                if t:
                    texts.append(t)
            break
    return texts


def ui_find_text(ip: str, target: str) -> bool:
    """Check if target text exists anywhere in the current UI."""
    import xml.etree.ElementTree as ET
    xml_str = ui_dump(ip)
    if not xml_str:
        return False
    try:
        root = ET.fromstring(xml_str)
    except ET.ParseError:
        return False
    target_lower = target.lower()
    for node in root.iter("node"):
        text = node.get("text", "")
        if target_lower in text.lower():
            return True
    return False


def ui_get_texts(ip: str) -> list[dict]:
    """Return all text elements with their resource IDs and positions."""
    import xml.etree.ElementTree as ET
    xml_str = ui_dump(ip)
    if not xml_str:
        return []
    try:
        root = ET.fromstring(xml_str)
    except ET.ParseError:
        return []
    results = []
    for node in root.iter("node"):
        text = node.get("text", "")
        if text:
            results.append({
                "text": text,
                "rid": node.get("resource-id", "").split("/")[-1],
                "focused": node.get("focused") == "true",
                "selected": node.get("selected") == "true",
                "bounds": node.get("bounds", ""),
            })
    return results


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
        wait(LOAD_DELAY * 1.5)


def open_app(ip: str, package: str):
    code, out = adb(ip, "shell", "monkey", "-p", package,
                    "-c", "android.intent.category.LAUNCHER", "1")
    if code != 0 or "No activities found" in out:
        output_err(f"Error launching {package}: {out}")
    else:
        output_ok(f"Launched {package}")


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
    wait(NAV_DELAY * 2)
    for _ in range(MOL3_SECTIONS[section]):
        key(ip, "down")
        wait(NAV_DELAY)
    key(ip, "ok")
    wait(LOAD_DELAY)
    output_ok(f"Switched to: {section}")
    return True


# ══════════════════════════════════════════════════════════════
#  IN-APP SEARCH
# ══════════════════════════════════════════════════════════════

def open_search(ip: str, section: str = "vod"):
    """Open the universal search screen from any section.

    The search icon is at the top-right of the content area.
    Navigation: go to section → right (into content) → up until search icon focused → ok.
    Verified via UI dump: search icon has resource-id 'dashboard_overview_option'.
    """
    go_to_section(ip, section)
    key(ip, "right")
    wait(NAV_DELAY)
    for _ in range(10):
        key(ip, "up")
        wait(NAV_DELAY * 0.6)
    key(ip, "ok")
    wait(SEARCH_DELAY)
    # Verify we landed on the search activity
    _wait_for_activity(ip, "UsActivity", timeout=5)


def _wait_for_activity(ip: str, name: str, timeout: float = 5) -> bool:
    """Wait for a specific activity to be in the foreground."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        code, out = adb(ip, "shell", "dumpsys", "activity", "activities", timeout=5)
        if code == 0 and name in out:
            return True
        time.sleep(0.5)
    return False


def _get_current_activity(ip: str) -> str:
    """Return the simple class name of the current foreground activity."""
    code, out = adb(ip, "shell", "dumpsys", "activity", "activities", timeout=5)
    if code != 0:
        return ""
    for line in out.splitlines():
        if "mResumedActivity" in line:
            # Extract: ...mol3.vod.ui.search.StreamSearchActivity t454
            m = re.search(r"/[\w.]+\.(\w+Activity)\b", line)
            return m.group(1) if m else ""
    return ""


def do_search(ip: str, query: str, section: str = "vod"):
    """Search for content using the universal search UI.

    Flow verified via ADB/uiautomator:
    1. Open search → lands on UsActivity with EditText focused
    2. Type query (spaces encoded as %s for ADB)
    3. Press Enter → results appear with category tabs
    """
    open_search(ip, section)
    text_input(ip, query)
    wait(NAV_DELAY * 2)
    key(ip, "ok")  # submit search
    wait(LOAD_DELAY)
    output_ok(f"Searched for '{query}' in {section}")


def select_first_result(ip: str):
    """Select the first search result.

    After searching, the UI shows category tabs (Chaînes TV, VOD, Séries TV, etc.)
    with one tab focused. Results are BELOW the tabs.
    Press down once to move from tabs to results, then ok to select.
    """
    # Move from tab bar down to first result
    key(ip, "down")
    wait(NAV_DELAY)
    # Verify we're on a result (not still on tabs) by checking focused text
    focused = ui_focused_text(ip)
    if focused and any("Chaînes" in t or "Programme" in t or "VOD" in t or
                        "Séries" in t or "Radios" in t or "Enregistrements" in t
                        for t in focused):
        # Still on tabs, press down again
        key(ip, "down")
        wait(NAV_DELAY)
    key(ip, "ok")
    wait(LOAD_DELAY)


# ══════════════════════════════════════════════════════════════
#  PLAYBACK CONTROL
# ══════════════════════════════════════════════════════════════

def stop_playback(ip: str):
    key(ip, "stop")
    wait(LOAD_DELAY * 0.5)
    key(ip, "up")
    wait(NAV_DELAY)
    key(ip, "ok")
    output_ok("Playback stopped.")


# ══════════════════════════════════════════════════════════════
#  PLAY MOVIE
# ══════════════════════════════════════════════════════════════

def play_movie(ip: str, query: str):
    """Search for a movie and play the first match.

    UI flow: search in VOD → select first result → detail page → play button.
    The detail page may focus on a play/resume button or description.
    """
    do_search(ip, query, section="vod")
    select_first_result(ip)
    # On the movie detail page — look for a play action
    wait(LOAD_DELAY * 0.5)
    focused = ui_focused_text(ip)
    # The detail page typically has action buttons; press OK on whatever is focused
    key(ip, "ok")
    wait(LOAD_DELAY * 0.5)
    output_ok(f"Playing movie: '{query}'", {"query": query})
    _notify("Formuler Remote", f"Playing: {query}")


# ══════════════════════════════════════════════════════════════
#  PLAY SERIES EPISODE
# ══════════════════════════════════════════════════════════════

def play_series(ip: str, query: str, season: int = 1, episode: int = 1):
    """Search for a series and play a specific episode.

    UI flow verified via ADB/uiautomator on Formuler Z11 Pro MAX:
    1. Search → select series from results
    2. Detail page: "Tous les épisodes" button is auto-focused → press OK
    3. Episode browser: seasons on left (focused), episodes on right
       - Down to navigate seasons, Right to move to episodes, Down to navigate episodes
    4. Press OK on episode to play
    """
    do_search(ip, query, section="series")
    select_first_result(ip)

    # We're on the series detail page (StreamSearchActivity).
    # "Tous les épisodes" button should be focused.
    # Verify by checking focused text.
    wait(LOAD_DELAY * 0.5)
    focused = ui_focused_text(ip)
    if focused and any("pisode" in t for t in focused):
        # "Tous les épisodes" is focused — press OK
        key(ip, "ok")
    else:
        # Fallback: try to find and click "Tous les épisodes"
        # It's typically the first action button on the detail page
        if VERBOSE:
            warn(f"Expected 'Tous les épisodes' focused, got: {focused}")
        key(ip, "ok")
    wait(LOAD_DELAY)

    # Now in episode browser:
    # Left panel: season list (Season 1 is selected by default)
    # Right panel: episodes for selected season

    # Navigate to correct season
    if season > 1:
        for _ in range(season - 1):
            key(ip, "down")
            wait(NAV_DELAY * 1.2)
        wait(NAV_DELAY * 2)

    # Move right to episode list
    key(ip, "right")
    wait(NAV_DELAY)

    # Navigate to correct episode (first episode is focused by default)
    if episode > 1:
        for _ in range(episode - 1):
            key(ip, "down")
            wait(NAV_DELAY * 1.2)

    # Verify correct episode is focused
    focused = ui_focused_text(ip)
    expected_label = f"S{season}:E{episode}"
    if focused and not any(expected_label in t for t in focused):
        if VERBOSE:
            warn(f"Expected '{expected_label}' focused, got: {focused}")

    # Play the episode
    key(ip, "ok")
    wait(LOAD_DELAY * 0.5)
    label = f"'{query}' S{season:02d}E{episode:02d}"
    output_ok(f"Playing {label}", {"query": query, "season": season, "episode": episode})
    _notify("Formuler Remote", f"Playing: {label}")


# ══════════════════════════════════════════════════════════════
#  STAR / FAVORITE TOGGLE
# ══════════════════════════════════════════════════════════════

def toggle_star(ip: str):
    keys(ip, "right", "right", "right", "right", delay=NAV_DELAY * 0.6)
    wait(NAV_DELAY)
    key(ip, "ok")
    wait(NAV_DELAY * 2)
    keys(ip, "left", "left", "left", "left", delay=NAV_DELAY * 0.6)
    output_ok("Star toggled.")


def star_search(ip: str, query: str, content_type: str = "vod"):
    do_search(ip, query, section=content_type)
    select_first_result(ip)
    toggle_star(ip)
    key(ip, "back")
    wait(NAV_DELAY * 2)
    output_ok(f"Toggled star for '{query}'")


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
    code, out = _adb_retry(
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
    code, out = _adb_retry(
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
#  TUNE HISTORY
# ══════════════════════════════════════════════════════════════

def _load_tune_history() -> list[dict]:
    if TUNE_HISTORY_FILE.exists():
        try:
            with open(TUNE_HISTORY_FILE) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return []


def _save_tune_history(history: list[dict]):
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with open(TUNE_HISTORY_FILE, "w") as f:
        json.dump(history[-50:], f, indent=2, ensure_ascii=False)


def _record_tune(channel: dict):
    """Record a channel tune event to history."""
    history = _load_tune_history()
    entry = {
        "title": channel.get("title", "Unknown"),
        "timestamp": datetime.datetime.now().isoformat(),
    }
    # Copy relevant fields
    for k in ("number", "unique_id", "intent", "content_id"):
        if channel.get(k):
            entry[k] = channel[k]
    history.append(entry)
    _save_tune_history(history)


def cmd_last(ip: str):
    """Retune the last tuned channel."""
    history = _load_tune_history()
    if not history:
        output_err("No tune history. Tune a channel first.")
        return
    last = history[-1]
    output_ok(f"Retuning: {last['title']}", last)
    _notify("Formuler Remote", f"Retuning: {last['title']}")
    if last.get("unique_id"):
        _tune_by_uid(ip, last["unique_id"])
    elif last.get("intent"):
        tune_by_intent(ip, last["intent"])
    else:
        cmd_tune(ip, last["title"])


def cmd_prev(ip: str):
    """Swap to previous channel (like TV recall button)."""
    history = _load_tune_history()
    if len(history) < 2:
        output_err("Need at least 2 channels in history.")
        return
    prev = history[-2]
    output_ok(f"Switching to previous: {prev['title']}", prev)
    _notify("Formuler Remote", f"Previous: {prev['title']}")
    if prev.get("unique_id"):
        _tune_by_uid(ip, prev["unique_id"])
    elif prev.get("intent"):
        tune_by_intent(ip, prev["intent"])
    else:
        cmd_tune(ip, prev["title"])


def cmd_tune_history(count: int = 10):
    """Show recent tune history."""
    history = _load_tune_history()
    if not history:
        output_err("No tune history.")
        return
    recent = history[-count:]
    recent.reverse()
    if JSON_MODE:
        output(recent)
    else:
        for i, entry in enumerate(recent, 1):
            ts = entry.get("timestamp", "")[:19].replace("T", " ")
            num = f" #{entry['number']}" if entry.get("number") else ""
            print(f"  {i:3d}  {ts}  {entry['title']}{num}")


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
    # Resolve aliases
    aliases = CONFIG.get("aliases", {})
    query = aliases.get(query.lower(), query)

    # Try full channel cache first
    if FULL_CHANNELS_CACHE.exists():
        with open(FULL_CHANNELS_CACHE) as f:
            full = json.load(f)
        # Try exact channel number
        if query.isdigit():
            for ch in full:
                if ch.get("number") == query:
                    output_ok(f"Tuning to: {ch['title']} (#{query})", ch)
                    _record_tune(ch)
                    _notify("Formuler Remote", f"Tuning: {ch['title']}")
                    if ch.get("unique_id"):
                        _tune_by_uid(ip, ch["unique_id"])
                    return
        # Try fuzzy match in full cache
        full_matches = _fuzzy_match(query, full)
        if len(full_matches) == 1 or (full_matches and all(m["title"] == full_matches[0]["title"] for m in full_matches)):
            ch = full_matches[0]
            output_ok(f"Tuning to: {ch['title']}", ch)
            _record_tune(ch)
            _notify("Formuler Remote", f"Tuning: {ch['title']}")
            if ch.get("unique_id"):
                _tune_by_uid(ip, ch["unique_id"])
            return
        if full_matches:
            _show_tune_choices(ip, full_matches, is_full=True)
            return

    # Fallback to favorites/history cache
    channels = get_channels(ip)
    matches = _fuzzy_match(query, channels)
    live = [m for m in matches if m["category"] in ("Favorites", "Live History")]
    if live:
        matches = live

    if not matches:
        results = search_provider(ip, query)
        if results:
            r = results[0]
            output_ok(f"Tuning to: {r['title']}", r)
            _record_tune(r)
            _notify("Formuler Remote", f"Tuning: {r['title']}")
            if r.get("unique_id"):
                _tune_by_uid(ip, r["unique_id"])
                return
            output_err("No unique ID found")
        else:
            error(f"No channel matching '{query}'")
        return

    if len(matches) == 1 or all(m["title"] == matches[0]["title"] for m in matches):
        ch = matches[0]
        output_ok(f"Tuning to: {ch['title']}", ch)
        _record_tune(ch)
        _notify("Formuler Remote", f"Tuning: {ch['title']}")
        if ch.get("intent"):
            tune_by_intent(ip, ch["intent"])
        return

    _show_tune_choices(ip, matches, is_full=False)


def _show_tune_choices(ip: str, matches: list[dict], is_full: bool):
    if AUTO_FIRST or JSON_MODE:
        ch = matches[0]
        output_ok(f"Tuning to: {ch['title']}", ch)
        _record_tune(ch)
        _notify("Formuler Remote", f"Tuning: {ch['title']}")
        if is_full and ch.get("unique_id"):
            _tune_by_uid(ip, ch["unique_id"])
        elif ch.get("intent"):
            tune_by_intent(ip, ch["intent"])
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
        output_ok(f"Tuning to: {ch['title']}", ch)
        _record_tune(ch)
        _notify("Formuler Remote", f"Tuning: {ch['title']}")
        if is_full and ch.get("unique_id"):
            _tune_by_uid(ip, ch["unique_id"])
        elif ch.get("intent"):
            tune_by_intent(ip, ch["intent"])


def cmd_search(ip: str, query: str):
    channels = get_channels(ip)
    cached = _fuzzy_match(query, channels)
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
    filtered = _fuzzy_match(filter_text, channels) if filter_text else channels

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
        channels = _fuzzy_match(filter_text, channels)

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
    output_ok(f"Browsing {section}. Use arrow keys to navigate, 'back' to return.")


def cmd_episodes(ip: str, query: str):
    """Open the episode browser for a series."""
    do_search(ip, query, section="series")
    select_first_result(ip)
    # Detail page: "Tous les épisodes" should be focused
    wait(LOAD_DELAY * 0.5)
    key(ip, "ok")  # open episodes browser
    wait(LOAD_DELAY)
    screenshot(ip, f"/tmp/formuler-episodes.png")
    output_ok(f"Episode browser open for '{query}'. Screenshot saved to /tmp/formuler-episodes.png")
    if not JSON_MODE:
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
    output_ok(f"Resuming: {last['title']}", last)
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
    path = "/tmp/formuler-epg.png"
    screenshot(ip, path)
    output_ok(f"EPG info screenshot saved to {path}", {"screenshot": path})
    key(ip, "info")  # dismiss


def cmd_guide(ip: str):
    ensure_mytv(ip)
    key(ip, "guide")
    wait(2)
    path = "/tmp/formuler-guide.png"
    screenshot(ip, path)
    output_ok(f"EPG guide screenshot saved to {path}", {"screenshot": path})


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
    output_ok(f"Showing EPG results for '{query}'. Navigate with arrows.")


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
    output_ok(f"Scheduled '{command}' at {target.strftime('%H:%M')} ({delay / 60:.0f}min from now)")


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
        output_ok(f"Cancelled: {active[index]['command']}")
    else:
        output_err(f"Invalid timer index. Use 'timers' to see list.")


# ══════════════════════════════════════════════════════════════
#  SLEEP TIMER
# ══════════════════════════════════════════════════════════════

_sleep_timer: dict | None = None  # {"timer": Timer, "time": str}


def _sleep_fire(ip: str):
    global _sleep_timer
    print(f"\n{_C.YELLOW}[Sleep Timer]{_C.RESET} Time's up — stopping playback and powering off")
    key(ip, "stop")
    wait(LOAD_DELAY * 0.5)
    key(ip, "sleep")
    _sleep_timer = None
    _notify("Formuler Remote", "Sleep timer fired — device powering off")


def cmd_sleep_timer(ip: str, minutes: float):
    global _sleep_timer
    if _sleep_timer and _sleep_timer["timer"].is_alive():
        _sleep_timer["timer"].cancel()
    t = threading.Timer(minutes * 60, _sleep_fire, args=[ip])
    t.daemon = True
    t.start()
    target = (datetime.datetime.now() + datetime.timedelta(minutes=minutes)).strftime("%H:%M")
    _sleep_timer = {"timer": t, "time": target}
    output_ok(f"Sleep timer set for {minutes:.0f}min (at {target})")


def cmd_sleep_at(ip: str, time_str: str):
    try:
        h, m = map(int, time_str.split(":"))
    except ValueError:
        output_err("Time format: HH:MM (e.g., 23:30)")
        return
    now = datetime.datetime.now()
    target = now.replace(hour=h, minute=m, second=0, microsecond=0)
    if target <= now:
        target += datetime.timedelta(days=1)
    minutes = (target - now).total_seconds() / 60
    cmd_sleep_timer(ip, minutes)


def cmd_sleep_cancel():
    global _sleep_timer
    if _sleep_timer and _sleep_timer["timer"].is_alive():
        _sleep_timer["timer"].cancel()
        output_ok(f"Sleep timer cancelled (was set for {_sleep_timer['time']})")
        _sleep_timer = None
    else:
        output_err("No sleep timer active.")


# ══════════════════════════════════════════════════════════════
#  ADVANCED REMOTE (Phase 10)
# ══════════════════════════════════════════════════════════════

def cmd_repeat(ip: str, key_name: str, count: int, delay_ms: float = 250):
    delay_s = delay_ms / 1000
    for i in range(count):
        key(ip, key_name)
        if i < count - 1:
            time.sleep(delay_s)
    output_ok(f"Pressed {key_name} x{count}")


def cmd_cec(ip: str, action: str):
    action = action.lower()
    if action == "on":
        key(ip, "wakeup")
        output_ok("CEC: Wake up / Power on")
    elif action == "off":
        key(ip, "sleep")
        output_ok("CEC: Sleep / Power off")
    elif action == "standby":
        key(ip, "power")
        output_ok("CEC: Standby toggle")
    else:
        output_err(f"Unknown CEC action: {action}. Use: on, off, standby")


def cmd_record_screen(ip: str, duration: int = 30, path: str = "/tmp/formuler-recording.mp4"):
    remote = "/sdcard/recording.mp4"
    info(f"Recording for {duration}s... (video surfaces will be green due to DRM)")
    try:
        adb(ip, "shell", "screenrecord", "--time-limit", str(duration), remote,
            timeout=duration + 10)
    except Exception:
        pass
    code, out = adb(ip, "pull", remote, path, timeout=30)
    adb(ip, "shell", "rm", remote)
    if code != 0:
        output_err(f"Recording pull failed: {out}")
    else:
        output_ok(f"Recording saved to {path}", {"path": path})


# ══════════════════════════════════════════════════════════════
#  CONVENIENCE COMMANDS
# ══════════════════════════════════════════════════════════════

def cmd_wake(ip: str):
    key(ip, "wakeup")
    wait(LOAD_DELAY)
    ensure_mytv(ip)
    output_ok("Device awake, MyTV running")


def cmd_power_off(ip: str):
    key(ip, "sleep")
    wait(NAV_DELAY * 2)
    run_adb("disconnect", tgt(ip))
    output_ok("CEC sleep sent, disconnected")


def cmd_history(count: int = 20):
    history_file = CACHE_DIR / "history"
    if not history_file.exists():
        output_err("No command history found.")
        return
    lines = history_file.read_text().splitlines()
    recent = lines[-count:] if count < len(lines) else lines
    if JSON_MODE:
        output(recent)
    else:
        for i, line in enumerate(recent, 1):
            print(f"  {i:3d}  {line}")


def cmd_watch(ip: str, interval: float = 5.0, directory: str = "/tmp"):
    """Take screenshots at regular intervals until Ctrl-C."""
    info(f"Watching every {interval}s to {directory}/ (Ctrl-C to stop)")
    try:
        n = 0
        while True:
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            path = f"{directory}/formuler-watch-{ts}.png"
            screenshot(ip, path)
            n += 1
            time.sleep(interval)
    except KeyboardInterrupt:
        output_ok(f"Watch stopped after {n} screenshots")


# ══════════════════════════════════════════════════════════════
#  M3U EXPORT
# ══════════════════════════════════════════════════════════════

def cmd_export_m3u(ip: str, path: str = "channels.m3u"):
    """Export full channel cache as M3U playlist (metadata only)."""
    channels = get_full_channels(ip)
    if not channels:
        output_err("No channels in cache. Run 'refresh-all' first.")
        return

    lines = ["#EXTM3U"]
    for ch in channels:
        num = ch.get("number", "0")
        title = ch.get("title", "Unknown")
        logo = ch.get("logo", "")
        extinf = f'#EXTINF:-1 tvg-chno="{num}"'
        if logo:
            extinf += f' tvg-logo="{logo}"'
        extinf += f",{title}"
        lines.append(extinf)
        # No stream URL available — CLI uses intents, not direct streams
        lines.append(f"# Channel {num}: {title} (no stream URL available)")

    content = "\n".join(lines) + "\n"
    Path(path).write_text(content, encoding="utf-8")
    output_ok(f"Exported {len(channels)} channels to {path}", {"path": path, "count": len(channels)})


# ══════════════════════════════════════════════════════════════
#  MISC
# ══════════════════════════════════════════════════════════════

def go_to_channel_number(ip: str, number: str):
    for d in number:
        key(ip, d)
    key(ip, "ok")


def screenshot(ip: str, path: str = "/tmp/formuler-screenshot.png"):
    remote = "/sdcard/screenshot.png"
    code, out = adb(ip, "shell", "screencap", "-p", remote)
    if code != 0:
        output_err(f"Screenshot capture failed: {out}")
        return
    code, out = run_adb("-s", tgt(ip), "pull", remote, path)
    if code != 0:
        output_err(f"Screenshot pull failed: {out}")
        return
    adb(ip, "shell", "rm", remote)
    output_ok(f"Screenshot saved to {path}", {"path": path})


def cmd_ping(ip: str):
    code, out = adb(ip, "shell", "echo", "pong", timeout=5)
    if code == 0 and "pong" in out:
        output_ok("Device reachable", {"ip": ip, "port": ADB_PORT})
    else:
        output_err(f"Device unreachable: {out}")


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
    last                            retune the last tuned channel
    prev                            swap to previous channel (recall)
    tune-history [count]            show recent tune history
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
    sleep-timer <minutes>           auto-off after N minutes
    sleep-at <HH:MM>               auto-off at specific time
    sleep-cancel                    cancel sleep timer

  {_C.CYAN}ADVANCED{_C.RESET}
    repeat <key> <count>            press key N times
    cec <on|off|standby>            TV power via CEC
    record [duration] [path]        screen record (default 30s)

  {_C.CYAN}EXPORT{_C.RESET}
    export-m3u [path]               export channel lineup as M3U file

  {_C.CYAN}CONVENIENCE{_C.RESET}
    wake                            CEC wakeup + launch MyTVOnline
    power-off                       CEC sleep + disconnect
    history [count]                 show recent command history
    watch [interval] [dir]          screenshot every N seconds (Ctrl-C to stop)

  {_C.CYAN}GENERAL{_C.RESET}
    type <text>                     type text on device
    open <app>                      launch app (youtube/netflix/prime/mytv/...)
    apps                            list installed apps
    screenshot [path]               capture screen
    status                          show device info
    ping                            check device connectivity
    reboot                          reboot device
    refresh                         reload favorites/history cache
    refresh-all                     rebuild full channel database
    commands                        list all commands as JSON schema
    keys                            list all key names
    help                            show this help
    quit / exit                     disconnect

  {_C.CYAN}FLAGS{_C.RESET}
    --json                          structured JSON output
    --yes                           skip confirmation prompts
    --first                         auto-select first match
    --wait <N>                      sleep N seconds after command
    --timeout <N>                   override ADB timeout (default 10s)
    --verbose / --debug             print ADB commands to stderr
    --dry-run                       show ADB commands without executing
    -h / --help                     show usage and exit
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

    # Help / meta
    elif cmd == "help":
        if JSON_MODE:
            output(COMMANDS)
        else:
            print(HELP_TEXT)
    elif cmd == "commands":
        output(COMMANDS)
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
    elif cmd == "last":
        cmd_last(ip)
    elif cmd == "prev":
        cmd_prev(ip)
    elif cmd == "tune-history":
        cmd_tune_history(int(args[0]) if args and args[0].isdigit() else 10)
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
    elif cmd == "sleep-timer" and args:
        try:
            cmd_sleep_timer(ip, float(args[0]))
        except ValueError:
            output_err("Usage: sleep-timer <minutes>")
    elif cmd == "sleep-at" and args:
        cmd_sleep_at(ip, args[0])
    elif cmd == "sleep-cancel":
        cmd_sleep_cancel()

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

    # Export
    elif cmd == "export-m3u":
        cmd_export_m3u(ip, args[0] if args else "channels.m3u")

    # Convenience
    elif cmd == "wake":
        cmd_wake(ip)
    elif cmd == "power-off":
        cmd_power_off(ip)
    elif cmd == "history":
        cmd_history(int(args[0]) if args and args[0].isdigit() else 20)
    elif cmd == "watch":
        interval = float(args[0]) if args and args[0].replace(".", "").isdigit() else 5.0
        directory = args[1] if len(args) > 1 else "/tmp"
        cmd_watch(ip, interval, directory)

    # Connectivity
    elif cmd == "ping":
        cmd_ping(ip)

    # Misc
    elif cmd == "screenshot":
        screenshot(ip, args[0] if args else "/tmp/formuler-screenshot.png")
    elif cmd == "status":
        cmd_status(ip)
    elif cmd == "reboot":
        if AUTO_YES:
            adb(ip, "shell", "reboot")
            output_ok("Rebooting...")
        else:
            try:
                if input("Reboot device? [y/N] ").strip().lower() == "y":
                    adb(ip, "shell", "reboot")
                    output_ok("Rebooting...")
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


def dispatch_chain(ip: str, raw: str) -> bool:
    """Dispatch a command string that may contain ; separated commands."""
    if ";" not in raw:
        return dispatch(ip, raw)
    for part in raw.split(";"):
        part = part.strip()
        if not part:
            continue
        if part.startswith("wait "):
            try:
                wait(float(part.split()[1]))
            except (ValueError, IndexError):
                wait(1)
        elif not dispatch(ip, part):
            return False
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
        "last", "prev", "tune-history",
        "sleep-timer", "sleep-at", "sleep-cancel",
        "export-m3u",
        "wake", "power-off", "history", "watch",
        "screenshot", "status", "ping", "reboot", "refresh", "refresh-all",
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
        if not dispatch_chain(ip, raw):
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
#  SHELL COMPLETIONS
# ══════════════════════════════════════════════════════════════

def _generate_completions(shell: str):
    all_words = sorted(set(list(COMMANDS.keys()) + list(KEYS.keys())))
    words_str = " ".join(all_words)
    if shell == "bash":
        print(f"""_formuler_remote_completions() {{
  local cur="${{COMP_WORDS[COMP_CWORD]}}"
  COMPREPLY=($(compgen -W "{words_str}" -- "$cur"))
}}
complete -F _formuler_remote_completions formuler-remote
complete -F _formuler_remote_completions formuler-remote.py""")
    elif shell == "zsh":
        print(f"""#compdef formuler-remote formuler-remote.py
_formuler_remote() {{
  local -a commands=({words_str})
  _describe 'command' commands
}}
compdef _formuler_remote formuler-remote formuler-remote.py""")
    elif shell == "fish":
        for w in all_words:
            desc = COMMANDS.get(w, {}).get("desc", "key")
            print(f"complete -c formuler-remote -f -a '{w}' -d '{desc}'")
    else:
        print(f"Unknown shell: {shell}. Use: bash, zsh, fish", file=sys.stderr)
        sys.exit(1)


# ══════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════

def main():
    global JSON_MODE, AUTO_YES, AUTO_FIRST, VERBOSE, ADB_TIMEOUT

    if not shutil.which("adb"):
        print("Error: adb not found. Install with: sudo pacman -S android-tools")
        sys.exit(1)

    # Parse flags (including value-bearing ones)
    simple_flags = {"--json", "--yes", "--first", "--verbose", "--debug", "--dry-run"}
    argv = []
    post_wait = 0.0
    i = 1
    while i < len(sys.argv):
        arg = sys.argv[i]
        if arg in simple_flags:
            if arg == "--json":
                JSON_MODE = True
            elif arg == "--yes":
                AUTO_YES = True
            elif arg == "--first":
                AUTO_FIRST = True
            elif arg in ("--verbose", "--debug"):
                VERBOSE = True
            elif arg == "--dry-run":
                DRY_RUN = True
                VERBOSE = True  # dry-run implies verbose
        elif arg == "--wait" and i + 1 < len(sys.argv):
            i += 1
            try:
                post_wait = float(sys.argv[i])
            except ValueError:
                print("Error: --wait requires a numeric argument", file=sys.stderr)
                sys.exit(1)
        elif arg == "--timeout" and i + 1 < len(sys.argv):
            i += 1
            try:
                ADB_TIMEOUT = int(sys.argv[i])
            except ValueError:
                print("Error: --timeout requires an integer argument", file=sys.stderr)
                sys.exit(1)
        elif arg in ("--help", "-h"):
            print(__doc__)
            print(HELP_TEXT)
            sys.exit(0)
        elif arg in ("--version", "-V"):
            print(f"formuler-remote {__version__}")
            sys.exit(0)
        elif arg == "--completions" and i + 1 < len(sys.argv):
            i += 1
            _generate_completions(sys.argv[i])
            sys.exit(0)
        else:
            argv.append(arg)
        i += 1

    ip = DEFAULT_IP
    off = 0
    # Accept IP address or hostname as first positional arg
    if argv and re.match(r"^[\w.\-]+$", argv[0]) and not argv[0] in KEYS and "." in argv[0]:
        ip = argv[0]
        off = 1

    if not ip:
        if JSON_MODE:
            _json_out({"ok": False, "error": "No device IP/hostname specified",
                        "hint": "Set FORMULER_IP env var, .env file, config file, or pass as first argument"})
        else:
            print("Error: No device IP/hostname specified.")
            print("Provide it via: CLI argument, FORMULER_IP env var, .env file, or config file.")
            print(f"Config: {CONFIG_FILE}")
        sys.exit(1)

    # Acquire lock to prevent concurrent instances
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _lock_file = open(CACHE_DIR / ".lock", "w")
    try:
        import fcntl
        fcntl.flock(_lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except ImportError:
        pass  # fcntl not available on Windows — skip locking
    except OSError:
        msg = "Another formuler-remote instance is running"
        if JSON_MODE:
            _json_out({"ok": False, "error": msg})
        else:
            print(f"Error: {msg}")
        sys.exit(1)

    if not connect(ip, quiet=JSON_MODE):
        sys.exit(1)

    remaining = argv[off:]
    if not remaining:
        # Batch/pipe mode: read commands from stdin when not a TTY
        if not sys.stdin.isatty():
            for line in sys.stdin:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                dispatch_chain(ip, line)
                if post_wait > 0:
                    time.sleep(post_wait)
            run_adb("disconnect", tgt(ip))
            sys.exit(_exit_code)
        else:
            interactive(ip)
            return

    cmd_str = " ".join(remaining)
    dispatch_chain(ip, cmd_str)
    if post_wait > 0:
        time.sleep(post_wait)
    run_adb("disconnect", tgt(ip))
    sys.exit(_exit_code)


if __name__ == "__main__":
    main()
