#!/usr/bin/env bash
# install.sh — install multisend to /usr/local/bin (or ~/bin if no sudo)
#
# One-liner install:
#   curl -fsSL https://raw.githubusercontent.com/YOURUSER/multisend/main/install.sh | bash

set -e

REPO_RAW="https://raw.githubusercontent.com/humojaguar/multisend/main"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC="$SCRIPT_DIR/multisend.py"

# If multisend.py isn't next to this script, download it (curl install mode)
if [ ! -f "$SRC" ]; then
    echo "Downloading multisend.py..."
    TMP="$(mktemp)"
    if command -v curl &>/dev/null; then
        curl -fsSL "$REPO_RAW/multisend.py" -o "$TMP"
    elif command -v wget &>/dev/null; then
        wget -qO "$TMP" "$REPO_RAW/multisend.py"
    else
        echo "Error: curl or wget is required." >&2
        exit 1
    fi
    SRC="$TMP"
fi

# Prefer /usr/local/bin if writable or can sudo, else ~/bin
if [ -w /usr/local/bin ]; then
    DEST=/usr/local/bin/multisend
    cp "$SRC" "$DEST"
    chmod +x "$DEST"
    echo "Installed to $DEST"
elif command -v sudo &>/dev/null; then
    DEST=/usr/local/bin/multisend
    sudo cp "$SRC" "$DEST"
    sudo chmod +x "$DEST"
    echo "Installed to $DEST (via sudo)"
else
    mkdir -p "$HOME/bin"
    DEST="$HOME/bin/multisend"
    cp "$SRC" "$DEST"
    chmod +x "$DEST"
    echo "Installed to $DEST"
    echo "Make sure ~/bin is in your PATH."
fi

echo ""
echo "Run 'multisend --configure' to add your first bot."
