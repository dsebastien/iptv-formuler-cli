---
name: formuler-remote
description: Controls a Formuler Z11 Pro MAX IPTV box via the formuler-remote CLI. Use when the user wants to control their TV, tune channels, play movies or series, manage favorites, check EPG, browse VOD/series, run macros, set sleep timers, or interact with the Formuler device. Triggers on tune, channel, play movie, play series, EPG, guide, VOD, IPTV, Formuler, remote control, TV control, watch, star, favorite, macro, sleep timer, last channel, previous channel.
allowed-tools: Bash
---

# Formuler Remote Control

Controls a Formuler Z11 Pro MAX IPTV box via ADB using the `formuler-remote` CLI (75 commands).

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
