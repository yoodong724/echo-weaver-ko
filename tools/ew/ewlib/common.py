"""공통 유틸리티: 설정, 경로, 해시, JSON 입출력, 툴박스 호출."""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[3]
TOOLBOX_CLI = PROJECT_ROOT / "vendor" / "korean-localization-toolbox" / "tools" / "l10n.py"
DEFAULT_CONFIG = PROJECT_ROOT / "config" / "project.json"


class EWError(Exception):
    """사용자에게 그대로 보여 줄 오류."""

    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


def now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).astimezone().isoformat(timespec="seconds")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_json(path: Path) -> Any:
    with open(path, "rb") as f:
        return json.loads(f.read().decode("utf-8-sig"))


def dump_json(obj: Any) -> bytes:
    return (json.dumps(obj, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def ensure_writable(path: Path, force: bool) -> None:
    if path.exists() and not force:
        raise EWError("OUTPUT_EXISTS", f"{path} 이(가) 이미 있습니다. 새 경로를 쓰거나 --force를 지정하십시오.")
    path.parent.mkdir(parents=True, exist_ok=True)


def write_json(path: Path, obj: Any, force: bool = False) -> Path:
    ensure_writable(path, force)
    path.write_bytes(dump_json(obj))
    return path


def write_text(path: Path, text: str, force: bool = False) -> Path:
    ensure_writable(path, force)
    path.write_text(text, encoding="utf-8")
    return path


def append_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def rel(path: Path) -> str:
    try:
        return str(Path(path).resolve().relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


# ---------------------------------------------------------------- config

class Config:
    """config/project.json 래퍼. 경로 값은 프로젝트 루트 기준 상대 경로를 허용한다."""

    def __init__(self, data: dict, path: Path):
        self.data = data
        self.config_path = path

    def __getitem__(self, key: str) -> Any:
        return self.data[key]

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)

    def project_path(self, value: str) -> Path:
        p = Path(value)
        return p if p.is_absolute() else PROJECT_ROOT / p

    @property
    def game_root(self) -> Path:
        override = os.environ.get("EW_GAME_ROOT")
        return Path(override) if override else Path(self.data["game"]["root"])

    @property
    def data_bundle(self) -> Path:
        return self.game_root / self.data["game"]["data_bundle"]

    @property
    def snapshot(self) -> str:
        return self.data["source"]["snapshot"]

    def snapshot_dir(self, snapshot: str | None = None) -> Path:
        return self.project_path(self.data["paths"]["source"]) / (snapshot or self.snapshot)

    def path(self, key: str) -> Path:
        return self.project_path(self.data["paths"][key])


def load_config(path: str | None = None) -> Config:
    p = Path(path) if path else DEFAULT_CONFIG
    if not p.exists():
        raise EWError("CONFIG_MISSING", f"설정 파일이 없습니다: {p}")
    return Config(read_json(p), p)


# ---------------------------------------------------------------- toolbox

def toolbox(*args: str) -> tuple[int, dict]:
    """동봉한 korean-localization-toolbox CLI를 실행하고 (종료 코드, JSON 결과)를 돌려준다."""
    if not TOOLBOX_CLI.exists():
        raise EWError("TOOLBOX_MISSING", f"툴박스가 없습니다: {TOOLBOX_CLI}")
    # -I는 스크립트 디렉터리를 sys.path에서 빼므로 쓰지 않는다(툴박스가 자기 패키지를 import).
    proc = subprocess.run([sys.executable, "-s", str(TOOLBOX_CLI), *args],
                          capture_output=True, text=True, encoding="utf-8")
    out = proc.stdout.strip()
    try:
        payload = json.loads(out) if out else {}
    except json.JSONDecodeError:
        payload = {"raw_stdout": out}
    if proc.stderr.strip():
        payload.setdefault("stderr", proc.stderr.strip())
    if proc.returncode not in (0, 1) or "raw_stdout" in payload or not payload:
        raise EWError("TOOLBOX_FAILED", f"l10n.py {args[0]} 실패: {json.dumps(payload, ensure_ascii=False)[:2000]}")
    return proc.returncode, payload
