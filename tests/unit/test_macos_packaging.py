from __future__ import annotations

import unittest
from pathlib import Path


class MacOSPackagingTests(unittest.TestCase):
    def test_dmg_build_uses_writable_image_workflow(self) -> None:
        script = Path("scripts/build_macos.sh").read_text(encoding="utf-8")
        self.assertNotIn("-srcfolder", script)
        self.assertIn("retry_hdiutil_create", script)
        self.assertIn("hdiutil convert", script)
        self.assertIn("RUNNER_TEMP", script)
        self.assertIn("detach_image", script)
        self.assertIn('ditto "$APP" "$MOUNT_POINT/Archive Scout.app"', script)


if __name__ == "__main__":
    unittest.main()
