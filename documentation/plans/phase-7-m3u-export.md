# Phase 7: M3U Playlist Export

**Priority**: LOW
**Status**: Planned
**Dependencies**: None (independent)

## Changes

### `export-m3u [path]`

Generate M3U from full channel cache. Includes `#EXTINF` with channel number, title, logo.

Note: Stream URLs are not available (CLI uses intents), so M3U contains metadata only — useful for channel lineup reference.

Add to COMMANDS, dispatch, completer, HELP_TEXT.

## Files Modified

- `formuler-remote.py` (new function + dispatch)
- `README.md` (document export)

## Verification

1. `python3 -c "import py_compile; py_compile.compile('formuler-remote.py', doraise=True)"`
2. `./formuler-remote.py --json commands` — verify `export-m3u` appears
