# Phase 5: Convenience Commands

**Priority**: LOW
**Status**: Planned
**Dependencies**: Phase 1

## Changes

### 1. `wake`

CEC wakeup + `ensure_mytv()`. Returns `output_ok("Device awake, MyTV running")`.

### 2. `power-off`

CEC sleep + disconnect. (Not named `sleep` — collision with KEYS dict entry.)

### 3. `history [count]`

Read readline history file (`CACHE_DIR/history`), show last N entries. JSON returns list of strings.

### 4. `watch [interval] [dir]`

Take screenshot every N seconds (default 5) to a directory. Run until Ctrl-C. In JSON mode, emit JSONL per screenshot.

Add all to COMMANDS, dispatch, completer, HELP_TEXT.

## Files Modified

- `formuler-remote.py` (new functions + dispatch)
- `SKILL.md` (add `wake`, `watch`)
- `README.md` (command table)

## Verification

1. `python3 -c "import py_compile; py_compile.compile('formuler-remote.py', doraise=True)"`
2. `./formuler-remote.py --json commands` — verify new commands appear
