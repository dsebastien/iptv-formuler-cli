# Phase 6: Distribution — Completions, Uninstall, --help

**Priority**: LOW-MEDIUM
**Status**: Planned
**Dependencies**: None (independent)

## Changes

### 1. `--completions <bash|zsh|fish>` flag

Print shell completion script to stdout and exit. Generate from `COMMANDS.keys()` + `KEYS.keys()`.

```bash
formuler-remote --completions bash >> ~/.bashrc
```

### 2. `--help` / `-h` flag

Print module docstring and exit. Standard CLI behavior.

### 3. `--uninstall` flag in install.sh

Remove script, symlink, skill dir. Optionally remove config/cache (prompt user).

## Files Modified

- `formuler-remote.py` (`main()` flag handling)
- `install.sh` (add `--uninstall`)
- `README.md` (completions setup, uninstall docs)

## Verification

1. `python3 -c "import py_compile; py_compile.compile('formuler-remote.py', doraise=True)"`
2. `bash -n install.sh` — verify shell syntax
