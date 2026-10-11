"""배포본 적용기. 사용자 PC의 원본 data.unity3d·DLL에 패치를 적용·복구한다.

배포본에는 원본 게임 파일·변환한 폰트가 없으므로, 사용자의 원본을 읽어 번역을 넣고 동봉한 TTF로 SDF를 굽는다.
결과 해시가 검증된 빌드와 같을 때만 설치하며, 원본 해시가 다르면(게임 업데이트 등) 적용하지 않는다.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

from . import managed
from .common import EWError, sha256_bytes, sha256_file

PATCH_FORMAT = "echo-weaver-ko/patch-v2"


def load_patch(patch_dir: Path) -> dict:
    path = patch_dir / "patch.json"
    if not path.is_file():
        raise EWError("PATCH_MISSING", f"{path} 이(가) 없습니다. 배포 ZIP을 다시 풀어 주십시오.")
    patch = json.loads(path.read_text(encoding="utf-8"))
    if patch.get("format") != PATCH_FORMAT:
        raise EWError("PATCH_FORMAT", "지원하지 않는 패치 형식입니다.")
    return patch


def _paths(game_root: Path, patch: dict) -> tuple[Path, Path]:
    bundle = managed.game_path(game_root, patch["game"]["data_bundle"])
    if not bundle.is_file():
        raise EWError("GAME_NOT_FOUND", f"{bundle} 이(가) 없습니다. KoreanPatch 폴더를 Echo Weaver 게임 폴더"
                                        "(Echo Weaver_Data가 있는 폴더) 안에 두고 실행하십시오.")
    return bundle, bundle.with_name(bundle.name + ".original")


def apply(game_root: Path, patch_dir: Path) -> dict:
    patch = load_patch(patch_dir)
    game = patch["game"]
    bundle, backup = _paths(game_root, patch)
    managed.ensure_game_stopped()
    current = sha256_file(bundle)
    if current not in (game["original_sha256"], game["patched_sha256"]):
        raise EWError("VERSION_MISMATCH", "게임 파일이 이 패치의 기준 버전과 다릅니다. 게임이 업데이트되었으면 새 패치가 필요합니다.")
    if backup.exists() and sha256_file(backup) != game["original_sha256"]:
        raise EWError("BACKUP_VERIFY", f"{backup}의 해시가 원본과 다릅니다.")
    if not backup.exists() and current != game["original_sha256"]:
        raise EWError("NO_BACKUP", f"검증된 원본 백업이 없습니다: {backup}")
    specs = patch.get("managed_files", [])
    if len({s["path"] for s in specs}) != len(specs):
        raise EWError("PATCH_PATHS", "DLL 수정 경로가 중복됩니다.")
    managed_data = []
    for spec in specs:
        managed.validate_spec(spec)
        target = managed.game_path(game_root, spec["path"])
        bak = target.with_name(target.name + ".original")
        if not target.is_file() or sha256_file(target) not in (spec["original_sha256"], spec["patched_sha256"]):
            raise EWError("MANAGED_VERSION", f"DLL이 지원 버전과 다릅니다: {target}")
        if bak.exists() and sha256_file(bak) != spec["original_sha256"]:
            raise EWError("BACKUP_VERIFY", f"DLL 백업 해시가 다릅니다: {bak}")
        if not bak.exists() and sha256_file(target) != spec["original_sha256"]:
            raise EWError("NO_BACKUP", f"DLL 원본 백업이 없습니다: {bak}")
        managed_data.append((spec, target, bak, managed.patch_bytes((bak if bak.exists() else target).read_bytes(), spec)))
    with tempfile.TemporaryDirectory(prefix="ew-ko-") as td:
        work = Path(td)
        if current == game["patched_sha256"]:
            staged_bundle, verify = bundle, {"passed": True, "existing_bundle_hash": True}
        else:
            staged_bundle = work / "data.unity3d"
            verify = build_bundle(patch, patch_dir, game_root, backup if backup.exists() else bundle, staged_bundle)
        changes = [managed.FileChange(bundle, staged_bundle, backup, game["original_sha256"], game["patched_sha256"])]
        for spec, target, bak, data in managed_data:
            staged = managed.game_path(work / "managed", spec["path"])
            staged.parent.mkdir(parents=True, exist_ok=True)
            staged.write_bytes(data)
            changes.append(managed.FileChange(target, staged, bak, spec["original_sha256"], spec["patched_sha256"]))
        result = managed.deploy(changes)
    return {**result, "backup": str(backup), "sha256": sha256_file(bundle), "verify": verify}


def build_bundle(patch: dict, patch_dir: Path, game_root: Path, source: Path, out: Path) -> dict:
    """원본 source에 번역·폰트를 넣어 out에 저장하고, 검증된 빌드 해시와 같은지 확인한다."""
    from . import copydata, fontbake
    from .bundlepatch import compose_copy, patch_bundle, verify_bundle
    from .unity import GameBundle

    f = patch["font"]
    font_path = patch_dir / f["path"]
    if not font_path.is_file() or sha256_file(font_path) != f["sha256"]:
        raise EWError("FONT_VERIFY", f"{font_path}이(가) 없거나 손상됐습니다. 배포 ZIP을 다시 풀어 주십시오.")
    translations = json.loads((patch_dir / patch["translations"]).read_text(encoding="utf-8"))
    ko_copy = compose_copy(GameBundle(source, game_root, patch["game"].get("unity_version")), patch, translations)
    if sha256_bytes(ko_copy) != patch["copy_sha256"]:
        raise EWError("COPY_MISMATCH", "원본에서 재구성한 언어 파일이 패치 기준과 다릅니다.")
    codepoints = fontbake.build_charset(f["charset"], [r["copy"] for r in copydata.parse(ko_copy)])
    font = fontbake.font_data(fontbake.bake(font_path, codepoints, f["point_size"], f["padding"], f["atlas_size"],
                                            f.get("supersample", 8), f.get("spread")), f)
    patch_bundle(patch, source, ko_copy, font, game_root).save(out, patch["game"].get("packer", "lz4"))
    verify = verify_bundle(patch, out, ko_copy, font, game_root, source)
    if not verify["passed"]:
        raise EWError("VERIFY_FAILED", json.dumps(verify, ensure_ascii=False))
    if sha256_file(out) != patch["game"]["patched_sha256"]:
        raise EWError("PATCH_HASH_MISMATCH", "만든 게임 파일이 검증된 빌드와 다릅니다. 원본을 유지합니다.")
    return verify


def restore(game_root: Path, patch_dir: Path) -> dict:
    patch = load_patch(patch_dir)
    bundle, backup = _paths(game_root, patch)
    expected = patch["game"]["original_sha256"]
    if ((backup.exists() and sha256_file(backup) != expected) or
            (not backup.exists() and sha256_file(bundle) != expected)):
        raise EWError("NO_BACKUP", f"검증된 원본 백업({backup.name})이 없습니다. Xbox 앱의 '확인 및 복구'를 사용하십시오.")
    changes = [managed.FileChange(bundle, backup if backup.exists() else bundle, backup, expected,
                                  patch["game"]["patched_sha256"])]
    for spec in patch.get("managed_files", []):
        managed.validate_spec(spec)
        target = managed.game_path(game_root, spec["path"])
        bak = target.with_name(target.name + ".original")
        changes.append(managed.FileChange(target, bak if bak.exists() else target, bak,
            spec["original_sha256"], spec["patched_sha256"]))
    result = managed.deploy(changes, restoring=True)
    return {**result, "sha256": sha256_file(bundle)}
