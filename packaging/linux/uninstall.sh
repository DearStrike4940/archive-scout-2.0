#!/usr/bin/env bash
set -euo pipefail
DEST_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/archive-scout"
BIN_PATH="$HOME/.local/bin/archive-scout"
DESKTOP_PATH="${XDG_DATA_HOME:-$HOME/.local/share}/applications/archive-scout.desktop"
rm -rf "$DEST_DIR"
rm -f "$BIN_PATH" "$DESKTOP_PATH"
echo "Archive Scout was uninstalled. Research project folders were not removed."
