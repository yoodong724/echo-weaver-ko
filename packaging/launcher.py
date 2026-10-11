"""KoreanPatch\\bin\\EchoWeaverPatch.exe 진입점. 사용자 PC에 Python이 필요 없다.

EXE의 상위 폴더(KoreanPatch)를 패치 폴더로, 그 상위 폴더를 게임 폴더로 쓴다.
--patch는 저장소에서 고정하지 않은 상태로 시험할 때만 쓴다.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ewlib.common import EWError

MESSAGES = {"install": "게임 파일과 DLL을 검증하고 한국어 폰트를 생성해 패치를 적용합니다. 잠시 기다리십시오.",
            "restore": "원본 백업을 검증하고 게임 파일을 복구합니다."}


def runtime_info() -> dict:
    import importlib
    import importlib.metadata

    packages = {"UnityPy": "UnityPy", "TypeTreeGeneratorAPI": "TypeTreeGeneratorAPI", "lz4": "lz4",
                "freetype": "freetype-py", "numpy": "numpy", "scipy": "scipy", "fontTools": "fonttools"}
    modules = {}
    for name, distribution in packages.items():
        module = importlib.import_module(name)
        modules[name] = {"version": importlib.metadata.version(distribution), "file": module.__file__}
    return {"frozen": bool(getattr(sys, "frozen", False)), "python": sys.version,
            "executable": sys.executable, "runtime_root": getattr(sys, "_MEIPASS", None), "modules": modules}


def main() -> int:
    for stream in [sys.stdout, sys.stderr]:
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Echo Weaver 비공식 한국어 패치")
    parser.add_argument("action", choices=["install", "restore", "self-test"])
    parser.add_argument("--patch", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.patch is None and not getattr(sys, "frozen", False):
        parser.error("고정하지 않은 실행에는 --patch가 필요합니다.")
    patch_dir = (args.patch or Path(sys.executable).parent.parent).resolve()
    try:
        if args.action == "self-test":
            result = runtime_info()
        else:
            from ewlib import applier

            print(MESSAGES[args.action], file=sys.stderr, flush=True)
            function = applier.apply if args.action == "install" else applier.restore
            result = function(patch_dir.parent, patch_dir)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except EWError as error:
        print(json.dumps({"error": error.code, "message": error.message}, ensure_ascii=False), file=sys.stderr)
        return 1
    except (OSError, ValueError) as error:
        print(json.dumps({"error": "FILE_ERROR", "message": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
