# Repository details

Release: `2.0.0-alpha.2.5`

Database schema: `3`

Supported build targets:

- Windows x64
- Linux x64
- macOS Universal 2 for Intel and Apple Silicon

Primary release files:

```text
ArchiveScout-Windows-x64.zip
ArchiveScout-Linux-x64.tar.gz
ArchiveScout-macOS-Universal.zip
```

Each package has a corresponding `.sha256` file.

Alpha 2’s theme is **search, scoring, review, and media downloading**.

Alpha 2.2 adds adaptive CDX window splitting for broad text and media index requests.

## macOS bundle integrity

The macOS build verifies `Contents/Resources/base_library.zip`, the executable, and every symbolic link before signing. It then packages the signed application with `ditto`, extracts the finished ZIP into a clean temporary directory, and verifies the extracted bundle and code signature again. The application also checks its frozen runtime before operations and network requests so a moved, deleted, replaced, or corrupted running app produces a direct installation error instead of a misleading CDX network failure.

Alpha 2.5 replaces DMG creation with a symlink-preserving ZIP because repeated `hdiutil` disk-image creation failures on the hosted macOS runner occurred after the application itself had already built and verified successfully.
