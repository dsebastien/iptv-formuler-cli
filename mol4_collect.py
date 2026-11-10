#!/usr/bin/env python3
"""Walk a MYTVOnline 4 VOD/series row (e.g. VOD > "Ajouts récents") and read each item.

Precondition: the group is selected in the left menu (e.g. VOD > Ajouts récents). The script
presses RIGHT to enter the row and reads the header of the focused item with OCR:
title, "<release date> • <genres>", TMDb score and "Date d'ajout: ...".
Prints one JSON line per item. Stops at the end of the row or after --max items.

Usage: mol4_collect.py [--ip IP] [--max 300] > items.jsonl
"""
import argparse, json, os, re, subprocess, sys, time
import numpy as np
import importlib.util

_spec = importlib.util.spec_from_file_location("mol4", os.path.join(os.path.dirname(__file__), "mol4_star.py"))
m = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(m)

# Header layout of the focused item (1920x1080), right of the 640 px menu.
TITLE = (1150, 120, 100, 100)     # w, h, x, y  (often a logo image)
META = (1150, 50, 100, 238)       # "11 September 2026 • Thriller"
SCORE = (600, 50, 100, 292)       # "12+  TMDb 72%  1h 54m"
ADDED = (900, 46, 100, 362)       # "Date d'ajout: Yesterday"


def read(png, box, thr=50):
    w, h, x, y = box
    return m.ocr(png, w, h, x, y, thr=thr, scale=200)


Y0, ROWS, W = 100, 320, 1920  # header band sent by the box (rows 100..420)


def _band_to_png(raw, path):
    """Rebuild a full 1920x1080 PNG (black outside the band) so the OCR boxes stay valid."""
    subprocess.run([m.MAGICK, "-size", f"{W}x{ROWS}", "-depth", "8", "rgba:-", "-background", "black",
                    "-extent", f"{W}x1080-0-{Y0}", path], input=raw, check=True)
    return path


def move_and_read(ip, keycodes):
    """Press keys and take two header captures in one ADB call.

    The first capture is taken at once (the text title shows before the logo loads), the
    second ~0.8 s later (meta line). The box crops the header band from raw screencaps
    (PNG encoding on the box costs ~2 s; a full raw frame costs ~1.7 s over Wi-Fi).
    Returns two PNG paths; PNG conversion happens later in the OCR workers.
    """
    ks = " ".join(str(m.KEY.get(k, k)) for k in keycodes)
    band = (f"dd if=/sdcard/mol4_{{}}.raw bs=16 skip=1 2>/dev/null | "
            f"dd bs={W * 4} skip={Y0} count={ROWS} 2>/dev/null")
    cmd = (("input keyevent " + ks + "; ") if ks else "") + \
          "screencap /sdcard/mol4_t.raw; sleep 1.2; screencap /sdcard/mol4_m.raw; " + \
          band.format("t") + "; " + band.format("m")
    data = m.adb(ip, "exec-out", cmd, capture=True)
    half = W * 4 * ROWS
    if len(data) < 2 * half:
        raise RuntimeError(f"short capture: {len(data)} bytes")
    m._SHOTS[0] += 1
    k = m._SHOTS[0]
    return ((os.path.join(m.TMP, f"t-{k:05d}.png"), data[:half]),
            (os.path.join(m.TMP, f"m-{k:05d}.png"), data[half:2 * half]))


def parse(n, tpng, mpng):
    if isinstance(tpng, tuple):
        tpng = _band_to_png(tpng[1], tpng[0])
    if isinstance(mpng, tuple):
        mpng = _band_to_png(mpng[1], mpng[0])
    item = {"n": n, "title": read(tpng, TITLE), "meta": read(mpng, META),
            "score": read(mpng, SCORE), "added": read(mpng, ADDED)}
    mm = re.search(r"(19|20)\d\d", item["meta"])
    item["year"] = int(mm.group(0)) if mm else None
    item["genres"] = re.sub(r"^.*?(19|20)\d\d\W*", "", item["meta"]).strip()
    rt = re.search(r"(\d+)h\s*(\d+)m|(\d+)\s*m", item["score"])
    item["runtime"] = (int(rt.group(1)) * 60 + int(rt.group(2)) if rt and rt.group(1) else
                       int(rt.group(3)) if rt else None)
    return item


