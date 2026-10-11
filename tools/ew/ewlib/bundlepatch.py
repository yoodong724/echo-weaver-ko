"""원본 data.unity3d에 한국어 언어 파일·폰트·TMP 설정을 넣고 결과를 다시 읽어 확인한다.

`ew build`·`ew package`와 배포본 적용기(applier)가 함께 쓴다. 폰트는 fontbake로 구운 값을 FontData로 받는다.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from . import copydata
from .common import EWError
from .unity import TMP_FONT_ASSET, TMP_SETTINGS, GameBundle


@dataclass
class FontData:
    """TMP 폰트 에셋에 넣을 값. atlas는 Alpha8 원시 바이트(row 0 = bottom)."""
    atlas: bytes
    size: int
    padding: int
    source_name: str
    face_info: dict
    glyph_table: list[dict]
    character_table: list[dict]
    used_rects: list[dict]


def _slot_font(gb: GameBundle, cfg):
    name = cfg["target"]["slot_font_asset"]
    fonts = gb.tmp_font_assets()
    if name not in fonts:
        raise EWError("FONT_ASSET_MISSING", f"TMP 폰트 에셋 '{name}'을 찾지 못했습니다.")
    return fonts[name]


def compose_copy(gb: GameBundle, cfg, translations: dict[str, str]) -> bytes:
    """사용자 원본 번들의 원문 언어 파일 + 한국어 번역 → 슬롯 언어 파일(배포본 적용용)."""
    pattern = cfg["source"]["copy_asset_pattern"]
    raw = gb.text_asset(pattern.format(lang=cfg["source"]["language"])).read().m_Script.encode("utf-8", "surrogateescape")
    base = copydata.parse(raw)
    targets = dict(translations)
    if cfg["target"]["untranslated_fallback"] == "slot":
        slot_raw = gb.text_asset(pattern.format(lang=cfg["target"]["slot_language"])).read().m_Script
        slot_rows = copydata.flatten(copydata.parse(slot_raw.encode("utf-8", "surrogateescape")))
        targets = {k: translations.get(k, slot_rows[k]) for k in slot_rows}
    return copydata.serialize(copydata.rebuild(base, targets))


def patch_bundle(cfg, original: Path, ko_copy: bytes, font: FontData, game_root: Path) -> GameBundle:
    gb = GameBundle(original, game_root, cfg["game"].get("unity_version"))
    slot = cfg["target"]["slot_language"]
    # 1) 언어 파일
    ta = gb.text_asset(cfg["source"]["copy_asset_pattern"].format(lang=slot)).read()
    ta.m_Script = ko_copy.decode("utf-8", "surrogateescape")
    ta.save()
    # 2) TMP 폰트 에셋(슬롯 전용 폴백)
    obj, tree = _slot_font(gb, cfg)
    if tree["m_AtlasPadding"] != font.padding:
        raise EWError("PADDING_MISMATCH", f"원본 padding {tree['m_AtlasPadding']} ≠ 설정 {font.padding}. 머티리얼과 맞추십시오.")
    size = font.size
    tree["m_FaceInfo"].update(font.face_info)
    tree["m_GlyphTable"] = font.glyph_table
    tree["m_CharacterTable"] = font.character_table
    tree["m_UsedGlyphRects"] = font.used_rects
    tree["m_FreeGlyphRects"] = []
    tree["m_AtlasWidth"] = size
    tree["m_AtlasHeight"] = size
    tree["m_AtlasPopulationMode"] = 0
    tree["m_FontFeatureTable"] = {k: [] for k in tree["m_FontFeatureTable"]}
    tree["m_CreationSettings"]["atlasWidth"] = size
    tree["m_CreationSettings"]["atlasHeight"] = size
    tree["m_CreationSettings"]["characterSequence"] = ""
    tree["m_CreationSettings"]["sourceFontFileName"] = font.source_name
    if len(tree["m_AtlasTextures"]) != 1 or tree["m_AtlasTextures"][0]["m_FileID"] != 0:
        raise EWError("ATLAS_LAYOUT", "단일 내부 아틀라스 텍스처를 가진 폰트 에셋만 지원합니다.")
    gb.write_mb(obj, TMP_FONT_ASSET, tree)
    sf = obj.assets_file
    tex = sf.objects[tree["m_AtlasTextures"][0]["m_PathID"]].read()
    if tex.m_TextureFormat != 1:  # Alpha8
        raise EWError("ATLAS_FORMAT", f"아틀라스 형식 {tex.m_TextureFormat}은(는) 지원하지 않습니다(Alpha8만).")
    tex.m_Width = size
    tex.m_Height = size
    tex.m_CompleteImageSize = len(font.atlas)
    tex.m_MipCount = 1
    if hasattr(tex, "m_MipMap"):
        tex.m_MipMap = False
    tex.image_data = font.atlas
    if tex.m_StreamData is not None:
        tex.m_StreamData.path = ""
        tex.m_StreamData.offset = 0
        tex.m_StreamData.size = 0
    tex.save()
    # 머티리얼의 텍스처 크기 값
    mat_ref = tree["m_Material"]
    if mat_ref["m_FileID"] == 0 and mat_ref["m_PathID"]:
        mat = sf.objects[mat_ref["m_PathID"]].read()
        floats = mat.m_SavedProperties.m_Floats
        for i, (k, v) in enumerate(floats):
            if k in ("_TextureWidth", "_TextureHeight"):
                floats[i] = (k, float(size))
            if k == "_GradientScale" and abs(v - (font.padding + 1)) > 1e-3:
                raise EWError("GRADIENT_SCALE", f"_GradientScale={v}, 예상 {font.padding + 1}")
        mat.save()
    # 3) TMP Settings: 한글 어절 단위 줄바꿈
    if cfg["target"].get("tmp_modern_hangul_line_breaking", True):
        for o in gb.monobehaviours(TMP_SETTINGS):
            t = gb.read_mb(o, TMP_SETTINGS)
            t["m_UseModernHangulLineBreakingRules"] = 1
            gb.write_mb(o, TMP_SETTINGS, t)
    return gb


def verify_bundle(cfg, path: Path, ko_copy: bytes, font: FontData, game_root: Path,
                  original: Path | None = None) -> dict:
    """저장한 번들을 다시 열어 바뀐 값을 읽어 본다(G17: 실제 출력 재확인)."""
    gb = GameBundle(path, game_root, cfg["game"].get("unity_version"))
    extra = {}
    if original is not None:
        # 바꾸지 않은 객체가 그대로인지: 파일별 객체 수와 원문 언어 파일 바이트 비교
        og = GameBundle(original, game_root, cfg["game"].get("unity_version"))
        extra["object_counts_equal"] = ({n: len(f.objects) for n, f in og.files.items()}
                                        == {n: len(f.objects) for n, f in gb.files.items()})
        src_name = cfg["source"]["copy_asset_pattern"].format(lang=cfg["source"].get("language", "en"))
        extra["source_copy_untouched"] = (og.text_asset(src_name).get_raw_data()
                                          == gb.text_asset(src_name).get_raw_data())
    slot = cfg["target"]["slot_language"]
    got = gb.text_asset(cfg["source"]["copy_asset_pattern"].format(lang=slot)).read().m_Script.encode("utf-8", "surrogateescape")
    obj, tree = _slot_font(gb, cfg)
    tex = obj.assets_file.objects[tree["m_AtlasTextures"][0]["m_PathID"]].read()
    settings = [gb.read_mb(o, TMP_SETTINGS)["m_UseModernHangulLineBreakingRules"] for o in gb.monobehaviours(TMP_SETTINGS)]
    checks = {
        "copy_identical": got == ko_copy,
        "copy_parses": len(copydata.parse(got)) > 0,
        "font_characters": len(tree["m_CharacterTable"]) == len(font.character_table),
        "atlas_identical": bytes(tex.get_image_data()) == font.atlas,
        "modern_hangul_line_breaking": settings == [1] * len(settings),
        **extra,
    }
    return {"passed": all(checks.values()), **checks}
