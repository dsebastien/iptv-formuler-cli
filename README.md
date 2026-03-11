# formuler-remote

CLI remote control for Formuler Z11 Pro MAX IPTV box via ADB.

Single-file Python script, zero dependencies beyond stdlib. Control your Formuler box from the terminal — tune channels, play movies, browse series, manage favorites, and more.

## Features

- **Full remote control** — all keys: navigation, playback, volume, channels, digits
- **Live TV** — tune by name or channel number, search channels, fuzzy matching
- **VOD** — search and play movies with a single command
- **Series** — play specific episodes (e.g., S2E5), browse seasons
- **Favorites** — toggle star on any content from the CLI
- **EPG** — view program guide, search EPG listings
- **Channel database** — local cache with full enumeration (A-Z prefix scan)
- **Macros** — save and replay command sequences
- **Timed actions** — schedule commands at specific times
- **Interactive REPL** — tab completion, command history, colored output
- **JSON output** — `--json` flag for scripting and integration
- **Auto-reconnect** — handles dropped ADB connections transparently
- **CEC control** — power TV on/off through the Formuler box
- **Screen capture** — screenshots and screen recording
- **Config file** — customizable IP, macros, cache settings

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
   ```
3. **Enable ADB on your Formuler**: Settings > System > Developer Options > ADB Debugging > ON
4. **Note your device IP**: Settings > Network

## Quick Start

```bash
# Clone
git clone https://github.com/dsebastien/iptv-formuler-cli.git
cd iptv-formuler-cli

# Make executable
chmod +x formuler-remote.py

# Interactive mode (connects to default IP or config IP)
./formuler-remote.py

# Or specify your device IP
./formuler-remote.py 192.168.0.100

# One-shot commands
./formuler-remote.py tune TF1
./formuler-remote.py play-movie "batman"
./formuler-remote.py play-series "breaking bad" 2 3   # S02E03
```

## Usage

### One-Shot Commands

```bash
# Live TV
./formuler-remote.py tune "BFM TV"         # tune by name
./formuler-remote.py tune 42               # tune by channel number (requires refresh-all)
./formuler-remote.py search france          # search channels

# VOD
./formuler-remote.py play-movie batman     # search & play first match
./formuler-remote.py search-vod batman     # search movies on device

# Series
./formuler-remote.py play-series "breaking bad" 1 4   # play S01E04
./formuler-remote.py search-series "walking dead"

# Favorites
./formuler-remote.py star                  # toggle star on current page
./formuler-remote.py star-vod batman       # find & star a movie

# Navigation
./formuler-remote.py section vod           # switch to VOD section
./formuler-remote.py up                    # send key press
./formuler-remote.py ok                    # send OK/Enter

# JSON output for scripting
./formuler-remote.py --json search TF1
./formuler-remote.py --json categories
```

### Interactive Mode

```bash
./formuler-remote.py
```

Features tab completion, command history (persisted across sessions), and colored output. Type `help` for the full command reference.

### Command Reference

| Category | Command | Description |
|----------|---------|-------------|
| **Navigation** | `up`, `down`, `left`, `right`, `ok`, `back`, `home`, `menu` | Remote key presses |
| **Playback** | `play`, `pause`, `play-pause`, `stop`, `rewind`, `fast-forward` | Media controls |
| **Volume** | `volume-up`, `volume-down`, `mute` | Volume controls |
| **Channels** | `channel-up`, `channel-down`, `channel <number>` | Channel navigation |
| **Sections** | `section <name>` | Switch section (live/vod/series/radio/recordings) |
| | `browse <section>` | Open section for browsing |
| **Live TV** | `tune <name\|number>` | Tune by name or channel number |
| | `search <query>` | Search local DB + device |
| | `list [filter]` | List favorites/history |
| | `list-all [filter]` | List all enumerated channels |
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
| **Macros** | `macro <name>` | Run a saved macro |
| | `macros` | List available macros |
| | `at <HH:MM> <command>` | Schedule a command |
| | `timers` | List pending timers |
| | `cancel-timer <index>` | Cancel a timer |
| **Advanced** | `repeat <key> <count>` | Press key N times |
| | `cec <on\|off\|standby>` | TV power via CEC |
| | `record [duration] [path]` | Screen record |
| **General** | `type <text>` | Type text on device |
| | `open <app>` | Launch app |
| | `apps` | List installed apps |
| | `screenshot [path]` | Capture screen |
| | `status` | Show device info |
| | `reboot` | Reboot device |
| | `refresh` | Reload favorites/history cache |
| | `refresh-all` | Rebuild full channel database |

## Configuration

Create `~/.config/formuler-remote/config.toml` (Python 3.11+) or `config.json`:

```toml
[device]
ip = "192.168.0.100"
port = 5555

[cache]
channels_max_age_hours = 24

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
  "macros": {
    "morning": "open mytv; wait 3; tune BFM TV",
    "news": "tune BFM TV"
  }
}
```

## How It Works

- **Transport**: ADB (Android Debug Bridge) over TCP/IP — no USB cable needed
- **Live TV**: Deep link intents to the MyTVOnline app for instant channel switching
- **VOD/Series**: UI automation via ADB key events (search → select → play)
- **Channel data**: Content providers (`formuler.media.tv` for favorites/history, `searchProvider` for full channel list)
- **No root required**: Standard ADB debugging is sufficient
- **No credentials**: Channel tuning uses device intents, not IPTV credentials

## Device Compatibility

Developed and tested on **Formuler Z11 Pro MAX** running Android 11 with MyTVOnline 3. Should work with other Formuler devices running MOL3 (MyTVOnline 3), though UI navigation timings may need adjustment.

## Known Limitations

- **VOD/Series deep links don't work** — content must be navigated via UI automation
- **Screenshots during video playback show green** — DRM/secure surface protection
- **Search provider returns max ~10 results** per query
- **EPG data cannot be extracted programmatically** — the EPG commands open the UI and take screenshots
- **Device UI is in French** — the script handles French-language UI elements

## License

MIT
