# GitHub setup

## Repository upload

Upload the contents of the extracted repository folder, not the enclosing folder itself. The repository root must directly contain:

```text
.github/
archive_scout/
docs/
examples/
packaging/
scripts/
tests/
README.md
pyproject.toml
requirements-build.txt
requirements-runtime.txt
run_app.py
```

On macOS, press `Command + Shift + .` in Finder to reveal `.github`.

## Test workflow

Open **Actions → Tests**. The matrix tests Windows, Linux, and Intel macOS with Python 3.11 and 3.12.

## Build workflow

Open **Actions → Build All Platforms → Run workflow**. A successful manual run creates three workflow artifacts.

## Release

Publish the tag:

```text
v2.0.0-alpha.2.4
```

The tagged build uploads:

```text
ArchiveScout-Windows-x64.zip
ArchiveScout-Windows-x64.zip.sha256
ArchiveScout-Linux-x64.tar.gz
ArchiveScout-Linux-x64.tar.gz.sha256
ArchiveScout-macOS-Universal.dmg
ArchiveScout-macOS-Universal.dmg.sha256
```

Do not use workflow-artifact URLs as public download links. The README points to GitHub Release assets.
