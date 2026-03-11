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
- Install the Claude Code skill to `~/.claude/skills/formuler-remote/`

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
```

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

[aliases]
tf1 = "TF1 HD"
bfm = "BFM TV"
france2 = "France 2 HD"

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

## Device Compatibility

Developed and tested on **Formuler Z11 Pro MAX** running Android 11 with MyTVOnline 3. Should work with other Formuler devices running MOL3 (MyTVOnline 3), though UI navigation timings may need adjustment.

## Known Limitations

- **VOD/Series deep links don't work** — content must be navigated via UI automation
- **Screenshots during video playback show green** — DRM/secure surface protection
- **Search provider returns max ~10 results** per query
- **EPG data cannot be extracted programmatically** — the EPG commands open the UI and take screenshots
- **Device UI is in French** — the script handles French-language UI elements
- **M3U export has no stream URLs** — only channel metadata (the CLI uses intents, not direct streams)

## License

MIT
