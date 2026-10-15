"""배포 ZIP 제작(Windows 전용). `ew package`가 준비한 KoreanPatch 폴더에 실행기와 라이선스를 더해 묶는다.

Linux에서 Windows EXE를 교차 빌드하지 않는다. build-windows.ps1이 전용 venv로 이 파일을 실행한다.
"""
from __future__ import annotations

import hashlib
import importlib.metadata as metadata
import json
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGING = ROOT / "packaging"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def archive_name(snapshot: str, version: str) -> str:
    revision = re.search(r"-rc([1-9][0-9]*)$", version)
    if "-rc" in version and revision is None:
        raise ValueError("추가 업데이트는 -rc1, -rc2, ... 형식이어야 합니다.")
    suffix = f"-rc{revision.group(1)}" if revision else ""
    return f"EchoWeaver-KO-{snapshot}{suffix}.zip"


def freeze(base: Path) -> Path:
    args = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onedir", "--console", "--noupx",
            "--name", "EchoWeaverPatch", "--paths", str(ROOT / "tools/ew"),
            "--distpath", str(base / "frozen"), "--workpath", str(base / "build"), "--specpath", str(base / "spec")]
    for package in ["UnityPy", "TypeTreeGeneratorAPI", "tpk_ar", "archspec", "freetype"]:
        args.extend(["--collect-all", package])
    for package in ["UnityPy", "TypeTreeGeneratorAPI", "lz4", "freetype-py", "numpy", "scipy", "fonttools"]:
        args.extend(["--copy-metadata", package])
    # 작업용 모듈(추출·검사·빌드)은 적용기에 필요 없다.
    for excluded in ["ewlib.pipeline", "ewlib.patcher", "ewlib.checks", "tkinter", "pytest", "IPython", "matplotlib"]:
        args.extend(["--exclude-module", excluded])
    args.append(str(PACKAGING / "launcher.py"))
    print("Building native Windows executable", flush=True)
    subprocess.run(args, check=True)
    return base / "frozen/EchoWeaverPatch"


def collect_licenses(license_dir: Path) -> list[dict]:
    """빌드 venv의 모든 배포판 LICENSE/COPYING/NOTICE, CPython 전문, 네이티브 라이브러리 고지."""
    license_dir.mkdir()
    inventory = []
    for distribution in sorted(metadata.distributions(), key=lambda d: d.metadata["Name"].lower()):
        name = distribution.metadata["Name"]
        row = {"name": name, "version": distribution.version, "license_files": []}
        for file in distribution.files or []:
            path = Path(str(file))
            if any(word in path.name.lower() for word in ["license", "copying", "notice"]):
                source = Path(distribution.locate_file(file))
                if not source.is_file():
                    continue
                safe_parts = [p for p in path.parts if p not in ("..", "/", "\\")]
                target = license_dir / name / Path(*safe_parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
                row["license_files"].append(target.relative_to(license_dir).as_posix())
        inventory.append(row)
    python_license = Path(sys.base_prefix) / "LICENSE.txt"
    if not python_license.is_file():
        raise SystemExit("Python LICENSE.txt is missing; cannot release the frozen runtime.")
    shutil.copyfile(python_license, license_dir / "Python-LICENSE.txt")
    shutil.copytree(PACKAGING / "licenses", license_dir / "native-notices")
    (license_dir / "inventory.json").write_text(json.dumps(inventory, ensure_ascii=False, indent=2), encoding="utf-8")
    return inventory


def main() -> None:
    if sys.platform != "win32" or len(sys.argv) != 2:
        raise SystemExit("Usage (Windows Python 3.11): build_windows.py <version>")
    version = sys.argv[1]
    base = ROOT / "runtime/package" / version
    stage = base / "KoreanPatch"
    patch = json.loads((stage / "patch.json").read_text(encoding="utf-8"))
    if patch["version"] != version:
        raise SystemExit(f"Run `ew package --version {version}` first.")
    snapshot = patch.get("snapshot") or json.loads((ROOT / "config/project.json").read_text(encoding="utf-8"))["source"]["snapshot"]
    archive = ROOT / "dist" / archive_name(snapshot, version)
    if archive.exists():
        raise SystemExit(f"Archive already exists: {archive.name}; use the next -rcN version.")
    for generated in (stage / "bin", stage / "licenses"):
        if generated.exists():
            shutil.rmtree(generated)
    shutil.copytree(freeze(base), stage / "bin")
    inventory = collect_licenses(stage / "licenses")
    archive.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for file in sorted(stage.rglob("*")):
            if file.is_file():
                z.write(file, (Path("KoreanPatch") / file.relative_to(stage)).as_posix())
    digest = sha(archive)
    archive.with_suffix(".sha256").write_text(f"{digest}  {archive.name}\n", encoding="utf-8")
    record = ROOT / "data/review" / snapshot / f"release-{version}"
    record.mkdir(parents=True, exist_ok=True)
    result = {"archive": archive.relative_to(ROOT).as_posix(), "sha256": digest, "size": archive.stat().st_size,
              "archive_root": "KoreanPatch", "label": patch["label"], "patched_sha256": patch["game"]["patched_sha256"],
              "python": sys.version, "pyinstaller": metadata.version("PyInstaller"),
              "executable_sha256": sha(stage / "bin/EchoWeaverPatch.exe"), "distribution_inventory": inventory}
    (record / "build-result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "distribution_inventory"}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
