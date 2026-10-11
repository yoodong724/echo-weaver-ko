"""해시로 제한한 Managed DLL 바이트 수정과 여러 파일의 설치·복구.

게임 DLL은 동봉하지 않는다. 사용자 원본의 지정된 바이트만 바꾸며,
언어 번들과 DLL을 모두 검증·준비한 뒤 교체한다. 교체 실패 시 이전 내용으로 되돌린다.
"""
from __future__ import annotations

import csv
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from .common import EWError, read_json, sha256_bytes, sha256_file


def game_path(root: Path, relative: str) -> Path:
    p = PurePosixPath(relative)
    if not relative or p.is_absolute() or ".." in p.parts or "\\" in relative or ":" in relative:
        raise EWError("PATCH_PATH", f"게임 폴더 내부 상대 경로가 필요합니다: {relative}")
    target = root.joinpath(*p.parts)
    if not target.resolve().is_relative_to(root.resolve()):
        raise EWError("PATCH_PATH", f"게임 폴더 밖을 가리키는 경로: {relative}")
    return target


def validate_spec(spec: dict) -> None:
    if spec.get("format") != "echo-weaver-ko/byte-patch-v1":
        raise EWError("MANAGED_FORMAT", "지원하지 않는 DLL 수정 형식입니다.")
    game_path(Path.cwd(), spec.get("path", ""))
    for key in ("original_sha256", "patched_sha256"):
        if not re.fullmatch(r"[0-9a-f]{64}", spec.get(key, "")):
            raise EWError("MANAGED_HASH", f"올바른 {key}가 필요합니다.")
    edits = spec.get("edits")
    if not isinstance(edits, list) or not edits:
        raise EWError("MANAGED_EDITS", "DLL 수정 바이트가 없습니다.")
    ranges = []
    for edit in edits:
        try:
            before, after = bytes.fromhex(edit["before"]), bytes.fromhex(edit["after"])
            offset = edit["offset"]
        except (KeyError, ValueError, TypeError) as exc:
            raise EWError("MANAGED_EDITS", "잘못된 DLL 수정 바이트입니다.") from exc
        if type(offset) is not int or offset < 0 or not before or len(before) != len(after):
            raise EWError("MANAGED_EDITS", "DLL 바이트 수정은 길이를 유지해야 합니다.")
        ranges.append((offset, offset + len(before)))
    ranges.sort()
    if any(a[1] > b[0] for a, b in zip(ranges, ranges[1:])):
        raise EWError("MANAGED_EDITS", "DLL 수정 범위가 겹칩니다.")


def patch_bytes(data: bytes, spec: dict) -> bytes:
    validate_spec(spec)
    digest = sha256_bytes(data)
    if digest == spec["patched_sha256"]:
        return data
    if digest != spec["original_sha256"]:
        raise EWError("MANAGED_VERSION", f"{spec['path']}이(가) 수정 기준 원본과 다릅니다.")
    result = bytearray(data)
    for edit in spec["edits"]:
        offset = edit["offset"]
        before, after = bytes.fromhex(edit["before"]), bytes.fromhex(edit["after"])
        if result[offset:offset + len(before)] != before:
            raise EWError("MANAGED_BYTES", "DLL의 지정된 원본 바이트가 다릅니다.")
        result[offset:offset + len(before)] = after
    result = bytes(result)
    if sha256_bytes(result) != spec["patched_sha256"]:
        raise EWError("MANAGED_VERIFY", "DLL 수정 결과 해시가 일치하지 않습니다.")
    return result


def load_specs(cfg) -> list[dict]:
    specs = [read_json(cfg.project_path(p)) for p in cfg.get("managed_patches", [])]
    for spec in specs:
        validate_spec(spec)
    if len({s["path"] for s in specs}) != len(specs):
        raise EWError("MANAGED_PATHS", "DLL 수정 경로가 중복됩니다.")
    return specs


def build(cfg, out: Path, backup_root: Path) -> list[dict]:
    specs = load_specs(cfg)
    # 모든 원본/백업을 먼저 확인한다. 게임 폴더에는 쓰지 않는다.
    prepared = []
    for spec in specs:
        target, backup = game_path(cfg.game_root, spec["path"]), game_path(backup_root, spec["path"])
        source = backup if backup.is_file() else target
        if not source.is_file() or sha256_file(source) != spec["original_sha256"]:
            raise EWError("MANAGED_BACKUP", f"검증된 DLL 원본이 필요합니다: {source}")
        data = source.read_bytes()
        prepared.append((spec, backup, data, patch_bytes(data, spec)))
    for spec, backup, data, patched in prepared:
        if not backup.exists():
            backup.parent.mkdir(parents=True, exist_ok=True)
            backup.write_bytes(data)
        staged = game_path(out / "game", spec["path"])
        staged.parent.mkdir(parents=True, exist_ok=True)
        staged.write_bytes(patched)
        if sha256_file(staged) != spec["patched_sha256"] or sha256_file(backup) != spec["original_sha256"]:
            raise EWError("MANAGED_VERIFY", "준비한 DLL 또는 백업의 해시가 다릅니다.")
    return specs


