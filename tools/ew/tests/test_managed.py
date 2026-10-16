"""DLL 수정 범위, 설치 중단·되돌리기·원본 복구의 회귀 검사."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ewlib import managed
from ewlib.common import EWError, PROJECT_ROOT, sha256_bytes


class ManagedPatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.guard = patch.object(managed, "ensure_game_stopped")
        self.guard.start()

    def tearDown(self):
        self.guard.stop()
        self.temp.cleanup()

    def fixture(self):
        changes = []
        for name, old, new in (("bundle", b"original language bundle", b"Korean language bundle"),
                               ("font.dll", b"original renderer", b"fixed renderer")):
            target, source, backup = (self.root / name, self.root / (name + ".new"),
                                      self.root / (name + ".original"))
            target.write_bytes(old)
            source.write_bytes(new)
            changes.append(managed.FileChange(target, source, backup, sha256_bytes(old), sha256_bytes(new)))
        return changes

    def test_real_dll_changes_one_byte_and_is_idempotent(self):
        spec = json.loads((PROJECT_ROOT / "config/patches/tmp-ui-literal-fallback-v1.json").read_text())
        source = PROJECT_ROOT / "backups/1.0.2.0" / spec["path"]
        if not source.is_file():
            self.skipTest("로컬 게임 원본 DLL이 필요한 검사")
        original = source.read_bytes()
        fixed = managed.patch_bytes(original, spec)
        self.assertEqual(len(original), len(fixed))
        self.assertEqual([(i, a, b) for i, (a, b) in enumerate(zip(original, fixed)) if a != b],
                         [(59240, 0x74, 0x11)])
        self.assertEqual(managed.patch_bytes(fixed, spec), fixed)
        damaged = bytearray(original)
        damaged[-1] ^= 1
        with self.assertRaises(EWError):
            managed.patch_bytes(bytes(damaged), spec)

    def restores(self, changes):
        # 배포본 restore와 같이 원본 출처를 매번 다시 고른다(복구 후에는 백업이 없다).
        return [managed.FileChange(c.target, managed.original_source(c.target, c.backup, c.original_sha256),
                                   c.backup, c.original_sha256, c.patched_sha256) for c in changes]

    def test_install_repeat_restore_repeat(self):
        changes = self.fixture()
        self.assertEqual(managed.deploy(changes)["status"], "installed")
        self.assertEqual(managed.deploy(changes)["status"], "already_installed")
        result = managed.deploy(self.restores(changes), restoring=True)
        self.assertEqual(result["status"], "restored")
        self.assertEqual(len(result["backups_removed"]), 2)
        self.assertEqual(managed.deploy(self.restores(changes), restoring=True)["status"], "already_original")
        self.assertEqual(changes[0].target.read_bytes(), b"original language bundle")
        self.assertEqual(changes[1].target.read_bytes(), b"original renderer")
        self.assertFalse(list(self.root.glob("*.original")))
        self.assertFalse(list(self.root.glob(".ew-*.tmp")))
        self.assertEqual(managed.deploy(changes)["status"], "installed")

    def test_stale_backup_from_previous_game_version_is_replaced_on_install(self):
        changes = self.fixture()
        for c in changes:
            c.backup.write_bytes(b"previous game version")
        self.assertEqual(managed.deploy(changes)["status"], "installed")
        self.assertEqual(changes[0].backup.read_bytes(), b"original language bundle")
        self.assertEqual(changes[1].backup.read_bytes(), b"original renderer")
        self.assertEqual(managed.deploy(self.restores(changes), restoring=True)["status"], "restored")
        self.assertEqual(changes[1].target.read_bytes(), b"original renderer")
        self.assertFalse(list(self.root.glob("*.original")))

    def test_stale_backup_is_removed_by_restore_without_install(self):
        changes = self.fixture()
        for c in changes:
            c.backup.write_bytes(b"previous game version")
        result = managed.deploy(self.restores(changes), restoring=True)
        self.assertEqual(result["status"], "already_original")
        self.assertEqual(len(result["backups_removed"]), 2)
        self.assertEqual(changes[0].target.read_bytes(), b"original language bundle")

    def test_stale_backup_with_unknown_game_file_is_rejected(self):
        changes = self.fixture()
        changes[0].backup.write_bytes(b"previous game version")
        changes[0].target.write_bytes(b"newer game version")
        with self.assertRaises(EWError) as error:
            managed.deploy(changes)
        self.assertEqual(error.exception.code, "VERSION_MISMATCH")
        with self.assertRaises(EWError) as error:
            managed.original_source(changes[0].target, changes[0].backup, changes[0].original_sha256)
        self.assertEqual(error.exception.code, "BACKUP_VERIFY")
        self.assertEqual(changes[0].backup.read_bytes(), b"previous game version")
        self.assertEqual(changes[1].target.read_bytes(), b"original renderer")

    def test_backup_outside_game_folder_is_kept_after_restore(self):
        changes = self.fixture()
        outside = self.root / "backups" / "bundle"
        outside.parent.mkdir()
        outside.write_bytes(b"original language bundle")
        changes[0] = managed.FileChange(changes[0].target, changes[0].source, outside,
                                        changes[0].original_sha256, changes[0].patched_sha256)
        managed.deploy(changes)
        result = managed.deploy(self.restores(changes), restoring=True)
        self.assertEqual(result["backups_removed"], [str(changes[1].backup)])
        self.assertEqual(outside.read_bytes(), b"original language bundle")

    def test_failed_restore_keeps_backups(self):
        changes = self.fixture()
        managed.deploy(changes)
        replace = os.replace

        def fail_second(src, dst):
            if Path(dst) == changes[1].target:
                raise OSError("simulated locked DLL")
            return replace(src, dst)

        with patch.object(managed.os, "replace", side_effect=fail_second):
            with self.assertRaises(OSError):
                managed.deploy(self.restores(changes), restoring=True)
        self.assertEqual(changes[0].target.read_bytes(), b"Korean language bundle")
        self.assertEqual(changes[0].backup.read_bytes(), b"original language bundle")
        self.assertEqual(changes[1].backup.read_bytes(), b"original renderer")

    def test_unknown_second_file_blocks_first_and_backups(self):
        changes = self.fixture()
        changes[1].target.write_bytes(b"user modification")
        with self.assertRaises(EWError):
            managed.deploy(changes)
        self.assertEqual(changes[0].target.read_bytes(), b"original language bundle")
        self.assertFalse(changes[0].backup.exists())
        self.assertFalse(changes[1].backup.exists())

    def test_bad_second_backup_blocks_first(self):
        changes = self.fixture()
        # 현재 파일이 원본이 아니면(수정본) 백업이 유일한 원본이므로 잔여 백업으로 대체하지 않는다.
        changes[1].target.write_bytes(b"fixed renderer")
        changes[1].backup.write_bytes(b"bad backup")
        with self.assertRaises(EWError):
            managed.deploy(changes)
        self.assertEqual(changes[0].target.read_bytes(), b"original language bundle")
        self.assertEqual(changes[1].backup.read_bytes(), b"bad backup")

    def test_second_replace_failure_rolls_back_first(self):
        changes = self.fixture()
        replace = os.replace
        failed = False

        def fail_once(src, dst):
            nonlocal failed
            if Path(dst) == changes[1].target and not failed:
                failed = True
                raise OSError("simulated locked DLL")
            return replace(src, dst)

        with patch.object(managed.os, "replace", side_effect=fail_once):
            with self.assertRaises(OSError):
                managed.deploy(changes)
        self.assertEqual(changes[0].target.read_bytes(), b"original language bundle")
        self.assertEqual(changes[1].target.read_bytes(), b"original renderer")
        self.assertFalse(list(self.root.glob(".ew-*.tmp")))

    def test_restore_preserves_updated_game_and_dll(self):
        changes = self.fixture()
        managed.deploy(changes)
        changes[0].target.write_bytes(b"game update")
        with self.assertRaises(EWError):
            managed.deploy(self.restores(changes), restoring=True)
        self.assertEqual(changes[0].target.read_bytes(), b"game update")
        self.assertEqual(changes[1].target.read_bytes(), b"fixed renderer")

    def test_change_during_staging_is_preserved(self):
        changes = self.fixture()
        temporary = managed._temporary

        def change_second(target, data):
            result = temporary(target, data)
            if target == changes[1].target:
                target.write_bytes(b"concurrent update")
            return result

        with patch.object(managed, "_temporary", side_effect=change_second):
            with self.assertRaises(EWError) as error:
                managed.deploy(changes)
        self.assertEqual(error.exception.code, "GAME_CHANGED")
        self.assertEqual(changes[0].target.read_bytes(), b"original language bundle")
        self.assertEqual(changes[1].target.read_bytes(), b"concurrent update")
        self.assertFalse(list(self.root.glob(".ew-*.tmp")))

    def test_path_escape_is_rejected(self):
        for path in ("../font.dll", "/font.dll", "C:/font.dll", "dir\\font.dll"):
            with self.assertRaises(EWError):
                managed.game_path(self.root, path)

    def test_old_label_can_restore_only_dll(self):
        changes = self.fixture()
        managed.deploy(changes)
        engine = changes[1]
        changes[1] = managed.FileChange(engine.target, engine.backup, engine.backup,
                                      engine.original_sha256, engine.patched_sha256, engine.original_sha256)
        managed.deploy(changes)
        self.assertEqual(changes[0].target.read_bytes(), b"Korean language bundle")
        self.assertEqual(changes[1].target.read_bytes(), b"original renderer")


if __name__ == "__main__":
    unittest.main()
