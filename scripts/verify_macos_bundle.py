from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def broken_symlinks(root: Path) -> list[Path]:
    broken: list[Path] = []
    for current, directories, files in os.walk(root, followlinks=False):
        current_path = Path(current)
        for name in [*directories, *files]:
            candidate = current_path / name
            if candidate.is_symlink() and not candidate.exists():
                broken.append(candidate)
    return broken


def verify_bundle(app: Path) -> list[str]:
    errors: list[str] = []
    contents = app / "Contents"
    executable_dir = contents / "MacOS"
    frameworks = contents / "Frameworks"
    resources = contents / "Resources"
    base_library = frameworks / "base_library.zip"

    if app.suffix != ".app":
        errors.append(f"not a .app bundle: {app}")
    if not contents.is_dir():
        errors.append(f"missing Contents directory: {contents}")
    if not executable_dir.is_dir() or not any(path.is_file() for path in executable_dir.iterdir() if executable_dir.exists()):
        errors.append(f"missing application executable in {executable_dir}")
    if not frameworks.is_dir():
        errors.append(f"missing Frameworks directory: {frameworks}")
    if not resources.is_dir():
        errors.append(f"missing Resources directory: {resources}")
    if not os.path.lexists(base_library):
        errors.append(f"missing bundled Python library: {base_library}")
    elif not base_library.exists():
        errors.append(f"broken bundled Python library link: {base_library}")
    elif not base_library.is_file():
        errors.append(f"bundled Python library is not a file: {base_library}")

    for link in broken_symlinks(app):
        errors.append(f"broken symbolic link: {link}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("app", type=Path)
    args = parser.parse_args()
    app = args.app.expanduser().resolve()
    errors = verify_bundle(app)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    base_library = app / "Contents" / "Frameworks" / "base_library.zip"
    print(f"Verified macOS bundle: {app}")
    print(f"Verified bundled Python library: {base_library.resolve(strict=True)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
