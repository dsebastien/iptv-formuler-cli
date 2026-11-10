---
name: formuler-remote
description: Controls a Formuler Z11 Pro MAX IPTV box via the formuler-remote CLI. Use when the user wants to control their TV, tune channels, play movies or series, manage favorites, check EPG, browse VOD/series, run macros, set sleep timers, or interact with the Formuler device. Triggers on tune, channel, play movie, play series, EPG, guide, VOD, IPTV, Formuler, remote control, TV control, watch, star, favorite, macro, sleep timer, last channel, previous channel.
allowed-tools: Bash
---

# Formuler Remote Control

Controls a Formuler Z11 Pro MAX IPTV box via ADB using the `formuler-remote` CLI (75+ commands).
Uses direct deeplinks via the Android content provider for instant VOD/series playback (<5s).

## Critical Rules

1. ALWAYS use `--json --first` flags for non-interactive operation
2. ALWAYS add `--yes` when running destructive commands (reboot)
3. Check exit code — 0 means success, non-zero means failure
4. Parse the JSON envelope: `{"ok": true, "message": "...", "data": ...}` or `{"ok": false, "error": "..."}`
5. Run `formuler-remote --json commands` to discover available commands before guessing
6. NEVER run the CLI without flags in a non-interactive context (it launches a REPL)
7. All commands return proper JSON in `--json` mode — every success has a message/data, every error sets exit code 1
8. Use `ping` to verify device connectivity before running commands
9. Fuzzy matching is built in — "tf1" matches "TF 1", accents are ignored, shorter names are preferred
10. Chain commands with `;` in a single invocation: `formuler-remote --json --first 'tune TF1 ; wait 3 ; screenshot'`

## Quick Reference

| Task | Command |
|------|---------|
| Tune channel | `formuler-remote --json --first tune "BFM TV"` |
| Tune by number | `formuler-remote --json --first tune 42` |
| Retune last channel | `formuler-remote --json last` |
| Swap to previous channel | `formuler-remote --json prev` |
| Show tune history | `formuler-remote --json tune-history` |
| Play movie | `formuler-remote --json --first play-movie "batman"` |
| Play series episode | `formuler-remote --json --first play-series "breaking bad" 2 3` |
| Search channels | `formuler-remote --json search france` |
| List all channels | `formuler-remote --json list-all` |
| Channel info | `formuler-remote --json channel-info 42` |
| Device status | `formuler-remote --json status` |
| Ping device | `formuler-remote --json ping` |
| Screenshot | `formuler-remote --json screenshot /tmp/screen.png` |
| EPG info | `formuler-remote --json epg` |
| Open guide | `formuler-remote --json guide` |
| VOD history | `formuler-remote --json vod-history` |
| Resume last | `formuler-remote --json --first resume vod` |
| Wake device | `formuler-remote --json wake` |
| Power off | `formuler-remote --json power-off` |
| Sleep timer | `formuler-remote --json sleep-timer 90` |
| Sleep at time | `formuler-remote --json sleep-at 23:30` |
| Cancel sleep | `formuler-remote --json sleep-cancel` |
| Export M3U | `formuler-remote --json export-m3u channels.m3u` |
| Watch screenshots | `formuler-remote --json watch 5 /tmp` |
| Chain commands | `formuler-remote --json --first 'tune TF1 ; wait 5 ; screenshot'` |
| List commands | `formuler-remote --json commands` |
| Send key | `formuler-remote --json ok` |
| Navigate | `formuler-remote --json up` / `down` / `left` / `right` |
| Volume | `formuler-remote --json volume-up` / `volume-down` / `mute` |

## Flags

| Flag | Description |
|------|-------------|
| `--json` | Structured JSON output |
| `--first` | Auto-select first match |
| `--yes` | Skip confirmation prompts |
| `--wait <N>` | Sleep N seconds after command |
| `--timeout <N>` | Override ADB timeout (default 10s) |
| `--verbose` | Print ADB commands to stderr |
| `--dry-run` | Show ADB commands without executing (implies --verbose) |
| `-V` / `--version` | Print version and exit |

## Command Chaining

Chain multiple commands with `;` in a single invocation:

```bash
formuler-remote --json --first 'tune TF1 ; wait 5 ; screenshot'
formuler-remote --json --first 'volume-up ; volume-up ; volume-up'
```

`wait N` is handled inline within chains. This avoids multiple subprocess calls and reconnect overhead.

## Batch Mode

Pipe multiple commands via stdin (one per line, `#` for comments):

```bash
echo -e "tune TF1\nwait 3\nscreenshot" | formuler-remote --json --first
```

## Workflow

### Tuning a channel

1. Ping first to verify connectivity:
   ```bash
   formuler-remote --json ping
   ```
2. Search if unsure about the exact name:
   ```bash
   formuler-remote --json search "TF1"
   ```
3. Tune (fuzzy matching handles partial/accented names, shorter names preferred):
   ```bash
   formuler-remote --json --first tune "TF1"
   ```
4. Quick-switch back to previous channel:
   ```bash
   formuler-remote --json prev
   ```

