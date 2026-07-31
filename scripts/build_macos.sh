#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
rm -rf build dist release
export MACOSX_DEPLOYMENT_TARGET="12.0"
python -m PyInstaller --noconfirm --clean --windowed --name "Archive Scout" --target-arch universal2 --collect-all truststore run_app.py
codesign --force --deep --sign - "dist/Archive Scout.app"
mkdir -p "build/dmg" release
cp -R "dist/Archive Scout.app" "build/dmg/"
ln -s /Applications "build/dmg/Applications"
hdiutil create -volname "Archive Scout" -srcfolder "build/dmg" -ov -format UDZO "release/ArchiveScout-macOS-Universal.dmg"
(
  cd release
  shasum -a 256 ArchiveScout-macOS-Universal.dmg > ArchiveScout-macOS-Universal.dmg.sha256
)
