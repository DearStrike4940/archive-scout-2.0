# GitHub Setup

## Upload the repository

Create one new public repository and upload the complete contents of this folder, including the hidden `.github` directory.

A suitable name is:

```text
archive-scout
```

## Test the repository

1. Open **Actions**.
2. Open **Tests**.
3. Run the workflow manually if it has not already started.
4. Confirm Windows, Linux, and macOS tests pass.

## Build all platforms

1. Open **Actions**.
2. Select **Build All Platforms**.
3. Click **Run workflow**.
4. Download and test the Windows, Linux, and macOS artifacts.

## Publish the first alpha

After testing all three builds, create and push the tag:

```text
v2.0.0-alpha.1
```

The workflow creates or updates the release and attaches:

```text
ArchiveScout-Windows-x64.zip
ArchiveScout-Linux-x64.tar.gz
ArchiveScout-macOS-Universal.dmg
```

Each package also receives a SHA-256 file. The README download links begin working publicly after these assets are attached to a published release.
