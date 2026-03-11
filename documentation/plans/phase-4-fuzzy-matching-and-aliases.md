# Phase 4: Fuzzy Matching and Channel Aliases

**Priority**: MEDIUM
**Status**: Planned
**Dependencies**: Phase 1

## Changes

### 1. Fuzzy matching

Add `import unicodedata`. Create `_normalize(s)` (strip accents, lowercase, collapse spaces) and `_fuzzy_match(query, candidates, key="title")` that:

- Tries exact match first
- Then starts-with
- Then all-tokens-contained
- Then spaces-removed containment ("tf1" matches "TF 1")
- Returns sorted by match quality

Use in: `cmd_tune`, `cmd_search`, `cmd_list`, `cmd_list_all`

### 2. Channel aliases

Read `CONFIG.get("aliases", {})`. In `cmd_tune`, before searching, check alias dict and substitute.

Config example:
```toml
[aliases]
tf1 = "TF1 HD"
bfm = "BFM TV"
```

## Files Modified

- `formuler-remote.py` (new functions + match logic)
- `SKILL.md` (mention aliases)
- `README.md` (aliases config, fuzzy matching)

## Verification

1. `python3 -c "import py_compile; py_compile.compile('formuler-remote.py', doraise=True)"`
