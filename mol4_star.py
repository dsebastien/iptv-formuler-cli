#!/usr/bin/env python3
"""Star (favorite) series or movies in MYTVOnline 4 (Formuler Z11, package tv.formuler.mol3.real).

MOL4 exposes no text to uiautomator and blocks its content provider, so this works from
screenshots: OCR (tesseract) reads result titles, and pixel checks read the star state.
The star is a toggle, so the script reads its state first and never presses a filled star.

Usage: mol4_star.py [--ip IP] [--type series|vod] [--dry-run] "Title 1" "Title 2" ...
Precondition: MOL4 shows the universal search screen (UsActivity) or any screen from which
BACK leads there. Run `mol4_star.py --open-search` once from a series/VOD detail page.
"""
import argparse, json, os, re, struct, subprocess, sys, tempfile, time, unicodedata
import numpy as np

KEY = {"up": 19, "down": 20, "left": 21, "right": 22, "ok": 23, "back": 4, "enter": 66, "del": 67}
TABS = {"vod": (645, 805), "series": (821, 1035)}  # x-range of the VOD / Séries TV tabs
CARD_X0, CARD_DX, CARD_W, ROW_Y = 110, 244, 240, 728
QUALITY = [("UHD", 4), ("4K", 4), ("FHD", 3), ("1080", 3), ("MULTI", 2), ("HD", 1)]
TMP = tempfile.mkdtemp(prefix="mol4-")
FOCUS = "tabs"  # where the focus is on the search screen: "tabs" or "card"


def adb(ip, *a, capture=False):
    r = subprocess.run(["adb", "-s", f"{ip}:5555", *a], capture_output=True)
    return r.stdout if capture else r.returncode


SCRCPY = None  # mol4_scrcpy.Scrcpy instance when --scrcpy is on: instant keys and frames


def keys(ip, *names, pause=0.35):
    codes = [int(KEY.get(n, n)) for n in names]
    if SCRCPY:
        for c in codes:
            SCRCPY.key(c)
            time.sleep(0.12)  # let the UI take each press
    else:
        adb(ip, "shell", "input", "keyevent", *map(str, codes))
    time.sleep(pause)


def type_text(ip, text):
    if SCRCPY:
        SCRCPY.text(text.replace("%s", " "))
    else:
        adb(ip, "shell", "input", "text", text)


_SHOTS = [0]


def shot(ip, name="s"):
    # Unique file per screenshot: callers keep earlier screenshots (e.g. the results screen).
    _SHOTS[0] += 1
    if SCRCPY:
        f = SCRCPY.frame(0.25)  # give the last key press a moment to render
        p = os.path.join(TMP, f"{name}-{_SHOTS[0]:05d}.ppm")
        with open(p, "wb") as fh:
            fh.write(b"P6 %d %d 255\n" % (f.shape[1], f.shape[0]) + f.tobytes())
        return p
    p = os.path.join(TMP, f"{name}-{_SHOTS[0]:05d}.png")
    raw = adb(ip, "exec-out", "screencap", capture=True)
    w, h = struct.unpack("<II", raw[:8])
    subprocess.run(["magick", "-size", f"{w}x{h}", "-depth", "8", "rgba:-", p],
                   input=raw[16:16 + w * h * 4], check=True)
    return p


def rgb(png, w, h, x, y):
    raw = subprocess.run(["magick", png, "-alpha", "off", "-crop", f"{w}x{h}+{x}+{y}", "+repage",
                          "-depth", "8", "rgb:-"], capture_output=True).stdout
    return np.frombuffer(raw, np.uint8).reshape(h, w, 3).astype(int)


def red_mask(a):
    return (a[:, :, 0] > 200) & (a[:, :, 1] < 120) & (a[:, :, 2] < 110)


def ocr(png, w, h, x, y, thr=50, scale=300):
    # One temp file per call: mol4_collect runs OCR in parallel threads.
    fd, t = tempfile.mkstemp(suffix=".png", dir=TMP)
    os.close(fd)
    subprocess.run(["magick", png, "-alpha", "off", "-crop", f"{w}x{h}+{x}+{y}", "+repage", "-colorspace",
                    "gray", "-negate", "-resize", f"{scale}%", "-threshold", f"{thr}%", "-bordercolor",
                    "white", "-border", "20", t])
    out = subprocess.run(["tesseract", t, "stdout", "--psm", "7", "-l", "eng"],
                         capture_output=True, text=True).stdout.strip()
    os.unlink(t)
    return out


# Card titles are small and OCR is unstable: read each with several settings, keep all.
OCR_VARIANTS = [(0, 44, 50, 300), (-6, 56, 50, 300), (-4, 50, 60, 300), (0, 44, 40, 400)]


