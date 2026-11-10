#!/usr/bin/env bash
set -euo pipefail

# Formuler Remote CLI — installer
# Usage: curl -fsSL https://raw.githubusercontent.com/dsebastien/iptv-formuler-cli/main/install.sh | bash

# Options (environment):
#   REF=v1.2.0          install a tag or branch instead of main
#   INSTALL_DIR=...     where commands go (default ~/.local/bin)
#   NO_MOL4=1           skip the MyTVOnline 4 tools (OCR scripts, Python venv)
#   ASSUME_YES=1        answer yes to every prompt (non-interactive installs)
#   SRC_DIR=.           install from a local checkout instead of GitHub (for testing)
# Flags: --uninstall, --no-mol4, --yes

REPO="dsebastien/iptv-formuler-cli"
REF="${REF:-main}"
BASE_URL="https://raw.githubusercontent.com/${REPO}/${REF}"
SCRIPT_NAME="formuler-remote.py"
RAW_URL="${BASE_URL}/${SCRIPT_NAME}"
SKILL_URL="${BASE_URL}/.claude/skills/formuler-remote/SKILL.md"
INSTALL_DIR="${INSTALL_DIR:-$HOME/.local/bin}"
SKILL_DIR="${HOME}/.claude/skills/formuler-remote"
LIB_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/formuler-remote"
MIN_PYTHON="3.10"
NO_MOL4="${NO_MOL4:-}"
ASSUME_YES="${ASSUME_YES:-}"
SRC_DIR="${SRC_DIR:-}"

# MyTVOnline 4 tools: script -> command name
MOL4_SCRIPTS="mol4_star.py mol4_scan.py mol4_collect.py mol4_scrcpy.py imdb_match.py"
MOL4_COMMANDS="mol4_star.py:formuler-mol4-star mol4_scan.py:formuler-mol4-scan mol4_collect.py:formuler-mol4-collect imdb_match.py:formuler-imdb-match"

# ── helpers ──────────────────────────────────────────────

info()  { printf '\033[32m%s\033[0m\n' "$*"; }
warn()  { printf '\033[33m%s\033[0m\n' "$*"; }
err()   { printf '\033[31mError: %s\033[0m\n' "$*" >&2; }
bold()  { printf '\033[1m%s\033[0m\n' "$*"; }

command_exists() { command -v "$1" >/dev/null 2>&1; }

# ask "question" -> 0 for yes (default yes). ASSUME_YES or no terminal: yes.
ask() {
    [ -n "$ASSUME_YES" ] && return 0
    [ -r /dev/tty ] || return 0
    printf "%s [Y/n] " "$1"
    local answer
    read -r answer </dev/tty || return 0
    case "$answer" in [nN]*) return 1 ;; *) return 0 ;; esac
}

download() {  # download URL DEST   (with SRC_DIR: copy the same path from the checkout)
    if [ -n "$SRC_DIR" ]; then
        cp "${SRC_DIR}/${1#"${BASE_URL}"/}" "$2"
    elif command_exists curl; then
        curl -fsSL "$1" -o "$2"
    elif command_exists wget; then
        wget -qO "$2" "$1"
    else
        err "Neither curl nor wget found. Cannot download."
        return 1
    fi
}

# install_pkg "label" apt dnf pacman zypper apk brew nix   (use - when a manager has no package)
install_pkg() {
    local label="$1" pkg i=0
    shift
    local names=("$@") managers=(apt dnf pacman zypper apk brew nix)
    local mgr
    mgr=$(detect_pkg_manager)
    [ "$mgr" = "yum" ] && mgr="dnf"
    for m in "${managers[@]}"; do
        if [ "$m" = "$mgr" ]; then pkg="${names[$i]:-}"; fi
        i=$((i + 1))
    done
    if [ -z "${pkg:-}" ] || [ "$pkg" = "-" ]; then
        warn "Install ${label} manually (no package known for ${mgr})."
        return 1
    fi
    case "$mgr" in
        apt)    sudo apt-get install -y -qq $pkg ;;
        dnf)    sudo dnf install -y $pkg ;;
        pacman) sudo pacman -S --needed --noconfirm $pkg ;;
        zypper) sudo zypper install -y $pkg ;;
        apk)    sudo apk add $pkg ;;
        brew)   brew install $pkg ;;
        nix)    nix-env -iA $(printf 'nixpkgs.%s ' $pkg) ;;
        *)      warn "Install ${label} manually."; return 1 ;;
    esac
}

