# Repository details

Release: `2.0.0-alpha.2.4`

Database schema: `3`

Supported build targets:

- Windows x64
- Linux x64
- macOS Universal 2 for Intel and Apple Silicon

Primary release files:

```text
ArchiveScout-Windows-x64.zip
ArchiveScout-Linux-x64.tar.gz
ArchiveScout-macOS-Universal.dmg
```

Each package has a corresponding `.sha256` file.

Alpha 2’s theme is **search, scoring, review, and media downloading**.

Alpha 2.2 adds adaptive CDX window splitting for broad text and media index requests.

## macOS bundle integrity

The macOS build uses `ditto` for application-bundle staging and verifies `Contents/Frameworks/base_library.zip`, the executable, and every symbolic link before signing, after staging, and inside the mounted final DMG. The application also checks its frozen runtime before operations and network requests so a moved, deleted, replaced, or corrupted running app produces a direct installation error instead of a misleading CDX network failure.

Alpha 2.4 replaces the fragile direct `hdiutil -srcfolder` step with a retryable writable-image workflow, preventing transient `Resource busy` errors from failing an otherwise valid macOS build.
