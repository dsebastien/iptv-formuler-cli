# formuler-remote

CLI remote control for Formuler Z11 Pro MAX IPTV box via ADB.

Single-file Python script, zero dependencies beyond stdlib. Control your Formuler box from the terminal — tune channels, play movies, browse series, manage favorites, and more.

## Features

- **Full remote control** — all keys: navigation, playback, volume, channels, digits
- **Live TV** — tune by name or channel number, fuzzy matching, channel aliases
- **VOD** — search and play movies with a single command
- **Series** — play specific episodes (e.g., S2E5), browse seasons
- **Favorites** — toggle star on any content from the CLI
- **EPG** — view program guide, search EPG listings
- **Channel database** — local cache with full enumeration (A-Z prefix scan)
- **Fuzzy matching** — accent-insensitive, partial name matching ("tf1" matches "TF 1"), shorter names preferred
- **Channel aliases** — configure shortcuts in config file
- **Tune history** — `last`/`prev` for quick channel switching, persistent history
- **Command chaining** — chain commands with `;` in a single invocation
- **Sleep timer** — auto power-off after N minutes or at a specific time
- **Macros** — save and replay command sequences
- **Timed actions** — schedule commands at specific times
- **Batch mode** — pipe multiple commands via stdin for automation
- **Interactive REPL** — tab completion, command history, colored output
- **JSON output** — `--json` flag for scripting and integration
- **Agent-friendly** — structured JSON envelope, `--first`/`--yes` flags, exit codes, command schema
- **Claude Code skill** — included skill for AI-driven TV control
- **Auto-reconnect** — handles dropped ADB connections transparently
- **Retry logic** — exponential backoff on transient ADB errors
- **Dry-run mode** — preview ADB commands without executing
- **CEC control** — power TV on/off through the Formuler box
- **Screen capture** — screenshots and screen recording
- **Screen mirroring** — live view of the box on your computer via [scrcpy](https://github.com/Genymobile/scrcpy), with audio here or on the TV
- **Web remote** — `serve` gives a token-protected remote control page for phone/tablet on your network, including a live picture + sound stream ("Watch here")
- **Playback check** — `play-movie`/`play-series` only report success once the player is actually playing
- **M3U export** — export channel lineup as M3U playlist
- **Shell completions** — bash, zsh, and fish completion scripts
- **Configurable timing** — tune navigation delays for your device speed
- **Config file** — customizable IP, macros, aliases, timing, cache settings

## Prerequisites

1. **Python 3.10+** (uses stdlib only, no pip install needed)
2. **ADB** (Android Debug Bridge):
   ```bash
   # Arch Linux
   sudo pacman -S android-tools

   # Ubuntu/Debian
   sudo apt install adb

   # macOS
   brew install android-platform-tools

   # Windows
   winget install Google.PlatformTools
   ```
3. **Enable ADB on your Formuler**: Settings > System > Developer Options > ADB Debugging > ON
4. **Note your device IP**: Settings > Network

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/dsebastien/iptv-formuler-cli/main/install.sh | bash
```

This will:
- Check for Python 3.10+ and ADB (offering to install ADB if missing)
- Download the script to `~/.local/bin/` with a `formuler-remote` symlink
- Install the MyTVOnline 4 tools (see below) to `~/.local/share/formuler-remote/`, with their own
  Python environment (NumPy, PyAV) and the commands `formuler-mol4-star`, `formuler-mol4-scan`,
  `formuler-mol4-collect` and `formuler-imdb-match` in `~/.local/bin/`. It offers to install
  tesseract and ImageMagick (needed) and scrcpy (optional, much faster)
- Install the Claude Code skill to `~/.claude/skills/formuler-remote/`

Options: `--no-mol4` skips the MyTVOnline 4 tools, `--yes` answers yes to every prompt, and
`REF=v1.3.0` installs a release instead of `main`:

```bash
curl -fsSL https://raw.githubusercontent.com/dsebastien/iptv-formuler-cli/main/install.sh | REF=v1.3.0 bash -s -- --yes
```

Or install manually:

```bash
git clone https://github.com/dsebastien/iptv-formuler-cli.git
cd iptv-formuler-cli
chmod +x formuler-remote.py
cp formuler-remote.py ~/.local/bin/
# Optional: install Claude Code skill
mkdir -p ~/.claude/skills/formuler-remote
cp .claude/skills/formuler-remote/SKILL.md ~/.claude/skills/formuler-remote/
```

### Windows

`install.sh` needs bash; on Windows install manually (PowerShell):

```powershell
git clone https://github.com/BlazeForce-NL/iptv-formuler-cli.git
cd iptv-formuler-cli
pip install pyreadline3   # optional: tab completion + history in interactive mode
python formuler-remote.py <your-device-ip> ping
# Optional: install Claude Code skill
New-Item -ItemType Directory -Force "$HOME\.claude\skills\formuler-remote"
Copy-Item .claude\skills\formuler-remote\SKILL.md "$HOME\.claude\skills\formuler-remote\"
```

Notes:
- Screenshots, recordings and UI dumps default to `%TEMP%` instead of `/tmp`.
- Config and cache live in `%USERPROFILE%\.config\formuler-remote` and `%USERPROFILE%\.cache\formuler-remote`.
- Without `pyreadline3` the interactive mode works, but without tab completion and history.
- The single-instance lock is not enforced on Windows.

## Uninstall

```bash
curl -fsSL https://raw.githubusercontent.com/dsebastien/iptv-formuler-cli/main/install.sh | bash -s -- --uninstall
```

Or if you have the repo cloned:
```bash
./install.sh --uninstall
```

## Quick Start

```bash
# Set your device IP (or use .env file / config file)
export FORMULER_IP=<your-device-ip>

# Interactive mode
formuler-remote

# Or pass the IP directly
formuler-remote <your-device-ip>

# One-shot commands
formuler-remote tune TF1
formuler-remote play-movie "batman"
formuler-remote play-series "breaking bad" 2 3   # S02E03
```

## Usage

### One-Shot Commands

```bash
# Live TV
formuler-remote tune "BFM TV"             # tune by name (fuzzy match)
formuler-remote tune 42                   # tune by channel number (requires refresh-all)
formuler-remote search france             # search channels

# VOD
formuler-remote play-movie batman         # search & play first match
formuler-remote search-vod batman         # search movies on device

# Series
formuler-remote play-series "breaking bad" 1 4   # play S01E04
formuler-remote search-series "walking dead"

# Favorites
formuler-remote star                      # toggle star on current page
formuler-remote star-vod batman           # find & star a movie

# Navigation
formuler-remote section vod               # switch to VOD section
formuler-remote up                        # send key press
formuler-remote ok                        # send OK/Enter

# Channel switching
formuler-remote last                      # retune last channel
formuler-remote prev                      # swap to previous channel
formuler-remote tune-history              # show tune history

# Sleep timer
formuler-remote sleep-timer 90            # auto-off in 90 minutes
formuler-remote sleep-at 23:30            # auto-off at 11:30 PM
formuler-remote sleep-cancel              # cancel sleep timer

# Command chaining
formuler-remote --json --first 'tune TF1 ; wait 5 ; screenshot'

# Convenience
formuler-remote wake                      # CEC wakeup + launch MyTV
formuler-remote power-off                 # CEC sleep + disconnect
formuler-remote ping                      # check device connectivity
formuler-remote export-m3u channels.m3u   # export channel lineup

# Screen mirroring (needs scrcpy: winget install Genymobile.scrcpy / brew install scrcpy)
formuler-remote mirror                    # video + audio on this computer
formuler-remote mirror --no-audio         # video here, sound stays on the TV
formuler-remote mirror --fullscreen       # start fullscreen
# On Android 11 (Z11 Pro MAX) audio forwarding mutes the TV; closing the window restores it.
```

### Web Remote

Control the box from a phone, tablet or browser on the same network:

```bash
formuler-remote serve            # LAN, port 8765
formuler-remote serve 9000       # other port
formuler-remote serve --local    # only this computer (127.0.0.1)
```

It prints a link like `http://192.168.0.185:8765/?t=…`. Open it on your phone and bookmark it. With an IPTV account configured, a switch at the top picks the mode: *📡 IPTV direct* (channels and the guide play on the phone, straight from the provider; tabs *Channels* and *Guide*) or *📺 TV* (they tune the box; tabs *Remote*, *Channels*, *Guide* and *Movies*, plus mirroring the TV screen). The player sits below it; the last mode and tab are remembered. The page has a D-pad, volume/channel keys, app buttons (MyTVOnline, YouTube, Prime Video), a channel grid with logos per country (Nederland, België, USA, Canada, Australië, Nieuw-Zeeland) with TV / 24/7 / Events / Radio filters (variants such as `NPO1 4K` / `NPO 1 FHD` / `NPO1 LQ` show as one tile that tunes the best quality; tick *All variants* to see them all), a play form for series/movies and mirror buttons. Arrow keys, Enter, Backspace, `+`/`-` and PageUp/PageDown work on a keyboard too.

- **Access token:** every request needs the token in the link. It is stored in `~/.cache/formuler-remote/web_token` so bookmarks survive restarts; delete that file to revoke old links.
- **Allowed commands:** the page can only run remote-control commands (tune, play, open, mirror, …), not `reboot`, `serve`, `watch` or `record`.
- **Speed:** key presses go through one persistent `adb shell`; other commands run one at a time through the CLI.
- **Watch here:** streams the box's picture and sound to the browser (needs [scrcpy](https://github.com/Genymobile/scrcpy) and [ffmpeg](https://ffmpeg.org/): `winget install Genymobile.scrcpy Gyan.FFmpeg`). scrcpy records the screen without a window, ffmpeg turns it into ~1s HLS segments, and the page plays them with [hls.js](https://github.com/video-dev/hls.js) (native HLS as fallback). The player stays a few segments behind the live edge so uneven delivery doesn't stall it: about 4s behind for the TV screen, 10–15s for provider channels. On Android 11 the TV is muted while streaming; **Stop** gives the sound back. The stream restarts itself every ~70 minutes to keep its temp file small.
- **Play on this device:** with an Xtream Codes account in `.env` (see [IPTV provider](#iptv-provider-optional)) the channel list gets a *Play on TV / Play on this device* switch. On this device, the server's ffmpeg pulls the channel straight from the provider and remuxes it to HLS (audio to AAC; channels tagged HEVC/H265 are re-encoded to 720p H.264), so you can watch something else than the TV. The current and next programme come from the provider's EPG. Many subscriptions allow one connection: when it's in use (usually by the TV) the page offers to put the TV to sleep first. The stream stops by itself about a minute after the last player went away.
- **Guide:** with `IPTV_EPG_LINK` (an XMLTV URL) next to the account in `.env`, the page shows a programme grid for the channels in the list (same country, type and filter), 6 hours per view from 3 hours back to about 30 hours ahead. Tap a programme for its description; one that's on now can be watched from there. The server downloads the XMLTV file in the background at most every 12 hours (it can be ~100 MB, a few minutes the first time) to `~/.cache/formuler-remote/epg.xml` and keeps an index in memory; channels are matched through the provider's `epg_channel_id`.
- **Channel tiles:** with the guide loaded, each tile shows the programme that's on now with a progress bar. Holding a tile for half a second (the touch version of hovering) shows a current frame of that channel in the tile, grabbed from the provider in about a second and cached for 3 minutes; a normal tap still tunes or plays. Previews are fetched one tile at a time on request, never for the whole list, so the provider doesn't see a burst of connections.
- **Programme search:** the Guide tab searches titles and descriptions of what's on now, later, or both, on the channels of all countries (e.g. `voetbal`). A programme that's on can be watched right away; ⏰ on a later one makes the server wake the box and tune the TV when it starts (also from a programme's details in the grid).
- **Movies & series on the phone:** in *IPTV direct* mode the *Movies* tab searches the provider's movie and series catalog (loaded on the first search, about a minute, then cached for a day in `~/.cache/formuler-remote/vod_*.json`). Series open a season/episode list. H.264 versions are passed through as they are; others are converted to 720p on the computer. 4K versions are marked: at ~20 Mbit/s they come in slower than real time from this provider and stutter, a normal version plays smoothly. Playback starts at the beginning and can be scrolled back.
- **Sleep timer:** 30 / 60 / 90 minutes or off, in the Remote tab. Runs in the server (the CLI's `sleep-timer` lives in its own process), puts the box to sleep and stops streams on the page. Timers are saved in `~/.cache/formuler-remote/web_timers.json` and survive a restart of `serve`.
- **Zapping:** while something plays on the page, *Previous/Next channel* steps through the channel list for a direct stream, or sends channel up/down to the box for the mirror.
- **Home screen:** the page has a web app manifest and icon, so *Add to Home Screen* gives it its own icon. On iPhone it opens full screen; Chrome on Android only opens it without the address bar over HTTPS, which `serve` doesn't do, so there it opens as a browser tab.
- **Windows:** allow Python through the firewall for private networks when asked, otherwise the phone can't connect.

### Interactive Mode

```bash
formuler-remote
```

Features tab completion, command history (persisted across sessions), and colored output. Type `help` for the full command reference.

### Command Chaining

Chain multiple commands with `;` in a single invocation:

```bash
formuler-remote --json --first 'tune TF1 ; wait 5 ; screenshot'
formuler-remote --json --first 'volume-up ; volume-up ; volume-up'
formuler-remote --json --first 'wake ; tune BFM TV ; wait 3 ; screenshot'
```

`wait N` is handled inline within chains. This avoids multiple subprocess calls and reconnect overhead.

### Batch Mode

Pipe commands via stdin for automation (one command per line, `#` for comments):

```bash
echo -e "tune TF1\nwait 3\nscreenshot" | formuler-remote --json --first
```

```bash
cat <<EOF | formuler-remote --json --first
# Morning routine
wake
tune BFM TV
wait 5
screenshot /tmp/morning.png
EOF
```

### Flags

| Flag | Description |
|------|-------------|
| `--json` | Structured JSON output (`{"ok": bool, "message"\|"error": ...}`) |
| `--first` | Auto-select first match instead of prompting |
| `--yes` | Skip confirmation prompts (e.g., reboot) |
| `--wait <N>` | Sleep N seconds after command completes |
| `--timeout <N>` | Override default ADB timeout (default 10s) |
| `--verbose` / `--debug` | Print ADB commands to stderr for debugging |
| `--dry-run` | Show ADB commands without executing (implies `--verbose`) |
| `-V` / `--version` | Print version and exit |
| `-h` / `--help` | Show usage information and exit |
| `--completions <shell>` | Print shell completion script (bash/zsh/fish) |

### Command Reference

| Category | Command | Description |
|----------|---------|-------------|
| **Navigation** | `up`, `down`, `left`, `right`, `ok`, `back`, `home`, `menu` | Remote key presses |
| **Playback** | `play`, `pause`, `play-pause`, `stop`, `rewind`, `fast-forward` | Media controls |
| **Volume** | `volume-up`, `volume-down`, `mute` | Volume controls |
| **Channels** | `channel-up`, `channel-down`, `channel <number>` | Channel navigation |
| **Sections** | `section <name>` | Switch section (live/vod/series/radio/recordings) |
| | `browse <section>` | Open section for browsing |
| **Live TV** | `tune <name\|number>` | Tune by name or channel number (fuzzy match) |
| | `last` | Retune last channel |
| | `prev` | Swap to previous channel |
| | `tune-history` | Show tune history |
| | `search <query>` | Search local DB + device |
| | `list [filter]` | List favorites/history |
| | `list-all [filter]` | List all enumerated channels |
| | `country [code] [filter]` | List countries, or all live channels of one (`nl be us ca au nz uk`) |
| | `tune-id <unique_id>` | Tune by provider channel id (from `country --json`) |
| | `channel-info <number>` | Show channel details |
| | `categories` | Show category counts |
| **VOD** | `search-vod <query>` | Search movies on device UI |
| | `play-movie <query>` | Search & play first match |
| | `stop-vod` | Stop with confirmation dialog |
| **Series** | `search-series <query>` | Search series on device UI |
| | `play-series <query> [S] [E]` | Play specific episode |
| | `episodes <query>` | Open episode browser |
| **Browsing** | `resume [vod\|series\|live]` | Resume last watched |
| | `info <query>` | Show content details |
| **EPG** | `epg [channel]` | Show EPG info overlay |
| | `guide` | Open full EPG guide |
| | `search-epg <query>` | Search program listings |
| | `now-playing` | Capture player log entries |
| **Favorites** | `star` | Toggle star on current page |
| | `star-vod <query>` | Find movie & toggle star |
| | `star-series <query>` | Find series & toggle star |
| **Sleep Timer** | `sleep-timer <minutes>` | Auto power-off after N minutes |
| | `sleep-at <HH:MM>` | Auto power-off at specific time |
| | `sleep-cancel` | Cancel sleep timer |
| **Macros** | `macro <name>` | Run a saved macro |
| | `macros` | List available macros |
| | `at <HH:MM> <command>` | Schedule a command |
| | `timers` | List pending timers |
| | `cancel-timer <index>` | Cancel a timer |
| **Export** | `export-m3u [path]` | Export channel lineup as M3U file |
| **Convenience** | `wake` | CEC wakeup + launch MyTVOnline |
| | `power-off` | CEC sleep + disconnect |
| | `history [count]` | Show recent command history |
| | `watch [interval] [dir]` | Screenshot every N seconds |
| **Advanced** | `repeat <key> <count>` | Press key N times |
| | `cec <on\|off\|standby>` | TV power via CEC |
| | `record [duration] [path]` | Screen record |
| **General** | `type <text>` | Type text on device |
| | `open <app>` | Launch app |
| | `apps` | List installed apps |
| | `screenshot [path]` | Capture screen |
| | `status` | Show device info |
| | `ping` | Check device connectivity |
| | `reboot` | Reboot device |
| | `refresh` | Reload favorites/history cache |
| | `refresh-all` | Rebuild full channel database |
| | `commands` | List all commands as JSON schema |

Get the full command schema programmatically:
```bash
formuler-remote --json commands
```

## AI Agent Integration

The CLI is designed to be efficient for AI agents (Claude Code, scripts, automation):

### Flags for automation

Always use `--json --first` for non-interactive operation:

```bash
# Structured JSON output with auto-selection
formuler-remote --json --first tune "BFM TV"

# Skip confirmations
formuler-remote --json --yes reboot

# Discover all commands programmatically
formuler-remote --json commands

# Check connectivity before running commands
formuler-remote --json ping
```

### JSON output format

All commands with `--json` return a consistent envelope:

```json
{"ok": true, "message": "Tuning to: BFM TV", "data": {"title": "BFM TV", ...}}
```

On error:
```json
{"ok": false, "error": "No channel matching 'xyz'"}
```

### Exit codes

- `0` — success
- `1` — error (command failed, device not found, etc.)

### Command chaining for agents

Chain commands with `;` to avoid multiple subprocess calls:
```bash
formuler-remote --json --first 'tune TF1 ; wait 5 ; screenshot'
```

### Batch mode for agents

Send multiple commands in a single invocation:
```bash
echo -e "ping\ntune TF1\nwait 3\nscreenshot" | formuler-remote --json --first
```

### Debugging

Preview ADB commands without executing:
```bash
formuler-remote --dry-run tune "TF1"           # preview commands
formuler-remote --verbose --json --first tune "TF1"  # see + execute
```

### Claude Code skill

The installer automatically installs a Claude Code skill to `~/.claude/skills/formuler-remote/`. This lets Claude control your TV naturally:

> "Tune to TF1"
> "Play the movie Batman"
> "What's the device status?"
> "Play Breaking Bad season 2 episode 5"

The skill teaches Claude to always use `--json --first --yes` flags, parse the JSON envelope, and check exit codes.

To install the skill manually:
```bash
mkdir -p ~/.claude/skills/formuler-remote
curl -fsSL https://raw.githubusercontent.com/dsebastien/iptv-formuler-cli/main/.claude/skills/formuler-remote/SKILL.md \
  -o ~/.claude/skills/formuler-remote/SKILL.md
```

## Shell Completions

Generate and install completion scripts:

```bash
# Bash
formuler-remote --completions bash >> ~/.bashrc

# Zsh
formuler-remote --completions zsh >> ~/.zshrc

# Fish
formuler-remote --completions fish > ~/.config/fish/completions/formuler-remote.fish
```

## Configuration

### Device IP / Hostname

The device address is resolved in this order (first match wins):

1. **CLI argument**: `formuler-remote 192.168.0.100 tune TF1`
2. **Environment variable**: `FORMULER_IP=192.168.0.100 formuler-remote tune TF1`
3. **`.env` file** (in current directory or `~/.config/formuler-remote/.env`):
   ```
   FORMULER_IP=192.168.0.100
   ```
4. **Config file** (see below)

### IPTV provider (optional)

For *Play on this device* in the web remote, add your provider's Xtream Codes login to the same `.env` file (kept local, never sent anywhere but the provider):
```
IPTV_SERVER=http://provider.example:8080
IPTV_USER=your-username
IPTV_PASS=your-password
IPTV_EPG_LINK=http://provider.example:8080/xmltv.php?username=...&password=...   # optional, for the guide
```
Channel tiles map to provider streams through the MyTVOnline channel id (`2_<group>_<stream>_0`), so it works for the channels the box lists.

### Config file

Create `~/.config/formuler-remote/config.toml` (Python 3.11+) or `config.json`:

```toml
[device]
ip = "192.168.0.100"
port = 5555

[cache]
channels_max_age_hours = 24

[timing]
nav_delay = 0.25
load_delay = 2.0
search_delay = 1.5
playback_timeout = 60

[aliases]
tf1 = "TF1 HD"
bfm = "BFM TV"
france2 = "France 2 HD"

# Extra countries for 'country' and the web remote: code = [name, [title prefixes]]
[countries]
de = ["Duitsland", ["DE"]]

[macros]
morning = "open mytv; wait 3; tune BFM TV"
news = "tune BFM TV"
movie-night = "section vod; wait 2"
```

JSON equivalent (`config.json`):
```json
{
  "device": {"ip": "192.168.0.100", "port": 5555},
  "cache": {"channels_max_age_hours": 24},
  "timing": {"nav_delay": 0.25, "load_delay": 2.0, "search_delay": 1.5},
  "aliases": {"tf1": "TF1 HD", "bfm": "BFM TV"},
  "macros": {
    "morning": "open mytv; wait 3; tune BFM TV",
    "news": "tune BFM TV"
  }
}
```

### Channel Aliases

Define aliases in the `[aliases]` section of your config file to create shortcuts for channel names:

```toml
[aliases]
tf1 = "TF1 HD"
bfm = "BFM TV"
```

Then use the alias: `formuler-remote tune tf1` will tune to "TF1 HD".

### Configurable Timing

Device navigation speed can be tuned in the `[timing]` section of your config file:

```toml
[timing]
nav_delay = 0.25    # seconds between key presses (default 0.25)
load_delay = 2.0    # seconds after opening screens (default 2.0)
search_delay = 1.5  # seconds after search input (default 1.5)
playback_timeout = 60  # max seconds to wait for VOD playback to start (default 60)
```

Useful if your device responds faster or slower than the defaults.

### Fuzzy Matching

Channel names support fuzzy matching:
- Accent-insensitive: "francais" matches "Fran\u00e7ais"
- Space-insensitive: "tf1" matches "TF 1"
- Partial match: "france" matches "France 2 HD", "France 3", etc.
- Token matching: "bfm tv" matches "BFM TV HD"

## How It Works

- **Transport**: ADB (Android Debug Bridge) over TCP/IP — no USB cable needed
- **Live TV**: Deep link intents to the MyTVOnline app for instant channel switching
- **VOD/Series**: UI automation via ADB key events (search -> select -> play)
- **Channel data**: Content providers (`formuler.media.tv` for favorites/history, `searchProvider` for full channel list)
- **Retry logic**: Transient ADB errors are retried with exponential backoff (0.5s, 1s, 2s)
- **Instance lock**: Only one CLI instance can run at a time (fcntl file lock)
- **No root required**: Standard ADB debugging is sufficient
- **No credentials**: Channel tuning uses device intents, not IPTV credentials

## MyTVOnline 4 tools

In November 2026 the Z11 updated `tv.formuler.mol3.real` to 12.2.5, which is **MyTVOnline 4** under
the MOL3 package name. MOL4 has a different UI and exposes no text to `uiautomator`, so the MOL3
key sequences of `formuler-remote` do not fit it. The `mol4` tools drive MOL4 from screenshots and
OCR. They need `FORMULER_IP`.

```bash
export FORMULER_IP=<your-device-ip>

# Star series or movies (reads the star first: the star is a toggle)
formuler-mol4-star --scrcpy --type series "Silo" "robot=>Mr Robot"
formuler-mol4-star --scrcpy --type vod --prefer MULTI "Battlestar Galactica"
formuler-mol4-star --scrcpy --unstar --type series "arrow=>Allen v Farrow"

# Scan VOD categories (INDEX counts from "Favoris" = 0 in the VOD menu)
formuler-mol4-scan "3=FILMS RECENTS" "4=BOX-OFFICE 2025" > movies.jsonl

# Keep the movies above 7 on IMDb (index built once from https://datasets.imdbws.com/)
formuler-imdb-match --build ./imdb
formuler-imdb-match --index ./imdb/movies.pkl movies.jsonl --min 7 > matched.jsonl
```

`--scrcpy` drives the box through scrcpy: key presses take milliseconds instead of ~1 s and frames
are free instead of ~2 s per screenshot. The Claude Code skill documents the MOL4 traps in detail.

## Device Compatibility

Developed and tested on **Formuler Z11 Pro MAX** running Android 11 with MyTVOnline 3 (`formuler-remote`) and MyTVOnline 4 (the `mol4` tools). Should work with other Formuler devices running MOL3 or MOL4, though UI navigation timings may need adjustment.

## Known Limitations

- **VOD/Series deep links don't work** — content must be navigated via UI automation
- **Screenshots during video playback show green** — DRM/secure surface protection
- **Search provider returns max ~10 results** per query
- **EPG data cannot be extracted programmatically** — the EPG commands open the UI and take screenshots
- **Device UI is in French** — the script handles French-language UI elements
- **M3U export has no stream URLs** — only channel metadata (the CLI uses intents, not direct streams)

## License

MIT