detect_os() {
    case "$(uname -s)" in
        Linux*)  echo "linux" ;;
        Darwin*) echo "macos" ;;
        MINGW*|MSYS*|CYGWIN*) echo "windows" ;;
        *)       echo "unknown" ;;
    esac
}

detect_pkg_manager() {
    if command_exists apt-get;  then echo "apt";
    elif command_exists dnf;    then echo "dnf";
    elif command_exists yum;    then echo "yum";
    elif command_exists pacman;  then echo "pacman";
    elif command_exists zypper;  then echo "zypper";
    elif command_exists apk;     then echo "apk";
    elif command_exists brew;    then echo "brew";
    elif command_exists nix-env; then echo "nix";
    else echo "unknown"; fi
}

# ── python check ─────────────────────────────────────────

check_python() {
    local py=""
    for cmd in python3 python; do
        if command_exists "$cmd"; then
            py="$cmd"
            break
        fi
    done

    if [ -z "$py" ]; then
        err "Python not found. Install Python ${MIN_PYTHON}+ first."
        return 1
    fi

    local version
    version=$("$py" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
    local major minor
    major=$(echo "$version" | cut -d. -f1)
    minor=$(echo "$version" | cut -d. -f2)
    local req_major req_minor
    req_major=$(echo "$MIN_PYTHON" | cut -d. -f1)
    req_minor=$(echo "$MIN_PYTHON" | cut -d. -f2)

    if [ "$major" -lt "$req_major" ] || { [ "$major" -eq "$req_major" ] && [ "$minor" -lt "$req_minor" ]; }; then
        err "Python ${version} found, but ${MIN_PYTHON}+ is required."
        return 1
    fi

    info "Python ${version} found ($py)"
}

# ── adb check / install ─────────────────────────────────

install_adb() {
    local os="$1"
    local pkg="$2"

    bold "ADB not found. Attempting to install..."

    if [ "$os" = "macos" ]; then
        if command_exists brew; then
            brew install android-platform-tools
            return
        else
            err "Homebrew not found. Install ADB manually: https://developer.android.com/tools/releases/platform-tools"
            return 1
        fi
    fi

    case "$pkg" in
        apt)    sudo apt-get update -qq && sudo apt-get install -y -qq adb ;;
        dnf)    sudo dnf install -y android-tools ;;
        yum)    sudo yum install -y android-tools ;;
        pacman) sudo pacman -S --noconfirm android-tools ;;
        zypper) sudo zypper install -y android-tools ;;
        apk)    sudo apk add android-tools ;;
        nix)    nix-env -iA nixpkgs.android-tools ;;
        *)
            err "Could not detect package manager. Install ADB manually:"
            echo "  https://developer.android.com/tools/releases/platform-tools"
            return 1
            ;;
    esac
}

check_adb() {
    local os="$1"
    local pkg="$2"

    if command_exists adb; then
        info "ADB found ($(adb version | head -1))"
        return
    fi

    if ! ask "ADB is required but not installed. Install now?"; then
        warn "Skipping ADB install. You'll need it before using formuler-remote."
        return
    fi

    install_adb "$os" "$pkg"

    if command_exists adb; then
        info "ADB installed successfully"
    else
        warn "ADB installation may have failed. Check manually with: adb version"
    fi
}

# ── download & install ───────────────────────────────────

install_script() {
    mkdir -p "$INSTALL_DIR"

    local tmp
    tmp=$(mktemp)
    trap 'rm -f "$tmp"' EXIT

    info "Downloading ${SCRIPT_NAME}..."
    download "$RAW_URL" "$tmp"

    mv "$tmp" "${INSTALL_DIR}/${SCRIPT_NAME}"
    chmod +x "${INSTALL_DIR}/${SCRIPT_NAME}"
    trap - EXIT

    # Create convenience symlink without .py extension
    ln -sf "${INSTALL_DIR}/${SCRIPT_NAME}" "${INSTALL_DIR}/formuler-remote"

    info "Installed to ${INSTALL_DIR}/${SCRIPT_NAME}"
    info "Symlink: ${INSTALL_DIR}/formuler-remote"
}

# ── MyTVOnline 4 tools ───────────────────────────────────

