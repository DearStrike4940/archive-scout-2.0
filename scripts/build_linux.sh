#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
rm -rf build dist release
python -m PyInstaller --noconfirm --clean --windowed --onedir --name ArchiveScout --collect-all truststore --collect-all urllib3 run_app.py
mkdir -p release/ArchiveScout-Linux-x64
cp -R dist/ArchiveScout release/ArchiveScout-Linux-x64/ArchiveScout
cp packaging/linux/install.sh packaging/linux/uninstall.sh README.md release/ArchiveScout-Linux-x64/
tar -C release -czf release/ArchiveScout-Linux-x64.tar.gz ArchiveScout-Linux-x64
(
  cd release
  sha256sum ArchiveScout-Linux-x64.tar.gz > ArchiveScout-Linux-x64.tar.gz.sha256
)