def card_titles(png, x):
    out = []
    for dy, h, thr, sc in OCR_VARIANTS:
        t = ocr(png, CARD_W, h, x, ROW_Y + dy, thr, sc)
        if t and t not in out:
            out.append(t)
    return out


def norm(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def selected_tab(png):
    a = red_mask(rgb(png, 1920, 80, 0, 176))
    for name, (x0, x1) in TABS.items():
        if a[:, x0:x1].sum() > 2000:
            return name
    return None


def cards(png, max_cards=7, full=False):
    """Return [(index, [ocr variants])] for result cards in the first row (OCR in parallel).

    Fast pass: one OCR setting per card. full=True adds the other settings (slower)."""
    from concurrent.futures import ThreadPoolExecutor
    xs = []
    for i in range(max_cards):
        x = CARD_X0 + CARD_DX * i
        if rgb(png, 200, 200, x + 20, 450).std() < 8:  # empty slot: flat background
            break
        xs.append((i, x))
    variants = OCR_VARIANTS if full else OCR_VARIANTS[:1]
    with ThreadPoolExecutor(max_workers=8) as ex:
        jobs = {(i, v): ex.submit(ocr, png, CARD_W, v[1], x, ROW_Y + v[0], v[2], v[3])
                for i, x in xs for v in variants}
    return [(i, list(dict.fromkeys(t for (j, _), f in jobs.items() if j == i
                                   for t in [f.result()] if t))) for i, _ in xs]


def focused_card_x(png):
    """x of the result card with the red focus frame, or None.

    The frame is two thin red vertical lines one card width apart, running the full card
    height. Red posters (e.g. "Love, Death & Robots") have red areas, not such line pairs.
    """
    a = rgb(png, 1920, 360, 0, 370)
    cnt = red_mask(a).sum(0)
    cols = np.where(cnt > 300)[0]
    for c in cols:
        if any(225 <= d - c <= 250 for d in cols):
            return int(c)
    return None


def similar(a, b):
    """Partial similarity: the focused card title scrolls (marquee), so OCR sees a slice of it."""
    import difflib
    a, b = norm(a), norm(b)
    if len(a) < 5:
        return 0
    if len(a) >= len(b):
        return difflib.SequenceMatcher(None, a, b).ratio()
    return max(difflib.SequenceMatcher(None, a, b[k:k + len(a)]).ratio() for k in range(len(b) - len(a) + 1))


def poster(png, x):
    return rgb(png, 160, 160, x + 40, 470)


def focus_card(ip, i, label, results_png=None):
    """Move focus to result card i (row at its start) and check it is the right card.

    The check compares the poster under the focus frame with card i's poster in the
    results screenshot (robust), and falls back to the slot position and the OCR title.
    """
    keys(ip, "down", pause=0.8)
    keys(ip, *(["left"] * 12), pause=0.8)
    if i:
        keys(ip, *(["right"] * i), pause=0.9)
    png = shot(ip)
    x = focused_card_x(png)
    if x is None:
        return False
    # Row not scrolled: the frame sits at the expected slot. Otherwise compare titles
    # without the "(QUALITY)" suffix, which OCR truncates differently on each card.
    if results_png is not None:
        ref = poster(results_png, CARD_X0 + CARD_DX * i)
        best = min(abs(poster(png, x + dx) - ref).mean() for dx in range(0, 9, 2))
        return best < 18
    if abs(x - (CARD_X0 + CARD_DX * i - 4)) <= 25:
        return True
    core = lambda t: re.sub(r"\(.*$", "", t)
    return max((similar(core(t), core(label)) for t in card_titles(png, max(0, x - 4))), default=0) > 0.7


def has_star_badge(png, i):
    """Yellow star at the top-right corner of result card i = already a favorite."""
    x = CARD_X0 + CARD_DX * i
    # The badge is a small star (~30 px) in the corner; a yellow poster fills the whole patch.
    a = rgb(png, 60, 50, x + 175, 385)
    yellow = (a[:, :, 0] > 220) & (a[:, :, 1] > 170) & (a[:, :, 2] < 90)
    frac = yellow.mean()
    return 0.04 < frac < 0.4 and not yellow[0].any() and not yellow[:, 0].any()


def quality(title):
    t = title.upper()
    for q, score in QUALITY:
        if q in t:
            return score
    return 0


def match_score(query, title):
    """3 = same title, 2 = title starts with the query, 1 = fuzzy/multi-word match, 0 = no.

    A one-word query never matches inside a longer title ("Sherlock" must not pick
    "Young Sherlock"). OCR noise is handled by a fuzzy ratio on the whole title.
    """
    import difflib
    q, nt = norm(query), norm(re.sub(r"\(.*$", "", title))
    nt = re.sub(r"^\w{1,4} ", "", nt)  # drop the OCR'd |FR| / |EN| prefix
    nt = re.sub(r"^(the|les|le|la|l) ", "", nt)
    q2 = re.sub(r"^(the|les|le|la|l) ", "", q)
    if nt == q2:
        return 3
    if nt.startswith(q2 + " "):
        return 2
    truncated = title.rstrip().endswith(".")
    if truncated and len(nt) >= 6 and q2.startswith(nt.rstrip(" .")):
        return 2
    qtok, tok = set(q2.split()), set(nt.split())
    if len(qtok) > 1 and len(qtok & tok) / len(qtok) >= 0.75:
        return 1
    if difflib.SequenceMatcher(None, nt, q2).ratio() >= 0.8:
        return 1
    return 0


def pick(query, found, prefer=None):
    """Best title match, then the preferred version label (e.g. MULTI), then the best quality."""
    best, best_key = None, None
    for i, variants in found:
        for t in variants:
            match = match_score(query, t)
            if not match:
                continue
            k = (match, bool(prefer and prefer.upper() in t.upper()), quality(t))
            if best_key is None or k > best_key:
                best, best_key = (i, t), k
    return best


def star_state(png):
    """Read the focused star button: 'filled', 'outline', 'notstar' (other button) or 'nofocus'.

    The button row moves up or down with the description length, so search a band.
    The center of a filled star is white; the center of an outline star is the red button.
    """
    y0 = 380
    a = rgb(png, 1500, 420, 0, y0)
    m = red_mask(a)
    rows = np.where(m.sum(1) > 40)[0]
    if len(rows) == 0:
        return "nofocus"
    r0, r1 = rows.min(), rows.max()
    cols = np.where(m[r0:r1 + 1].sum(0) > 10)[0]
    c0, c1 = cols.min(), cols.max()
    if c1 - c0 > 220 or r1 - r0 > 140:
        return "notstar"
    cy, cx = (r0 + r1) // 2, (c0 + c1) // 2
    patch = a[cy - 6:cy + 7, cx - 6:cx + 7]
    white = ((patch > 215).all(2)).mean()
    return "filled" if white > 0.5 else "outline"


def no_content(png):
    return "contenu" in ocr(png, 700, 90, 610, 650).lower()


def wait_results(ip, timeout=35):
    """Poll until result cards or the 'Pas de contenu' message show."""
    end = time.time() + timeout
    png = shot(ip)
    while time.time() < end:
        if no_content(png) or rgb(png, 200, 200, CARD_X0 + 20, 450).std() >= 8:
            time.sleep(0.8)  # let the remaining cards render
            return shot(ip)
        time.sleep(0.7)
        png = shot(ip)
    return png


def search(ip, query, kind):
    # Focus the search field with a cursor: exactly one UP from the tabs, two from a card.
    # A further UP removes the cursor and typing goes nowhere. Do not press OK either.
    global FOCUS
    keys(ip, *(["up"] * (2 if FOCUS == "card" else 1)), pause=0.6)
    FOCUS = "tabs"
    keys(ip, "123", *(["del"] * 50), pause=0.3)  # 123 = MOVE_END
    ascii_q = "".join(c for c in unicodedata.normalize("NFKD", query) if ord(c) < 128)
    ascii_q = re.sub(r"[^A-Za-z0-9 ]", " ", ascii_q).strip().replace(" ", "%s")
    type_text(ip, ascii_q)
    time.sleep(0.4)
    keys(ip, "enter", pause=1.5)
    png = wait_results(ip)
    field = norm(ocr(png, 830, 90, 250, 42))
    if field.replace(" ", "") != norm(query).replace(" ", ""):
        return "badfield:" + field
    tab = selected_tab(png)
    for _ in range(4):
        if tab == kind:
            break
        keys(ip, "right" if (tab is None or TABS[tab][0] < TABS[kind][0]) else "left", pause=1)
        png = wait_results(ip)
        tab = selected_tab(png)
    return png if tab == kind else None


def star(ip, query, kind, dry=False, unstar=False, prefer=None):
    """query may be "search text=>expected title" when the catalog title has punctuation
    the app search needs exactly (e.g. "robot=>Mr Robot" for "Mr. Robot")."""
    text, _, expected = query.partition("=>")
    expected = expected or text
    png = search(ip, text, kind)
    if png is None:
        return {"title": query, "result": "no-results"}
    if png.startswith("badfield:"):
        return {"title": query, "result": "search-failed", "field": png[9:]}
    if no_content(png):
        return {"title": query, "result": "not-in-catalog"}
    # The results row can keep the scroll position of an earlier search: move it to its
    # start (DOWN, LEFT x12, UP back to the tabs) so card i sits in slot i.
    keys(ip, "down", pause=0.6)
    keys(ip, *(["left"] * 12), pause=0.6)
    keys(ip, "up", pause=1.0)
    png = shot(ip)
    found = cards(png)
    choice = pick(expected, found, prefer)
    if not choice:  # OCR is unstable on small titles: retry with all settings
        found = cards(png, full=True)
        choice = pick(expected, found, prefer)
    if not choice:
        return {"title": query, "result": "no-match", "seen": [v[0] for _, v in found if v]}
    i, label = choice
    # Do not trust the poster badge: search results are cached and the badge can be stale.
    # Always open the title and read the real star.
    return set_card_star(ip, query, i, label, dry, unstar, png)


def set_card_star(ip, query, i, label, dry=False, unstar=False, results_png=None):
    """Open result card i of the current search and set its star (search screen, focus on tabs)."""
    global FOCUS
    ok = focus_card(ip, i, label, results_png)
    FOCUS = "card"
    if not ok:
        return {"title": query, "picked": label, "result": "focus-failed"}
    keys(ip, "ok", pause=3.5)
    keys(ip, *(["right"] * 6), pause=0.8)
    state = star_state(shot(ip))
    res = {"title": query, "picked": label, "before": state}
    want = "filled" if unstar else "outline"  # the state that needs a press
    if state == want and not dry:
        keys(ip, "ok", pause=1.5)
        res["after"] = star_state(shot(ip))
    if unstar:
        res["result"] = ("unstarred" if res.get("after") == "outline" else
                         "not-starred" if state == "outline" else "dry-run" if dry else "check")
    else:
        res["result"] = ("starred" if res.get("after") == "filled" else
                         "already" if state == "filled" else "dry-run" if dry and state == "outline" else
                         "check")
    keys(ip, "back", pause=2)
    FOCUS = "card"
    return res


def resumed(ip):
    out = adb(ip, "shell", "dumpsys activity activities | grep mResumedActivity", capture=True).decode()
    return out.strip().split("/")[-1].split(" ")[0] if out else ""


def open_search(ip):
    """Open the universal search (UsActivity) from anywhere.

    UsActivity is not exported, so: deep-link to a VOD/series page published in the launcher
    rows (formuler.media.tv/preview_program), then UP, RIGHT to its search icon, OK.
    """
    global FOCUS
    if "UsActivity" in resumed(ip):
        return True
    raw = adb(ip, "shell", "content query --uri content://formuler.media.tv/preview_program "
              "--projection intent_uri", capture=True).decode()
    mm = re.search(r"S\.vod_unique_id=([^;]+);i\.channel_type=(\d+)", raw)
    if not mm:
        return False
    import urllib.parse
    # Without season/episode the link opens the title page, whose header has the search icon.
    uid = re.sub(r"&(season_id|episode_id)=[^&]*", "", urllib.parse.unquote(mm.group(1)))
    adb(ip, "shell", "am", "start", "-n", "tv.formuler.mol3.real/tv.formuler.mol3.deeplink.SchemeLinkActivity",
        "--es", "vod_unique_id", f"'{uid}'", "--ei", "channel_type", mm.group(2))
    time.sleep(4)
    keys(ip, "up", pause=0.8)
    keys(ip, "right", pause=0.8)
    keys(ip, "ok", pause=2.5)
    FOCUS = "tabs"
    if "UsActivity" in resumed(ip):
        keys(ip, "back", pause=1)  # close the on-screen keyboard
        keys(ip, "down", pause=0.6)  # field -> tabs
        return True
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ip", default=os.environ.get("FORMULER_IP"),
                    help="box IP (default: $FORMULER_IP)")
    ap.add_argument("--type", choices=["series", "vod"], default="series")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--unstar", action="store_true", help="remove the favorite instead of adding it")
    ap.add_argument("--prefer", help="preferred version label, e.g. MULTI or VOST (default: best quality)")
    ap.add_argument("--scrcpy", action="store_true",
                    help="drive the box through scrcpy (instant keys and frames; needs scrcpy + PyAV)")
    ap.add_argument("--focus", choices=["tabs", "card"], default="tabs",
                    help="where the focus is on the search screen at start")
    ap.add_argument("titles", nargs="+")
    a = ap.parse_args()
    if not a.ip:
        ap.error("set FORMULER_IP or pass --ip")
    global FOCUS, SCRCPY
    FOCUS = a.focus
    if a.scrcpy:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from mol4_scrcpy import Scrcpy
        SCRCPY = Scrcpy(f"{a.ip}:5555").start()
    if "UsActivity" not in resumed(a.ip):
        if not open_search(a.ip):
            sys.exit("could not open the search screen")
    try:
        for t in a.titles:
            r = star(a.ip, t, a.type, a.dry_run, a.unstar, a.prefer)
            print(json.dumps(r, ensure_ascii=False), flush=True)
    finally:
        if SCRCPY:
            SCRCPY.stop()


if __name__ == "__main__":
    main()
