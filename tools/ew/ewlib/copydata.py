"""Echo Weaver 언어 파일(`Copy/{lang}_copy` TextAsset) 형식 처리.

원본 형식: {"data": [{"id": ..., "copy": ..., "agent"?: ..., "speaker"?: ...}, ...]}
툴박스 어댑터는 배열을 다루지 않으므로 `{id: copy}` 평면 객체로 바꿔 추출·삽입하고,
빌드 때 원본 배열 구조(행 순서·필드·키 순서)를 그대로 두고 copy 값만 교체한다.
"""
from __future__ import annotations

import json
import re

from .common import EWError

GROUP_SUFFIX = re.compile(r"(_\d+[A-Z]?)+$")


def parse(raw: bytes) -> list[dict]:
    try:
        doc = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EWError("COPY_PARSE", f"언어 파일 JSON을 읽을 수 없습니다: {exc}") from exc
    if not isinstance(doc, dict) or set(doc) != {"data"} or not isinstance(doc["data"], list):
        raise EWError("COPY_SHAPE", "예상한 {\"data\": [...]} 구조가 아닙니다. 게임 형식이 바뀌었는지 확인하십시오.")
    rows = doc["data"]
    seen = set()
    for i, r in enumerate(rows):
        if not isinstance(r, dict) or not isinstance(r.get("id"), str) or not isinstance(r.get("copy"), str):
            raise EWError("COPY_ROW", f"{i}번째 행에 문자열 id/copy가 없습니다.")
        if r["id"] in seen:
            raise EWError("COPY_DUPLICATE_ID", f"중복 ID: {r['id']}")
        seen.add(r["id"])
    return rows


def flatten(rows: list[dict]) -> dict[str, str]:
    return {r["id"]: r["copy"] for r in rows}


def serialize(rows: list[dict]) -> bytes:
    """게임이 읽는 원본과 같은 압축 JSON(BOM 없음, UTF-8)으로 직렬화한다."""
    return json.dumps({"data": rows}, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def rebuild(base_rows: list[dict], targets: dict[str, str]) -> list[dict]:
    """원본 행 구조를 복사하고 copy만 바꾼다. targets에 없는 ID는 base의 값을 유지한다."""
    unknown = set(targets) - {r["id"] for r in base_rows}
    if unknown:
        raise EWError("COPY_UNKNOWN_ID", f"원본에 없는 ID {len(unknown)}개: {sorted(unknown)[:5]}")
    out = []
    for r in base_rows:
        row = dict(r)
        if r["id"] in targets:
            row["copy"] = targets[r["id"]]
        out.append(row)
    return out


def group_key(identifier: str) -> str:
    """연속 대사 묶음 키. 예: RIFT_T2_3 → RIFT_T2, NOVA_INTRO_12 → NOVA_INTRO."""
    return GROUP_SUFFIX.sub("", identifier) or identifier


def speaker_of(row: dict) -> str | None:
    agent = row.get("agent")
    if not isinstance(agent, str) or agent in ("", "None"):
        return None
    return agent


def json_pointer(identifier: str) -> str:
    return "/" + identifier.replace("~", "~0").replace("/", "~1")
