from __future__ import annotations

import unittest
from pathlib import Path


class MacOSPackagingTests(unittest.TestCase):
    def test_macos_build_uses_symlink_preserving_zip(self) -> None:
        script = Path("scripts/build_macos.sh").read_text(encoding="utf-8")
        self.assertNotIn("hdiutil", script)
        self.assertNotIn(".dmg", script)
        self.assertIn("ArchiveScout-macOS-Universal.zip", script)
        self.assertIn("ditto -c -k --sequesterRsrc --keepParent", script)
        self.assertIn("ditto -x -k", script)
        self.assertIn('python scripts/verify_macos_bundle.py "$EXTRACTED_APP"', script)
        self.assertIn('codesign --verify --deep --strict --verbose=2 "$EXTRACTED_APP"', script)


if __name__ == "__main__":
    unittest.main()