def ensure_game_stopped() -> None:
    # Windows 배포본에서도 PowerShell 없이 실행 중인 게임을 확인한다.
    if os.name != "nt":
        return  # WSL에서의 Windows 게임 상태는 QA 호출 측에서 먼저 확인한다.
    try:
        result = subprocess.run(["tasklist.exe", "/FI", "IMAGENAME eq Echo Weaver.exe", "/FO", "CSV", "/NH"],
                                capture_output=True, check=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        raise EWError("GAME_STATE", "게임 실행 상태를 확인하지 못했습니다.") from exc
    if any(row and row[0].casefold() == "echo weaver.exe"
           for row in csv.reader(result.stdout.decode(errors="replace").splitlines())):
        raise EWError("GAME_RUNNING", "Echo Weaver를 종료한 뒤 다시 실행하십시오.")


@dataclass
class FileChange:
    target: Path
    source: Path
    backup: Path
    original_sha256: str
    patched_sha256: str
    desired_sha256: str | None = None


def _temporary(target: Path, data: bytes) -> Path:
    path = None
    try:
        with tempfile.NamedTemporaryFile(dir=target.parent, prefix=".ew-", suffix=".tmp", delete=False) as f:
            path = Path(f.name)
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
    except BaseException:
        if path is not None:
            path.unlink(missing_ok=True)
        raise
    return path


def deploy(changes: list[FileChange], *, restoring: bool = False) -> dict:
    ensure_game_stopped()
    if len({c.target.resolve() for c in changes}) != len(changes):
        raise EWError("PATCH_PATHS", "설치 경로가 중복됩니다.")
    prepared = []
    # 어느 파일도 바꾸기 전에 전체 입력·현재 파일·기존 백업을 확인한다.
    for c in changes:
        desired = c.desired_sha256 or (c.original_sha256 if restoring else c.patched_sha256)
        if desired not in (c.original_sha256, c.patched_sha256):
            raise EWError("PATCH_HASH", "설치할 파일 해시가 원본/수정본과 다릅니다.")
        if not c.target.is_file() or not c.source.is_file():
            raise EWError("PATCH_FILE", f"필요한 파일이 없습니다: {c.target} / {c.source}")
        previous, incoming = c.target.read_bytes(), c.source.read_bytes()
        current = sha256_bytes(previous)
        if current not in (c.original_sha256, c.patched_sha256):
            raise EWError("VERSION_MISMATCH", f"알 수 없는 게임 파일을 덮어쓰지 않습니다: {c.target}")
        if sha256_bytes(incoming) != desired:
            raise EWError("COPY_VERIFY", f"준비한 파일의 해시가 다릅니다: {c.source}")
        if c.backup.exists():
            if sha256_file(c.backup) != c.original_sha256:
                raise EWError("BACKUP_VERIFY", f"원본 백업 해시가 다릅니다: {c.backup}")
        elif current != c.original_sha256:
            raise EWError("NO_BACKUP", f"검증된 원본 백업이 없습니다: {c.backup}")
        prepared.append((c, previous, incoming, current, desired))
    staged, replaced = [], []
    try:
        for c, previous, incoming, current, desired in prepared:
            if not c.backup.exists() and not restoring:
                c.backup.parent.mkdir(parents=True, exist_ok=True)
                c.backup.write_bytes(previous)
                if sha256_file(c.backup) != c.original_sha256:
                    raise EWError("BACKUP_VERIFY", str(c.backup))
            if current != desired:
                staged.append((c, _temporary(c.target, incoming), previous, desired))
        for c, temp, previous, desired in staged:
            if sha256_file(c.target) != sha256_bytes(previous):
                raise EWError("GAME_CHANGED", f"설치 중 게임 파일이 변경됐습니다: {c.target}")
            os.replace(temp, c.target)
            replaced.append((c, previous, desired))
            if sha256_file(c.target) != desired:
                raise EWError("COPY_VERIFY", str(c.target))
    except BaseException as exc:
        failures = []
        for c, previous, desired in reversed(replaced):
            try:
                if sha256_file(c.target) != desired:
                    failures.append(str(c.target))
                    continue
                temp = _temporary(c.target, previous)
                try:
                    os.replace(temp, c.target)
                finally:
                    temp.unlink(missing_ok=True)
                if sha256_file(c.target) != sha256_bytes(previous):
                    failures.append(str(c.target))
            except Exception:
                failures.append(str(c.target))
        if failures:
            raise EWError("ROLLBACK_FAILED", f"복구 확인이 필요합니다: {', '.join(failures)}") from exc
        raise
    finally:
        for _, temp, _, _ in staged:
            temp.unlink(missing_ok=True)
    return {"status": ("restored" if restoring else "installed") if staged else
                      ("already_original" if restoring else "already_installed"),
            "files": [{"path": str(c.target), "sha256": desired, "changed": current != desired}
                      for c, _, _, current, desired in prepared]}