check_mol4_deps() {
    if command_exists tesseract; then
        info "tesseract found"
    elif ask "The MOL4 tools need tesseract (OCR). Install it now?"; then
        install_pkg "tesseract" "tesseract-ocr tesseract-ocr-eng" tesseract "tesseract tesseract-data-eng" \
            "tesseract-ocr tesseract-ocr-traineddata-english" "tesseract-ocr tesseract-ocr-data-eng" \
            tesseract tesseract || true
    fi
    if command_exists magick; then
        info "ImageMagick 7 found"
    elif command_exists convert; then
        info "ImageMagick 6 found (convert)"
    elif ask "The MOL4 tools need ImageMagick. Install it now?"; then
        install_pkg "ImageMagick" imagemagick ImageMagick imagemagick ImageMagick imagemagick imagemagick imagemagick || true
    fi
    if command_exists scrcpy; then
        info "scrcpy found ($(scrcpy --version 2>/dev/null | head -1 | cut -d' ' -f2)): --scrcpy mode available"
    elif ask "Optional: install scrcpy for the much faster --scrcpy mode?"; then
        install_pkg "scrcpy" scrcpy - scrcpy - - scrcpy scrcpy || true
    fi
}

install_mol4() {
    mkdir -p "$LIB_DIR"
    info "Downloading the MyTVOnline 4 tools to ${LIB_DIR}..."
    local f
    for f in $MOL4_SCRIPTS; do
        download "${BASE_URL}/${f}" "${LIB_DIR}/${f}.tmp"
        mv "${LIB_DIR}/${f}.tmp" "${LIB_DIR}/${f}"
    done

    # Own venv: system Pythons often refuse pip installs (PEP 668).
    local py
    py=$(command -v python3 || command -v python)
    if [ ! -x "${LIB_DIR}/venv/bin/python" ]; then
        info "Creating a Python environment in ${LIB_DIR}/venv..."
        if ! "$py" -m venv "${LIB_DIR}/venv"; then
            err "Could not create a venv (on Debian/Ubuntu: sudo apt-get install python3-venv)."
            return 1
        fi
    fi
    info "Installing NumPy and PyAV (PyAV is for --scrcpy)..."
    "${LIB_DIR}/venv/bin/python" -m pip install -q --upgrade pip >/dev/null 2>&1 || true
    "${LIB_DIR}/venv/bin/python" -m pip install -q numpy
    "${LIB_DIR}/venv/bin/python" -m pip install -q av \
        || warn "PyAV did not install: the tools work, but without --scrcpy."

    local pair script cmd
    for pair in $MOL4_COMMANDS; do
        script="${pair%%:*}"
        cmd="${pair##*:}"
        cat > "${INSTALL_DIR}/${cmd}" <<WRAPPER
#!/usr/bin/env sh
exec "${LIB_DIR}/venv/bin/python" "${LIB_DIR}/${script}" "\$@"
WRAPPER
        chmod +x "${INSTALL_DIR}/${cmd}"
    done
    info "Commands: formuler-mol4-star, formuler-mol4-scan, formuler-mol4-collect, formuler-imdb-match"
}

# ── Claude Code skill ────────────────────────────────────

install_skill() {
    mkdir -p "$SKILL_DIR"

    local tmp
    tmp=$(mktemp)

    info "Installing Claude Code skill..."
    if ! download "$SKILL_URL" "$tmp"; then
        warn "Cannot download the skill. Skipping."
        rm -f "$tmp"
        return
    fi

    mv "$tmp" "${SKILL_DIR}/SKILL.md"
    info "Skill installed to ${SKILL_DIR}/SKILL.md"
}

# ── PATH check ───────────────────────────────────────────

check_path() {
    if echo "$PATH" | tr ':' '\n' | grep -qx "$INSTALL_DIR"; then
        return
    fi

    warn "${INSTALL_DIR} is not in your PATH."
    echo ""
    echo "Add it by appending one of these to your shell profile:"
    echo ""

    local shell_name
    shell_name="$(basename "${SHELL:-bash}")"
    local rc_file
    case "$shell_name" in
        zsh)  rc_file="~/.zshrc" ;;
        fish) rc_file="~/.config/fish/config.fish" ;;
        *)    rc_file="~/.bashrc" ;;
    esac

    if [ "$shell_name" = "fish" ]; then
        echo "  fish_add_path ${INSTALL_DIR}"
    else
        echo "  export PATH=\"${INSTALL_DIR}:\$PATH\""
    fi
    echo ""
    echo "Then restart your shell or run: source ${rc_file}"
}

