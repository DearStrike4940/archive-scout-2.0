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
  run_app.py

APP="dist/Archive Scout.app"
DMG="release/ArchiveScout-macOS-Universal.dmg"
TEMP_ROOT="${RUNNER_TEMP:-${TMPDIR:-/tmp}}"
WORK_ROOT="$(mktemp -d "$TEMP_ROOT/archive-scout-dmg.XXXXXX")"
RW_DMG="$WORK_ROOT/ArchiveScout-macOS-Universal-rw.dmg"
FINAL_TEMP_DMG="$WORK_ROOT/ArchiveScout-macOS-Universal.dmg"
MOUNT_POINT="$WORK_ROOT/mount"
VERIFY_POINT="$WORK_ROOT/verify"
IMAGE_ATTACHED=0
VERIFY_ATTACHED=0

cleanup() {
  if [[ "$VERIFY_ATTACHED" -eq 1 ]]; then
    hdiutil detach "$VERIFY_POINT" -force -quiet >/dev/null 2>&1 || true
  fi
  if [[ "$IMAGE_ATTACHED" -eq 1 ]]; then
    hdiutil detach "$MOUNT_POINT" -force -quiet >/dev/null 2>&1 || true
  fi
  rm -rf "$WORK_ROOT"
}
trap cleanup EXIT

retry_hdiutil_create() {
  local attempt
  for attempt in 1 2 3 4; do
    rm -f "$RW_DMG"
    if hdiutil create \
      -size "${IMAGE_SIZE_KB}k" \
      -fs HFS+ \
      -volname "Archive Scout" \
      -format UDRW \
      "$RW_DMG"; then
      return 0
    fi
    if [[ "$attempt" -lt 4 ]]; then
      echo "hdiutil create failed on attempt $attempt; retrying after $((attempt * 3)) seconds..."
      sleep $((attempt * 3))
    fi
  done
  echo "Unable to create the writable macOS disk image after four attempts." >&2
  return 1
}

detach_image() {
  local point="$1"
  local attempt
  for attempt in 1 2 3 4; do
    if hdiutil detach "$point" -quiet; then
      return 0
    fi
    if [[ "$attempt" -lt 4 ]]; then
      echo "Disk image at $point is still busy; retrying detach after $((attempt * 2)) seconds..."
      sync
      sleep $((attempt * 2))
    fi
  done
  hdiutil detach "$point" -force -quiet
}

python scripts/verify_macos_bundle.py "$APP"
codesign --force --deep --sign - "$APP"
codesign --verify --deep --strict --verbose=2 "$APP"

mkdir -p release "$MOUNT_POINT" "$VERIFY_POINT"
APP_SIZE_KB="$(du -sk "$APP" | awk '{print $1}')"
IMAGE_SIZE_KB=$((APP_SIZE_KB + 131072))

retry_hdiutil_create

hdiutil attach \
  "$RW_DMG" \
  -nobrowse \
  -noverify \
  -noautoopen \
  -mountpoint "$MOUNT_POINT" \
  -quiet
IMAGE_ATTACHED=1

ditto "$APP" "$MOUNT_POINT/Archive Scout.app"
ln -s /Applications "$MOUNT_POINT/Applications"
python scripts/verify_macos_bundle.py "$MOUNT_POINT/Archive Scout.app"
sync

detach_image "$MOUNT_POINT"
IMAGE_ATTACHED=0

rm -f "$FINAL_TEMP_DMG" "$DMG"
hdiutil convert \
  "$RW_DMG" \
  -format UDZO \
  -imagekey zlib-level=9 \
  -o "$FINAL_TEMP_DMG"
mv "$FINAL_TEMP_DMG" "$DMG"

hdiutil attach \
  "$DMG" \
  -nobrowse \
  -readonly \
  -noautoopen \
  -mountpoint "$VERIFY_POINT" \
  -quiet
VERIFY_ATTACHED=1
python scripts/verify_macos_bundle.py "$VERIFY_POINT/Archive Scout.app"
detach_image "$VERIFY_POINT"
VERIFY_ATTACHED=0

(
  cd release
  shasum -a 256 ArchiveScout-macOS-Universal.dmg > ArchiveScout-macOS-Universal.dmg.sha256
)

trap - EXIT
rm -rf "$WORK_ROOT"
