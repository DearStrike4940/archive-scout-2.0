#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

rm -rf build dist release
export MACOSX_DEPLOYMENT_TARGET="12.0"

python -m PyInstaller \
  --noconfirm \
  --clean \
  --windowed \
  --name "Archive Scout" \
  --target-arch universal2 \
  --collect-all truststore \
  --collect-all urllib3 \
  run_app.py

APP="dist/Archive Scout.app"
ZIP="release/ArchiveScout-macOS-Universal.zip"
TEMP_ROOT="${RUNNER_TEMP:-${TMPDIR:-/tmp}}"
VERIFY_ROOT="$(mktemp -d "$TEMP_ROOT/archive-scout-macos-verify.XXXXXX")"
EXTRACTED_APP="$VERIFY_ROOT/Archive Scout.app"

cleanup() {
  rm -rf "$VERIFY_ROOT"
}
trap cleanup EXIT

python scripts/verify_macos_bundle.py "$APP"
codesign --force --deep --sign - "$APP"
codesign --verify --deep --strict --verbose=2 "$APP"

mkdir -p release
rm -f "$ZIP" "$ZIP.sha256"

ditto -c -k --sequesterRsrc --keepParent "$APP" "$ZIP"
ditto -x -k "$ZIP" "$VERIFY_ROOT"

python scripts/verify_macos_bundle.py "$EXTRACTED_APP"
codesign --verify --deep --strict --verbose=2 "$EXTRACTED_APP"

(
  cd release
  shasum -a 256 ArchiveScout-macOS-Universal.zip > ArchiveScout-macOS-Universal.zip.sha256
)

trap - EXIT
rm -rf "$VERIFY_ROOT"
