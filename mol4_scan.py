#!/usr/bin/env python3
"""Scan MYTVOnline 4 VOD categories into JSON lines (title, year, genres, runtime, ...).

Usage: mol4_scan.py [--ip IP] [--max-per-cat 2000] INDEX=NAME[@SKIP] [...] > items.jsonl
INDEX is the position in the VOD left menu, counted from "Favoris" = 0
(Favoris, Historique, Ajouts récents, then the provider categories).
"""
import argparse, os, re, sys, time, importlib.util

here = os.path.dirname(os.path.abspath(__file__))
def load(name, file):
    spec = importlib.util.spec_from_file_location(name, os.path.join(here, file))
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); return mod
m = load("mol4", "mol4_star.py")
c = load("mol4c", "mol4_collect.py")


def focused_menu_item(ip):
    """OCR the focused (red) entry of the VOD left menu."""
    import numpy as np
    png = m.shot(ip)
    a = m.rgb(png, 500, 1080, 140, 0)
    rows = np.where(m.red_mask(a).sum(1) > 200)[0]
    if len(rows) == 0:
        return ""
    y0, y1 = rows.min(), rows.max()
    return m.ocr(png, 440, max(30, y1 - y0), 170, y0, thr=50, scale=250)


def open_vod_category(ip, index, name=""):
    """Fresh start of the app (force-stop keeps all data), MENU > VOD, then the category.

    A plain relaunch restores the last screen (e.g. a search), so force-stop first.
    The left menu wraps around, so never press UP to "reach the top": count DOWN from Favoris.
    """
    m.adb(ip, "shell", "am", "force-stop", "tv.formuler.mol3.real")
    time.sleep(1)
    m.adb(ip, "shell", "monkey", "-p", "tv.formuler.mol3.real", "-c", "android.intent.category.LAUNCHER", "1")
    time.sleep(8)
    m.keys(ip, "82", pause=2)                            # MENU -> main menu (TV en direct focused)
    m.keys(ip, "down", pause=0.6)                        # VOD
    m.keys(ip, "ok", pause=4)                            # VOD screen, left menu on "Favoris"
    first = focused_menu_item(ip)
    if "favori" not in first.lower():
        sys.exit(f"VOD menu did not start on Favoris (saw {first!r})")
    if index:
        m.keys(ip, *(["down"] * index), pause=3)
    got = focused_menu_item(ip)
    if name and m.norm(name)[:8] not in m.norm(got):
        sys.exit(f"expected category {name!r}, focused {got!r}")
    # After a fresh start the first selected category can stay a grey skeleton forever.
    # Selecting the previous entry and coming back starts the loading.
    m.keys(ip, "up", pause=3)
    m.keys(ip, "down", pause=4)
    # Big categories still need time: wait for a real header
    # before entering the grid, or the first key presses go nowhere or into the menu.
    for _ in range(40):
        png = m.shot(ip)
        # With the menu open the header sits right of the menu (x ~730).
        if re.search(r"(19|20)\d\d", m.ocr(png, 1100, 50, 730, 236, thr=70, scale=200)):  # dimmed text
            break
        time.sleep(3)
    else:
        sys.exit(f"category {name!r} did not load")
    m.keys(ip, "right", pause=3)                         # into the grid, first card


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ip", default=os.environ.get("FORMULER_IP"),
                    help="box IP (default: $FORMULER_IP)")
    ap.add_argument("--max-per-cat", type=int, default=2000)
    ap.add_argument("cats", nargs="+")
    a = ap.parse_args()
    if not a.ip:
        ap.error("set FORMULER_IP or pass --ip")
    for spec in a.cats:
        idx, _, name = spec.partition("=")
        name, _, skip = name.partition("@")      # "3=FILMS RECENTS@160" resumes at item 160
        open_vod_category(a.ip, int(idx), name)
        c.walk_grid(a.ip, a.max_per_cat, category=name or idx, skip=int(skip or 0))


if __name__ == "__main__":
    main()
