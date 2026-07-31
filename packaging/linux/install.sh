#!/usr/bin/env bash
set -euo pipefail
SOURCE_DIR="$(cd "$(dirname "$0")" && pwd)/ArchiveScout"
DEST_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/archive-scout"
BIN_DIR="$HOME/.local/bin"
APPLICATIONS_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
mkdir -p "$DEST_DIR" "$BIN_DIR" "$APPLICATIONS_DIR"
rm -rf "$DEST_DIR/ArchiveScout"
cp -R "$SOURCE_DIR" "$DEST_DIR/ArchiveScout"
ln -sf "$DEST_DIR/ArchiveScout/ArchiveScout" "$BIN_DIR/archive-scout"
cat > "$APPLICATIONS_DIR/archive-scout.desktop" <<EOF
[Desktop Entry]
Name=Archive Scout
Comment=Wayback Machine archive research tool
Exec=$DEST_DIR/ArchiveScout/ArchiveScout
Terminal=false
Type=Application
Categories=Utility;Education;
EOF
chmod +x "$APPLICATIONS_DIR/archive-scout.desktop"
printf 'Archive Scout was installed. Make sure %s is in your PATH.\n' "$BIN_DIR"
