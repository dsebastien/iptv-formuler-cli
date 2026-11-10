#!/usr/bin/env python3
"""Match collected MOL4 items (mol4_collect.py JSON lines) to IMDb ratings.

Needs an index built from the public IMDb datasets (https://datasets.imdbws.com/):
  imdb_match.py --build DIR      # reads DIR/title.{ratings,basics,akas}.tsv.gz -> DIR/movies.pkl
  imdb_match.py --index DIR/movies.pkl items.jsonl [--min 7] [--exclude Documentary]

Matching: normalized title (original, primary or a FR/BE/CA/world AKA), year +/- 1, then the
closest runtime, then the most votes. Fuzzy fallback on titles of the same years.
Prints one JSON line per item with imdb id, rating, votes, genres and keep=true/false.
"""
import argparse, csv, difflib, gzip, json, pickle, re, sys, unicodedata


def norm(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def build(d):
    rat = {}
    with gzip.open(f"{d}/title.ratings.tsv.gz", "rt") as f:
        next(f)
        for line in f:
            t, r, v = line.rstrip("\n").split("\t")
            rat[t] = (float(r), int(v))
    mv = {}
    with gzip.open(f"{d}/title.basics.tsv.gz", "rt", encoding="utf8") as f:
        next(f)
        for line in f:
            p = line.rstrip("\n").split("\t")
            if p[1] in ("movie", "tvMovie") and p[0] in rat:
                rt = int(p[7]) if p[7].isdigit() else None
                mv[p[0]] = (p[2], p[3], int(p[5]) if p[5].isdigit() else None, p[8], rt) + rat[p[0]]
    idx = {}
    for t, row in mv.items():
        for n in {norm(row[0]), norm(row[1])}:
            idx.setdefault(n, set()).add(t)
    with gzip.open(f"{d}/title.akas.tsv.gz", "rt", encoding="utf8") as f:
        next(f)
        for line in f:
            p = line.split("\t", 5)
            if p[0] in mv and p[3] in ("FR", "BE", "CA", "\\N", "XWW"):
                idx.setdefault(norm(p[2]), set()).add(p[0])
    by_year = {}
    for n, ids in idx.items():
        for t in ids:
            by_year.setdefault(mv[t][2], set()).add(n)
    pickle.dump({"mv": mv, "idx": {k: list(v) for k, v in idx.items()},
                 "by_year": {k: list(v) for k, v in by_year.items()}}, open(f"{d}/movies.pkl", "wb"))
    print(f"{len(mv)} movies, {len(idx)} titles")


def clean_title(t):
    t = re.sub(r"^\W*[|I\[]?(FR|EN|IFR|IEN)[|\]]\s*", "", t)  # |FR| prefix (OCR: IFR|, |FR], ...)
    t = re.sub(r"\s*\|\s*(19|20)\d\d\s*$", "", t)  # "Sinners | 2025"
    t = re.sub(r"\((UHD|4K|FHD|HD|MULTI|VOST)[^)]*\)?", "", t, flags=re.I)
    t = re.sub(r"[^\w' :&-]+$", "", t)              # OCR junk at the end
    return t.strip()


def variants(title):
    """Title spellings to try: as read, with a split French elision (LAccuse -> L Accuse),
    and without a leading article."""
    n = norm(title)
    out = [n]
    m2 = re.match(r"^([ldj])([aeiouyh]\w+)(.*)$", n)
    if m2:
        out.append(f"{m2.group(1)} {m2.group(2)}{m2.group(3)}")
    for v in list(out):
        out.append(re.sub(r"^(the|les|le|la|l|un|une|a) ", "", v))
    return list(dict.fromkeys(out))


def match(db, item):
    raw = item.get("title", "")
    title, year, rt = clean_title(raw), item.get("year"), item.get("runtime")
    if not year:  # meta line not captured: use "| 2026" in the title, if any
        ty = re.search(r"\|\s*((19|20)\d\d)\s*$", raw)
        year = int(ty.group(1)) if ty else None
        item["year"] = year
    truncated = raw.rstrip().endswith(("...", "…", ".."))
    years = {year - 1, year, year + 1} if year else None
    ok_year = lambda t: not years or db["mv"][t][2] in years
    cands, how = [], "exact"
    for n in variants(title.rstrip(". …")):
        cands = [t for t in db["idx"].get(n, []) if ok_year(t)]
        if cands:
            break
    pool = {x for y in years for x in db["by_year"].get(y, [])} if years else set()
    if not cands and truncated and years:
        pre = norm(title.rstrip(". …"))
        if len(pre) >= 6:
            cands = [t for x in pool if x.startswith(pre) for t in db["idx"][x] if ok_year(t)]
            how = "prefix"
    if not cands and years:
        for n in variants(title):
            if len(n) < 3:
                continue
            close = difflib.get_close_matches(n, pool, n=3, cutoff=0.85)
            cands = [t for c in close for t in db["idx"][c] if ok_year(t)]
            if cands:
                how = "fuzzy"
                break
    if not cands:
        return None
    def key(t):
        row = db["mv"][t]
        dr = abs((row[4] or 0) - rt) if rt and row[4] else 30
        return (dr > 12, dr, -row[6])
    t = sorted(cands, key=key)[0]
    row = db["mv"][t]
    if rt and row[4] and abs(row[4] - rt) > 20 and how != "exact":
        return None  # runtime too different for a loose title match
    return {"imdb": t, "imdb_title": row[0], "imdb_original": row[1], "imdb_year": row[2],
            "imdb_genres": row[3], "imdb_runtime": row[4], "rating": row[5], "votes": row[6], "how": how}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--build")
    ap.add_argument("--index")
    ap.add_argument("--min", type=float, default=7.0)
    ap.add_argument("--min-votes", type=int, default=500)
    ap.add_argument("--exclude", default="Documentary")
    ap.add_argument("items", nargs="?")
    a = ap.parse_args()
    if a.build:
        return build(a.build)
    db = pickle.load(open(a.index, "rb"))
    excl = {g.strip() for g in a.exclude.split(",") if g.strip()}
    for line in open(a.items):
        item = json.loads(line)
        r = match(db, item)  # may fill item["year"] from the title
        out = {"n": item["n"], "category": item.get("category"), "title": clean_title(item["title"]),
               "raw_title": item["title"], "year": item.get("year"),
               "genres_app": item.get("genres"), "runtime": item.get("runtime")}
        if r:
            out.update(r)
            genres = set(r["imdb_genres"].split(","))
            app = (item.get("genres") or "").lower() + " " + (item.get("category") or "").lower()
            narrative = {"Drama", "Comedy", "Romance", "Fantasy", "Action", "Adventure", "Crime",
                         "Thriller", "Horror", "Sci-Fi", "Family", "Animation", "Mystery", "War",
                         "Western", "History", "Biography"}
            concert = "Music" in genres and not (genres & narrative)
            doc = (bool(genres & excl) or concert
                   or any(w in app for w in ("documentaire", "concert", "spectacle")))
            out["keep"] = (r["rating"] > a.min and r["votes"] >= a.min_votes and not doc
                           and bool(item.get("year")))  # no year: too risky, review by hand
            out["excluded"] = "documentary/concert/show" if doc else None
        else:
            out["keep"] = None
        print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    main()