# ── uninstall ────────────────────────────────────────────

uninstall() {
    echo ""
    bold "Formuler Remote CLI — Uninstaller"
    echo ""

    # Remove script and symlink
    if [ -f "${INSTALL_DIR}/${SCRIPT_NAME}" ]; then
        rm -f "${INSTALL_DIR}/${SCRIPT_NAME}"
        info "Removed ${INSTALL_DIR}/${SCRIPT_NAME}"
    fi
    if [ -L "${INSTALL_DIR}/formuler-remote" ]; then
        rm -f "${INSTALL_DIR}/formuler-remote"
        info "Removed symlink ${INSTALL_DIR}/formuler-remote"
    fi

    # Remove MyTVOnline 4 tools
    local pair
    for pair in $MOL4_COMMANDS; do
        if [ -f "${INSTALL_DIR}/${pair##*:}" ]; then
            rm -f "${INSTALL_DIR}/${pair##*:}"
            info "Removed ${INSTALL_DIR}/${pair##*:}"
        fi
    done
    if [ -d "$LIB_DIR" ]; then
        rm -rf "$LIB_DIR"
        info "Removed ${LIB_DIR}"
    fi

    # Remove skill
    if [ -d "$SKILL_DIR" ]; then
        rm -rf "$SKILL_DIR"
        info "Removed skill directory ${SKILL_DIR}"
    fi

    # Optionally remove config and cache
    local config_dir="${HOME}/.config/formuler-remote"
    local cache_dir="${HOME}/.cache/formuler-remote"

    if [ -d "$config_dir" ] || [ -d "$cache_dir" ]; then
        local answer=""
        printf "Remove config and cache directories? [y/N] "
        [ -r /dev/tty ] && read -r answer </dev/tty || true
        case "$answer" in
            [yY]*)
                [ -d "$config_dir" ] && rm -rf "$config_dir" && info "Removed $config_dir"
                [ -d "$cache_dir" ] && rm -rf "$cache_dir" && info "Removed $cache_dir"
                ;;
            *)
                info "Kept config/cache directories."
                ;;
        esac
    fi

    echo ""
    info "Uninstall complete."
}

# ── main ─────────────────────────────────────────────────

main() {
    echo ""
    bold "Formuler Remote CLI — Installer"
    echo ""

    local os pkg
    os=$(detect_os)
    pkg=$(detect_pkg_manager)

    if [ "$os" = "windows" ]; then
        warn "Windows detected (MSYS/Cygwin/Git Bash)."
        warn "This script may work but is untested. Consider using WSL."
    elif [ "$os" = "unknown" ]; then
        warn "Unknown OS detected. Proceeding anyway..."
    fi

    check_python
    check_adb "$os" "$pkg"
    install_script
    if [ -z "$NO_MOL4" ]; then
        check_mol4_deps
        install_mol4 || warn "MyTVOnline 4 tools not installed (formuler-remote still works)."
    fi
    install_skill
    check_path

    echo ""
    info "Done! Get started:"
    echo ""
    echo "  # Set your device IP"
    echo "  export FORMULER_IP=<your-device-ip>"
    echo ""
    echo "  # Launch interactive mode"
    echo "  formuler-remote"
    echo ""
    echo "  # Or run a command directly"
    echo "  formuler-remote tune TF1"
    echo ""
    if [ -z "$NO_MOL4" ]; then
        echo "  # MyTVOnline 4 (Z11 with MOL 12.x): star titles, scan the VOD catalog"
        echo "  formuler-mol4-star --scrcpy --type series \"Silo\""
        echo "  formuler-mol4-scan \"4=BOX-OFFICE 2025\" > movies.jsonl"
        echo ""
    fi
    echo "  # Claude Code skill installed — Claude can now control your TV!"
    echo "  # Try asking: 'tune to TF1' or 'play the movie batman'"
    echo ""
}

# Dispatch: --uninstall or install
ACTION=main
for arg in "$@"; do
    case "$arg" in
        --uninstall) ACTION=uninstall ;;
        --no-mol4)   NO_MOL4=1 ;;
        --yes|-y)    ASSUME_YES=1 ;;
        *)           err "Unknown option: $arg"; exit 2 ;;
    esac
done
"$ACTION"
