# Phase 1: Error Handling Foundation

**Priority**: HIGH
**Status**: Planned
**Dependencies**: None (foundation phase)

## Problem

Commands call `info()` for success, which is a no-op in JSON mode. `_exit_code` only set by `error()`/`output_err()`. Agents get no response or a misleading `{"ok": true}`.

## Changes

### Replace `info()` with `output_ok()` in command functions

| Function | Current | New |
|----------|---------|-----|
| `play_movie` | `info(f"Playing movie: '{query}'")` | `output_ok(msg, {"query": query})` |
| `play_series` | `info(f"Playing {label}")` | `output_ok(msg, {"query": query, "season": s, "episode": e})` |
| `toggle_star` | `info("Star toggled.")` | `output_ok("Star toggled.")` |
| `star_search` | `info(f"Toggled star for '{query}'")` | `output_ok(msg)` |
| `stop_playback` | `info("Playback stopped.")` | `output_ok("Playback stopped.")` |
| `go_to_section` | `info(f"Switched to: {section}")` | `output_ok(f"Switched to: {section}")` |
| `cmd_browse` | `info(...)` | `output_ok(msg)` |
| `cmd_episodes` | `info(...)` | `output_ok(msg)` |
| `cmd_epg` | `info(...)` | `output_ok(msg, {"screenshot": path})` |
| `cmd_guide` | `info(...)` | `output_ok(msg, {"screenshot": path})` |
| `cmd_search_epg` | `info(...)` | `output_ok(msg)` |
| `screenshot` | `info(...)` | `output_ok(msg, {"path": path})` |
| `cmd_record_screen` | `info(...)` | `output_ok(msg, {"path": path})` |
| `cmd_repeat` | `info(...)` | `output_ok(msg)` |
| `cmd_cec` | `info(...)` | `output_ok(msg)` |
| `do_search` | `info(...)` | `output_ok(msg)` |
| `open_app` | `info(...)` | `output_ok(msg)` |
| `cmd_tune` (all paths) | `info(...)` | `output_ok(msg, channel_data)` |

### Keep `info()` for intermediate progress

- "Launching MyTVOnline..."
- "Connection lost. Reconnecting..."
- "Recording for Ns..."
- "Running macro: ..."
- "Cached N channels"

### Check ADB return codes

- `key()`: Check return code of `adb()`, call `output_err()` on failure
- `screenshot()`: Check return codes of screencap and pull operations

## Files Modified

- `formuler-remote.py` (~30 sites)
- `SKILL.md` (note JSON consistency)
- `README.md` (JSON output section)

## Verification

1. `python3 -c "import py_compile; py_compile.compile('formuler-remote.py', doraise=True)"`
2. `./formuler-remote.py --json commands` — verify commands appear
