"""배포본 적용기의 입력 확인: 패치 형식, 잘못 둔 폴더, 동봉 폰트 손상."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ewlib import applier, managed
from ewlib.common import EWError, sha256_bytes


class ApplierTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.patch_dir = self.root / "KoreanPatch"
        self.patch_dir.mkdir()
        self.guard = patch.object(managed, "ensure_game_stopped")
        self.guard.start()

    def tearDown(self):
        self.guard.stop()
        self.temp.cleanup()

    def write_patch(self, fmt=applier.PATCH_FORMAT, original="0" * 64):
        (self.patch_dir / "patch.json").write_text(json.dumps({
            "format": fmt, "game": {"data_bundle": "Echo Weaver_Data/data.unity3d", "original_sha256": original,
                                    "patched_sha256": "1" * 64},
            "font": {"path": "payload/font.ttf", "sha256": sha256_bytes(b"font")}}), encoding="utf-8")

    def code(self, function):
        with self.assertRaises(EWError) as caught:
            function(self.root, self.patch_dir)
        return caught.exception.code

    def test_missing_or_old_patch_is_rejected(self):
        self.assertEqual(self.code(applier.apply), "PATCH_MISSING")
        self.write_patch("echo-weaver-ko/patch-v1")
        self.assertEqual(self.code(applier.apply), "PATCH_FORMAT")

    def test_misplaced_package_does_not_touch_files(self):
        self.write_patch()
        for function in (applier.apply, applier.restore):
            self.assertEqual(self.code(function), "GAME_NOT_FOUND")
        self.assertEqual(sorted(p.name for p in self.root.iterdir()), ["KoreanPatch"])

    def test_damaged_font_is_rejected_before_game_files_change(self):
        bundle = self.root / "Echo Weaver_Data" / "data.unity3d"
        bundle.parent.mkdir()
        bundle.write_bytes(b"original bundle")
        self.write_patch(original=sha256_bytes(b"original bundle"))
        self.assertEqual(self.code(applier.apply), "FONT_VERIFY")
        (self.patch_dir / "payload").mkdir()
        (self.patch_dir / "payload" / "font.ttf").write_bytes(b"other")
        self.assertEqual(self.code(applier.apply), "FONT_VERIFY")
        self.assertEqual(sorted(p.name for p in bundle.parent.iterdir()), ["data.unity3d"])
        self.assertEqual(bundle.read_bytes(), b"original bundle")


if __name__ == "__main__":
    unittest.main()
