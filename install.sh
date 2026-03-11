#!/usr/bin/env bash
set -euo pipefail

# Formuler Remote CLI — installer
# Usage: curl -fsSL https://raw.githubusercontent.com/dsebastien/iptv-formuler-cli/main/install.sh | bash

REPO="dsebastien/iptv-formuler-cli"
SCRIPT_NAME="formuler-remote.py"
RAW_URL="https://raw.githubusercontent.com/${REPO}/main/${SCRIPT_NAME}"
SKILL_URL="https://raw.githubusercontent.com/${REPO}/main/.claude/skills/formuler-remote/SKILL.md"
INSTALL_DIR="${INSTALL_DIR:-$HOME/.local/bin}"
SKILL_DIR="${HOME}/.claude/skills/formuler-remote"
MIN_PYTHON="3.10"

# ── helpers ──────────────────────────────────────────────

info()  { printf '\033[32m%s\033[0m\n' "$*"; }
warn()  { printf '\033[33m%s\033[0m\n' "$*"; }
err()   { printf '\033[31mError: %s\033[0m\n' "$*" >&2; }
bold()  { printf '\033[1m%s\033[0m\n' "$*"; }

command_exists() { command -v "$1" >/dev/null 2>&1; }

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

    printf "ADB is required but not installed. Install now? [Y/n] "
    read -r answer </dev/tty
    case "$answer" in
        [nN]*) warn "Skipping ADB install. You'll need it before using formuler-remote."; return ;;
    esac

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
    if command_exists curl; then
        curl -fsSL "$RAW_URL" -o "$tmp"
    elif command_exists wget; then
        wget -qO "$tmp" "$RAW_URL"
    else
        err "Neither curl nor wget found. Cannot download."
        return 1
    fi

    mv "$tmp" "${INSTALL_DIR}/${SCRIPT_NAME}"
    chmod +x "${INSTALL_DIR}/${SCRIPT_NAME}"
    trap - EXIT

    # Create convenience symlink without .py extension
    ln -sf "${INSTALL_DIR}/${SCRIPT_NAME}" "${INSTALL_DIR}/formuler-remote"

    info "Installed to ${INSTALL_DIR}/${SCRIPT_NAME}"
    info "Symlink: ${INSTALL_DIR}/formuler-remote"
}

# ── Claude Code skill ────────────────────────────────────

install_skill() {
    mkdir -p "$SKILL_DIR"

    local tmp
    tmp=$(mktemp)

    info "Installing Claude Code skill..."
    if command_exists curl; then
        curl -fsSL "$SKILL_URL" -o "$tmp"
    elif command_exists wget; then
        wget -qO "$tmp" "$SKILL_URL"
    else
        warn "Cannot download skill (no curl/wget). Skipping."
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
    echo "  # Claude Code skill installed — Claude can now control your TV!"
    echo "  # Try asking: 'tune to TF1' or 'play the movie batman'"
    echo ""
}

main
