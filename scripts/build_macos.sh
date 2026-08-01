#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
rm -rf build dist release
export MACOSX_DEPLOYMENT_TARGET="12.0"
python -m PyInstaller --noconfirm --clean --windowed --name "Archive Scout" --target-arch universal2 --collect-all truststore run_app.py
APP="dist/Archive Scout.app"
STAGED_APP="build/dmg/Archive Scout.app"
DMG="release/ArchiveScout-macOS-Universal.dmg"
MOUNT_POINT="build/dmg-verification"
python scripts/verify_macos_bundle.py "$APP"
codesign --force --deep --sign - "$APP"
codesign --verify --deep --strict --verbose=2 "$APP"
mkdir -p "build/dmg" release
ditto "$APP" "$STAGED_APP"
python scripts/verify_macos_bundle.py "$STAGED_APP"
ln -s /Applications "build/dmg/Applications"
hdiutil create -volname "Archive Scout" -srcfolder "build/dmg" -ov -format UDZO "$DMG"
mkdir -p "$MOUNT_POINT"
cleanup() {
  hdiutil detach "$MOUNT_POINT" -quiet >/dev/null 2>&1 || true
}
trap cleanup EXIT
hdiutil attach "$DMG" -nobrowse -readonly -mountpoint "$MOUNT_POINT" -quiet
python scripts/verify_macos_bundle.py "$MOUNT_POINT/Archive Scout.app"
hdiutil detach "$MOUNT_POINT" -quiet
trap - EXIT
(
  cd release
  shasum -a 256 ArchiveScout-macOS-Universal.dmg > ArchiveScout-macOS-Universal.dmg.sha256
)
