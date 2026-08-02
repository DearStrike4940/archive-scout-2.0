# Repository details

Release: `2.0.0-alpha.3`

Database schema: `4`

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

Alpha 3's theme is **archive recovery and analysis**.

Major subsystems added in Alpha 3:

- forum canonicalization and thread reconstruction
- built-in and custom identifier extraction
- legacy embed/player recovery
- controlled external-asset lookup
- exact and near-duplicate clustering
- source-to-mirror provenance
- snapshot comparison and first-appearance research
- project and shared-review merging
- schema version 4 migration
- noninterrupting transient CDX recovery down to one-second windows
- combined direct-media extension indexing

## macOS bundle integrity

The macOS build verifies `Contents/Resources/base_library.zip`, the executable, and every symbolic link before signing. It packages the signed application with `ditto`, extracts the completed ZIP into a clean temporary directory, and verifies the extracted bundle and code signature again.