### Playing VOD/Series content

```bash
formuler-remote --json --first play-movie "batman"
formuler-remote --json --first play-series "breaking bad" 2 5
```

**Fast path (v1.2.0+):** `play-movie` and `play-series` now use deeplinks via the content provider.
If the content is in favorites/history, it fires a direct intent to SchemeLinkActivity (~1-2 ADB commands, <5s).
Falls back to UI search only when content is not in the cache. No screenshots needed in the fast path.

### Watch history

```bash
formuler-remote --json vod-history              # all history (default 20 entries)
formuler-remote --json vod-history 5            # last 5 entries
formuler-remote --json vod-history batman        # filter by query
```

Shows VOD and series watch history from the device's content provider.
For series, includes last-watched season/episode.

### Sleep timer

```bash
formuler-remote --json sleep-timer 90       # auto-off in 90 minutes
formuler-remote --json sleep-at 23:30       # auto-off at 11:30 PM
formuler-remote --json sleep-cancel         # cancel
```

### Building the channel database

First run requires enumeration:
```bash
formuler-remote --json refresh-all
```
After that, `list-all`, `tune` by number, and `export-m3u` work from cache.

### Macros and chaining

```bash
formuler-remote --json macros                                    # list available
formuler-remote --json macro morning                             # run one
formuler-remote --json --first 'wake ; tune BFM TV ; wait 3 ; screenshot'  # ad-hoc chain
```

### Channel aliases

Configure in `~/.config/formuler-remote/config.toml`:
```toml
[aliases]
tf1 = "TF1 HD"
bfm = "BFM TV"
```
Then: `formuler-remote --json --first tune tf1`

### Debugging

```bash
formuler-remote --dry-run play-series "breaking bad" 2 3   # preview ADB commands
formuler-remote --verbose --json --first tune "TF1"        # see ADB commands + execute
```

## JSON Output Format

All commands with `--json` return:
```json
{"ok": true, "message": "Human-readable status", "data": <command-specific>}
```
On error:
```json
{"ok": false, "error": "Description of what went wrong"}
```

## Environment

The device IP must be set via one of:
- `FORMULER_IP` environment variable
- `.env` file with `FORMULER_IP=<ip>`
- `~/.config/formuler-remote/config.toml` or `config.json`
- First CLI argument: `formuler-remote --json 192.168.0.100 status`

## Configurable Timing

Device navigation speed can be tuned in config:
```toml
[timing]
nav_delay = 0.25    # seconds between key presses (default 0.25)
load_delay = 2.0    # seconds after opening screens (default 2.0)
search_delay = 1.5  # seconds after search input (default 1.5)
```

## Key Names

Navigation: `up`, `down`, `left`, `right`, `ok`, `back`, `home`, `menu`
Playback: `play`, `pause`, `play-pause`, `stop`, `rewind`, `fast-forward`
Volume: `volume-up`, `volume-down`, `mute`
Channels: `channel-up`, `channel-down`
Digits: `0`-`9`
Other: `info`, `guide`, `record`, `delete`, `tab`, `power`, `wakeup`, `sleep`

## Available Sections

`live` (or `tv`), `vod` (or `movies`), `series`, `radio`, `matchday`, `recordings`, `schedule`, `content`, `notifications`, `settings`

## Known Apps

`mytv`, `youtube`, `netflix`, `plex`, `kodi`, `vlc`, `prime`, `disney`, `settings`

## MyTVOnline 4 (MOL4) on the Z11: favorites, catalog scans, recovery

On 2026-11-10 the Z11 updated `tv.formuler.mol3.real` to 12.2.5, which is **MyTVOnline 4 under the
MOL3 package name**. The CLI commands above were built for MOL3; on MOL4 the key sequences for
search and star are different, and the favorites/history rows in `formuler.media.tv` restart empty.
Use the `mol4` tools for MOL4. `install.sh` installs them as `formuler-mol4-star`,
`formuler-mol4-scan`, `formuler-mol4-collect` and `formuler-imdb-match` (same options as the
`mol4_star.py`, `mol4_scan.py`, `mol4_collect.py` and `imdb_match.py` scripts used below). They need `adb`, `tesseract`, ImageMagick and
NumPy, and the box IP in `FORMULER_IP` (or `--ip`).

**Use `--scrcpy` (needs the `scrcpy` package and PyAV).** `adb shell input keyevent` starts a Java
process per call (~1 s on the Z11) and `screencap` takes ~2 s per image. `mol4_scrcpy.py` runs the
scrcpy server once: keys go through its control socket in milliseconds and the screen arrives as
H.264, so a frame is free. Live video still shows as black.

### What MOL4 does and does not expose

- No text in `uiautomator dump`, and `tv.formuler.mytvonline.provider` requires the signature
  permission `tv.formuler.molprovider.ACCESS`. `adb backup` returns an empty archive (47 bytes).
  The app database is not readable without root. Do not try to root the box; unlocking the
  bootloader wipes the data partition.
- `content://formuler.media.tv/preview_program` (launcher rows) is readable and gives deep-link
  intents (`SchemeLinkActivity` with `vod_unique_id`).
