---
name: formuler-remote
description: Controls a Formuler Z11 Pro MAX IPTV box via the formuler-remote CLI. Use when the user wants to control their TV, tune channels, play movies or series, manage favorites, check EPG, browse VOD/series, run macros, or interact with the Formuler device. Triggers on tune, channel, play movie, play series, EPG, guide, VOD, IPTV, Formuler, remote control, TV control, watch, star, favorite, macro.
allowed-tools: Bash
---

# Formuler Remote Control

Controls a Formuler Z11 Pro MAX IPTV box via ADB using the `formuler-remote` CLI.

## Critical Rules

1. ALWAYS use `--json --first` flags for non-interactive operation
2. ALWAYS add `--yes` when running destructive commands (reboot)
3. Check exit code — 0 means success, non-zero means failure
4. Parse the JSON envelope: `{"ok": true, "data": ...}` or `{"ok": false, "error": "..."}`
5. Run `formuler-remote --json commands` to discover available commands before guessing
6. NEVER run the CLI without flags in a non-interactive context (it launches a REPL)

## Quick Reference

| Task | Command |
|------|---------|
| Tune channel | `formuler-remote --json --first tune "BFM TV"` |
| Tune by number | `formuler-remote --json --first tune 42` |
| Play movie | `formuler-remote --json --first play-movie "batman"` |
| Play series episode | `formuler-remote --json --first play-series "breaking bad" 2 3` |
| Search channels | `formuler-remote --json search france` |
| List all channels | `formuler-remote --json list-all` |
| Channel info | `formuler-remote --json channel-info 42` |
| Device status | `formuler-remote --json status` |
| Screenshot | `formuler-remote --json screenshot /tmp/screen.png` |
| EPG info | `formuler-remote --json epg` |
| Open guide | `formuler-remote --json guide` |
| Resume last | `formuler-remote --json --first resume vod` |
| List commands | `formuler-remote --json commands` |
| Send key | `formuler-remote --json ok` |
| Navigate | `formuler-remote --json up` / `down` / `left` / `right` |
| Volume | `formuler-remote --json volume-up` / `volume-down` / `mute` |

## Workflow

### Tuning a channel

1. Search first if unsure about the exact name:
   ```bash
   formuler-remote --json search "TF1"
   ```
2. Tune using the result:
   ```bash
   formuler-remote --json --first tune "TF1"
   ```
3. Verify with status:
   ```bash
   formuler-remote --json status
   ```

### Playing VOD/Series content

1. Search to confirm availability:
   ```bash
   formuler-remote --json search-vod "batman"
   ```
2. Play:
   ```bash
   formuler-remote --json --first play-movie "batman"
   ```
3. For series with specific episode:
   ```bash
   formuler-remote --json --first play-series "breaking bad" 2 5
   ```

### Building the channel database

First run requires enumeration (takes a few minutes):
```bash
formuler-remote --json refresh-all
```
After that, `list-all` and `tune` by number work instantly from cache.

### Macros

Run predefined command sequences from the user's config:
```bash
formuler-remote --json macros          # list available
formuler-remote --json macro morning   # run one
```

## JSON Output Format

All commands with `--json` return:
```json
{"ok": true, "data": <command-specific>, "message": "Human-readable status"}
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