def header_sig(tcap, mcap):
    """Cheap fingerprint of the title (first capture) and meta line (second capture).
    The title changes at once after a move; the meta line can still be blank."""
    t = np.frombuffer(tcap[1], np.uint8).reshape(ROWS, W, 4)[0:110:4, 100:1200:4, :3]
    mm = np.frombuffer(mcap[1], np.uint8).reshape(ROWS, W, 4)[138:178:4, 100:700:4, :3]
    return np.concatenate([t.ravel(), mm.ravel()]).astype(int)


def walk_grid(ip, maxn, cols=7, category="", skip=0):
    """Walk a category grid row by row from the focused first card.

    Navigation and screenshots run in this thread; OCR runs in a worker pool, so the box
    never waits for tesseract. End of grid = the header did not change after a move.
    """
    from concurrent.futures import ThreadPoolExecutor
    pool = ThreadPoolExecutor(max_workers=6)
    futures = []
    # Move away and back so the first header shows its text title (before the logo loads).
    m.keys(ip, "right", pause=1.5)
    tpng, mpng = move_and_read(ip, ["left"])
    n, col, prev = 0, 0, None
    seen = set()  # coarse fingerprints of the titles: the grid wraps to the top at its end
    if skip:  # resume: jump to item `skip` (row skip//cols, column skip%cols)
        moves = ["down"] * (skip // cols) + ["right"] * (skip % cols)
        for i in range(0, len(moves), 10):
            m.keys(ip, *moves[i:i + 10], pause=1.5)
        tpng, mpng = move_and_read(ip, [])
        n, col = skip, skip % cols
    while n < maxn:
        sig = header_sig(tpng, mpng)
        if prev is not None and np.abs(sig - prev).mean() < 2:
            # Maybe just slow: look again once before calling it the end of the grid.
            tpng, mpng = move_and_read(ip, [])
            sig = header_sig(tpng, mpng)
            if np.abs(sig - prev).mean() < 2:
                break
        prev = sig
        t = np.frombuffer(tpng[1], np.uint8).reshape(ROWS, W, 4)[10:90:8, 100:1100:8, :3]
        fp = (t.mean(2) > 128).tobytes()   # white title text on dark background
        if fp in seen:
            break  # back at a title we already read: the grid wrapped around
        seen.add(fp)
        futures.append(pool.submit(parse, n, tpng, mpng))
        n += 1
        if col < cols - 1:
            tpng, mpng = move_and_read(ip, ["right"])
            col += 1
        else:
            tpng, mpng = move_and_read(ip, ["down"] + ["left"] * (cols - 1))
            col = 0
        # flush finished items in order
        while futures and futures[0].done():
            item = futures.pop(0).result()
            item["category"] = category
            print(json.dumps(item, ensure_ascii=False), flush=True)
    for f in futures:
        item = f.result()
        item["category"] = category
        print(json.dumps(item, ensure_ascii=False), flush=True)
    pool.shutdown()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ip", default=os.environ.get("FORMULER_IP"),
                    help="box IP (default: $FORMULER_IP)")
    ap.add_argument("--max", type=int, default=300)
    ap.add_argument("--enter", action="store_true", help="press RIGHT once first to enter the row")
    ap.add_argument("--grid", action="store_true", help="walk a 7-column category grid")
    ap.add_argument("--category", default="")
    a = ap.parse_args()
    if not a.ip:
        ap.error("set FORMULER_IP or pass --ip")
    if a.enter:
        m.keys(a.ip, "right", pause=2)
    if a.grid:
        return walk_grid(a.ip, a.max, category=a.category)
    last, same = None, 0
    for n in range(a.max):
        png = m.shot(a.ip)
        item = {"n": n, "title": read(png, TITLE), "meta": read(png, META),
                "score": read(png, SCORE), "added": read(png, ADDED)}
        mm = re.search(r"(19|20)\d\d", item["meta"])
        item["year"] = int(mm.group(0)) if mm else None
        item["genres"] = re.sub(r"^.*?(19|20)\d\d\W*", "", item["meta"]).strip()
        rt = re.search(r"(\d+)h\s*(\d+)m|(\d+)\s*m", item["score"])
        item["runtime"] = (int(rt.group(1)) * 60 + int(rt.group(2)) if rt and rt.group(1) else
                           int(rt.group(3)) if rt else None)
        key = (item["title"], item["meta"], item["score"])
        if key == last:
            same += 1
            if same >= 2:  # focus did not move twice: end of the row
                break
            m.keys(a.ip, "right", pause=1.2)
            continue
        same, last = 0, key
        print(json.dumps(item, ensure_ascii=False), flush=True)
        m.keys(a.ip, "right", pause=1.2)


if __name__ == "__main__":
    main()