- Screenshots work on menu and detail screens (`exec-out screencap -p`). Live video is a plain
  green image.
- The update can switch **network debugging off**: turn it on again after every MOL update.
- Never "Clear data" or reinstall MOL after an update that lost favorites: the old database may
  still be on the box (276 MB in the 2026-11-10 case) and only Formuler can migrate it.

### Star series or movies: `mol4_star.py`

```bash
python3 mol4_star.py --type series "Silo" "Les Simpson"            # star (best quality: UHD/4K > FHD > MULTI > HD)
python3 mol4_star.py --type series --prefer MULTI "Battlestar Galactica"
python3 mol4_star.py --type series "robot=>Mr Robot"               # search text => expected title
python3 mol4_star.py --type vod "odyssee=>L Odyssee"
python3 mol4_star.py --unstar --type series "arrow=>Allen v Farrow"
python3 mol4_star.py --dry-run ...                                  # read the star, do not press
python3 mol4_star.py --scrcpy ...                                   # much faster (see above)
```

One JSON line per title: `starred`, `already`, `unstarred`, `not-in-catalog`, `no-match` (with the
OCR'd titles it saw), `focus-failed`, `search-failed`. About 15 s per title.

How it works, and the traps it handles (each one caused a wrong star during the first run):

1. **The star is a toggle.** Read the star before pressing: the focused button's center pixel is
   white when filled, red when empty. The button row moves up or down with the description length.
2. **Poster star badges are stale** (search results are cached). Never skip a title because of the
   yellow badge; always open it and read the real star. Yellow posters (Pluribus) also look like badges.
3. **Search field focus:** exactly one UP from the tabs (two from a card) gives the field with a
   cursor. A further UP removes the cursor and typing goes nowhere. Never press OK on the field:
   it can submit the old text. Check the field text with OCR after typing.
4. **App search needs the catalog's characters:** "Mr Robot" finds nothing, "robot" finds
   "Mr. Robot". Use `search=>expected title`.
5. **Matching:** exact title first, then "title starts with the query"; a one-word query never
   matches inside a longer title ("Sherlock" must not pick "Young Sherlock", "Arrow" must not pick
   "Allen v. Farrow"). French catalog titles: Les Simpson, Les Soprano, Rick et Morty, Désenchantée,
   Dr House, Formula 1 : Pilotes de leur destin, L'Accusé (= Contratiempo / The Invisible Guest).
6. **The results row keeps the scroll of the previous search:** DOWN, LEFT x12, UP before reading
   the cards, so card i is in slot i.
7. **Focus check by poster image,** not OCR: the focused card's title scrolls (marquee). The focus
   frame is two thin red vertical lines one card apart; red posters ("Love, Death & Robots") fool a
   plain red-pixel search.
8. **VOD search can load for more than 10 s** (spinner): wait up to 35 s for cards or
   "Pas de contenu" before reading results.
9. `open_search()`: UsActivity is not exported. Deep-link a title page from `preview_program`
   **without** `season_id`/`episode_id`, then UP, RIGHT, OK on its search icon.

### Scan VOD categories: `mol4_scan.py` + `mol4_collect.py`

```bash
python3 mol4_scan.py "3=FILMS RECENTS" "4=BOX-OFFICE 2025" "35=FILMS 4K UHD" > items.jsonl
```

`INDEX` counts from "Favoris" = 0 in the VOD left menu (Favoris, Historique, Ajouts récents, then
the provider categories; the list wraps around, so never press UP to "reach the top"). About 2.5 s
per movie. Traps:

- A plain relaunch restores the last screen: `am force-stop` first (keeps the data).
- After a fresh start the first selected category stays a grey skeleton: select the previous entry
  and come back, then wait until the header shows a year (dimmed text: OCR threshold 70).
- The header title turns into a logo image ~1 s after focus. Take the title screenshot on the box
  in the same shell call as the key press (`input keyevent 22; screencap -p ...`), then read the
  meta line from a second screenshot.
- "Ajouts récents" is a single row with logos; prefer the category grids (7 per row).
- At its end the grid wraps to the top: stop when a title fingerprint repeats.
- `INDEX=NAME@SKIP` resumes a category at item SKIP.

### Do not touch the provider portal

The Stalker portal checks more than the MAC (it answers `UDONTHAVEACCESS` to a non-box client).
Login attempts from another device with the box MAC can get the home IP blocked for hours, which
cuts the box off too. Work through the box UI only.

### Filter by IMDb rating: `imdb_match.py`

```bash
python3 imdb_match.py --build DIR                         # DIR has title.{ratings,basics,akas}.tsv.gz from datasets.imdbws.com
python3 imdb_match.py --index DIR/movies.pkl items.jsonl --min 7 > matched.jsonl
```

Matches on title (primary, original, FR/BE/CA AKAs, split elision "LAccusé" -> "L Accusé",
truncated "..." prefix), year +/- 1, runtime. `keep` = rating > min, >= 500 votes, not
documentary/concert/show (Music without a narrative genre counts as a concert). The app shows
TMDb %, not IMDb.
