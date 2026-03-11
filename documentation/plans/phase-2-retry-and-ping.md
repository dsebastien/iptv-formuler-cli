# Phase 2: Retry Logic and Health Check

**Priority**: MEDIUM
**Status**: Planned
**Dependencies**: Phase 1 (needs clean error reporting)

## Changes

### 1. `_adb_retry()` wrapper

Retry on transient errors (timeout, busy, closed) with exponential backoff (0.5s, 1s, 2s), max 3 attempts.

Use for: `fetch_channels`, `search_provider`, `screenshot`, `cmd_record_screen`, `cmd_status`

### 2. `ping` command

`adb shell echo pong` with 5s timeout. Returns `{"ok": true, "data": {"ip": ..., "port": ...}}` or error.

Add to COMMANDS, dispatch, completer, HELP_TEXT.

### 3. Lock file

`fcntl.flock()` on `CACHE_DIR/.lock` in `main()` to prevent concurrent instances sending conflicting key events.

Add `import fcntl`.

## Files Modified

- `formuler-remote.py` (new functions + modify `adb()`)
- `SKILL.md` (add `ping`)
- `README.md` (document `ping`, retry)

## Verification

1. `python3 -c "import py_compile; py_compile.compile('formuler-remote.py', doraise=True)"`
2. `./formuler-remote.py --json commands` — verify `ping` appears
