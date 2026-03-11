# Phase 3: Agent Efficiency — Batch Mode and Flags

**Priority**: MEDIUM
**Status**: Planned
**Dependencies**: Phase 2 (needs JSON consistency + timeout integration)

## Changes

### 1. Batch/pipe mode

When stdin is not a TTY and no command args given, read lines from stdin, dispatch each. In JSON mode, emit one JSON object per line (JSONL). Ignore blank lines and `#` comments.

```bash
echo -e "tune TF1\nwait 3\nscreenshot" | formuler-remote --json --first
```

### 2. `--wait <N>` flag

Sleep N seconds after command completes. Parsed in `main()`, applied after `dispatch()`.

### 3. `--timeout <N>` flag

Override default ADB timeout (10s). Store in global `ADB_TIMEOUT`, use as default in `adb()` function.

### 4. `--verbose` / `--debug` flag

Set `VERBOSE` global. In `adb()`, print full command and return code to stderr. Does not pollute stdout JSON.

## Files Modified

- `formuler-remote.py` (`main()` + globals)
- `SKILL.md` (document flags)
- `README.md` (flags table, batch mode docs)

## Verification

1. `python3 -c "import py_compile; py_compile.compile('formuler-remote.py', doraise=True)"`
2. `echo "commands" | ./formuler-remote.py --json` — verify batch mode works
