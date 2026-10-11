"""TextMeshPro 정적 SDF 아틀라스를 오프라인으로 굽는다.

게임의 TMP 폰트 에셋은 정적(Static) 아틀라스라서 한글 글리프를 런타임에 만들 수 없다.
이 모듈은 한국어 폰트에서 필요한 문자를 SDF로 렌더링해 TMP 글리프·문자 테이블과
Alpha8 아틀라스를 만든다. 좌표계는 TMP/TextCore와 같이 아래쪽이 y=0이다.
"""
from __future__ import annotations

import io
import math
from dataclasses import dataclass, field
from pathlib import Path

import freetype
import numpy as np
from fontTools.ttLib import TTFont
from scipy.ndimage import distance_transform_edt

from .bundlepatch import FontData
from .common import EWError


@dataclass
class Glyph:
    unicode: int
    index: int
    width: int
    height: int
    bearing_x: int
    bearing_y: int
    advance: float
    sdf: np.ndarray | None = field(default=None, repr=False)  # (h+2p, w+2p), row 0 = bottom
    x: int = 0
    y: int = 0


@dataclass
class BakeResult:
    glyphs: list[Glyph]
    atlas: np.ndarray            # (H, W) uint8, row 0 = bottom
    face_info: dict
    missing: list[int]
    used_rects: list[dict]


def ksx1001_hangul() -> list[str]:
    """KS X 1001 완성형 한글 2,350자."""
    out = []
    for hi in range(0xB0, 0xC9):
        for lo in range(0xA1, 0xFF):
            try:
                ch = bytes([hi, lo]).decode("euc-kr")
            except UnicodeDecodeError:
                continue
            if "가" <= ch <= "힣":
                out.append(ch)
    return out


EXTRA_PUNCT = "…·‘’“”「」『』〈〉《》–—―~～•※♪★☆○●■□▲△▶◀←→↑↓·°%‰"


def build_charset(spec: list[str], texts: list[str]) -> list[int]:
    chars: set[str] = set()
    for item in spec:
        if item == "ascii":
            chars.update(chr(c) for c in range(0x20, 0x7F))
        elif item == "ksx1001":
            chars.update(ksx1001_hangul())
        elif item == "jamo":
            chars.update(chr(c) for c in range(0x3131, 0x318F))
        elif item == "punct":
            chars.update(EXTRA_PUNCT)
        elif item == "translations":
            for t in texts:
                chars.update(t)
        else:
            raise EWError("CHARSET_UNKNOWN", f"알 수 없는 문자 집합: {item}")
    return sorted(ord(c) for c in chars if c not in "\n\r\t")


class SdfBaker:
    def __init__(self, font_path: Path, point_size: int, padding: int, supersample: int = 8,
                 spread: float | None = None):
        if not font_path.is_file():
            raise EWError("FONT_MISSING", f"폰트 파일이 없습니다: {font_path}")
        self.font_path = font_path
        # FreeType의 경로 API는 CP949 Windows에서 UTF-8 한글 폴더를 열지 못하므로 같은 바이트를 메모리로 넘긴다.
        self.face = freetype.Face(io.BytesIO(font_path.read_bytes()))
        self.ps = point_size
        self.pad = padding
        self.ss = supersample
        # SDF 거리 정규화 폭(픽셀). TMP 머티리얼의 _GradientScale(= padding + 1)과 맞춘다.
        self.spread = spread if spread is not None else padding + 1
        self.tt = TTFont(str(font_path), fontNumber=0, lazy=True)
        self.cmap = self.tt.getBestCmap()

    def glyph(self, cp: int) -> Glyph | None:
        gi = self.face.get_char_index(cp)
        if gi == 0:
            return None
        ss, pad = self.ss, self.pad
        self.face.set_pixel_sizes(0, self.ps * ss)
        self.face.load_glyph(gi, freetype.FT_LOAD_RENDER | freetype.FT_LOAD_NO_HINTING)
        g = self.face.glyph
        bm = g.bitmap
        advance = g.advance.x / 64.0 / ss
        if bm.width == 0 or bm.rows == 0:
            return Glyph(cp, gi, 0, 0, 0, 0, advance, None)
        xmin, xmax = g.bitmap_left / ss, (g.bitmap_left + bm.width) / ss
        ymax, ymin = g.bitmap_top / ss, (g.bitmap_top - bm.rows) / ss
        x0, x1 = math.floor(xmin), math.ceil(xmax)
        y0, y1 = math.floor(ymin), math.ceil(ymax)
        rw, rh = x1 - x0, y1 - y0
        W, H = (rw + 2 * pad) * ss, (rh + 2 * pad) * ss
        canvas = np.zeros((H, W), dtype=bool)          # row 0 = top
        ox = g.bitmap_left - (x0 - pad) * ss
        oy = (y1 + pad) * ss - g.bitmap_top
        buf = np.array(bm.buffer, dtype=np.uint8).reshape(bm.rows, bm.pitch)[:, :bm.width]
        canvas[oy:oy + bm.rows, ox:ox + bm.width] = buf >= 128
        inside = distance_transform_edt(canvas)
        outside = distance_transform_edt(~canvas)
        signed = np.where(canvas, -(inside - 0.5), outside - 0.5) / ss   # >0 = 바깥, 단위: 아틀라스 픽셀
        low = signed.reshape(H // ss, ss, W // ss, ss).mean(axis=(1, 3))
        alpha = np.clip(0.5 - low / (2.0 * self.spread), 0.0, 1.0)
        sdf = np.round(alpha * 255).astype(np.uint8)[::-1]          # row 0 = bottom
        return Glyph(cp, gi, rw, rh, x0, y1, advance, sdf)

    def face_info(self) -> dict:
        tt = self.tt
        upem = tt["head"].unitsPerEm
        s = self.ps / upem
        hhea, os2, post = tt["hhea"], tt["OS/2"], tt["post"]
        name = tt["name"]
        family = name.getBestFamilyName() or self.font_path.stem
        style = name.getBestSubFamilyName() or "Regular"

        def top_of(ch: str, fallback: float) -> float:
            gi = self.face.get_char_index(ord(ch))
            if not gi:
                return fallback
            self.face.set_pixel_sizes(0, self.ps)
            self.face.load_glyph(gi, freetype.FT_LOAD_NO_HINTING)
            return self.face.glyph.metrics.horiBearingY / 64.0

        ascent = hhea.ascent * s
        descent = hhea.descent * s
        line_height = (hhea.ascent - hhea.descent + hhea.lineGap) * s
        return {
            "m_FaceIndex": 0,
            "m_FamilyName": family,
            "m_StyleName": style,
            "m_PointSize": float(self.ps),
            "m_Scale": 1.0,
            "m_UnitsPerEM": upem,
            "m_LineHeight": line_height,
            "m_AscentLine": ascent,
            "m_CapLine": top_of("H", 0.7 * self.ps),
            "m_MeanLine": top_of("x", 0.5 * self.ps),
            "m_Baseline": 0.0,
            "m_DescentLine": descent,
            "m_SuperscriptOffset": ascent,
            "m_SuperscriptSize": 0.5,
            "m_SubscriptOffset": descent,
            "m_SubscriptSize": 0.5,
            "m_UnderlineOffset": post.underlinePosition * s,
            "m_UnderlineThickness": max(post.underlineThickness * s, 1.0),
            "m_StrikethroughOffset": getattr(os2, "yStrikeoutPosition", upem * 0.25) * s,
            "m_StrikethroughThickness": max(getattr(os2, "yStrikeoutSize", upem * 0.05) * s, 1.0),
            "m_TabWidth": self._advance(ord(" ")) * 10,
        }

    def _advance(self, cp: int) -> float:
        gi = self.face.get_char_index(cp)
        self.face.set_pixel_sizes(0, self.ps)
        self.face.load_glyph(gi, freetype.FT_LOAD_NO_HINTING)
        return self.face.glyph.advance.x / 64.0


def pack(glyphs: list[Glyph], padding: int, width: int, height: int) -> list[dict]:
    """선반(shelf) 방식으로 배치. 글리프 사각형 사이에는 padding*2 이상의 간격을 둔다."""
    order = sorted((g for g in glyphs if g.sdf is not None), key=lambda g: (-g.height, -g.width, g.unicode))
    x = y = shelf_h = 0
    used = []
    for g in order:
        cw, ch = g.width + 2 * padding, g.height + 2 * padding
        if x + cw > width:
            x, y, shelf_h = 0, y + shelf_h, 0
        if y + ch > height:
            raise EWError("ATLAS_FULL", f"{width}x{height} 아틀라스에 글리프가 모두 들어가지 않습니다. 크기를 늘리거나 문자 집합을 줄이십시오.")
        g.x, g.y = x + padding, y + padding
        used.append({"m_X": x, "m_Y": y, "m_Width": cw, "m_Height": ch})
        x += cw
        shelf_h = max(shelf_h, ch)
    return used


def bake(font_path: Path, codepoints: list[int], point_size: int, padding: int, atlas_size: int,
         supersample: int = 8, spread: float | None = None, progress=None) -> BakeResult:
    baker = SdfBaker(font_path, point_size, padding, supersample, spread)
    glyphs, missing, seen_index = [], [], {}
    for i, cp in enumerate(codepoints):
        g = baker.glyph(cp)
        if g is None:
            missing.append(cp)
            continue
        glyphs.append(g)
        if progress and i % 250 == 0:
            progress(i, len(codepoints))
    used = pack(glyphs, padding, atlas_size, atlas_size)
    atlas = np.zeros((atlas_size, atlas_size), dtype=np.uint8)
    for g in glyphs:
        if g.sdf is None:
            continue
        h, w = g.sdf.shape
        atlas[g.y - padding:g.y - padding + h, g.x - padding:g.x - padding + w] = g.sdf
    return BakeResult(glyphs, atlas, baker.face_info(), missing, used)


def tmp_tables(result: BakeResult) -> tuple[list[dict], list[dict]]:
    """TMP_FontAsset의 m_GlyphTable, m_CharacterTable 형식으로 변환한다."""
    glyph_rows, char_rows, done = [], [], set()
    for g in sorted(result.glyphs, key=lambda g: g.unicode):
        if g.index not in done:
            done.add(g.index)
            glyph_rows.append({
                "m_Index": g.index,
                "m_Metrics": {"m_Width": float(g.width), "m_Height": float(g.height),
                              "m_HorizontalBearingX": float(g.bearing_x), "m_HorizontalBearingY": float(g.bearing_y),
                              "m_HorizontalAdvance": float(g.advance)},
                "m_GlyphRect": {"m_X": g.x, "m_Y": g.y, "m_Width": g.width, "m_Height": g.height},
                "m_Scale": 1.0,
                "m_AtlasIndex": 0,
                "m_ClassDefinitionType": 0,
            })
        char_rows.append({"m_ElementType": 1, "m_Unicode": g.unicode, "m_GlyphIndex": g.index, "m_Scale": 1.0})
    glyph_rows.sort(key=lambda r: r["m_Index"])
    return glyph_rows, char_rows


def font_data(result: BakeResult, font: dict) -> FontData:
    """굽기 결과 → 번들에 넣을 값. font는 설정의 font 항목(atlas_size·padding·path)."""
    glyphs, chars = tmp_tables(result)
    return FontData(np.ascontiguousarray(result.atlas).tobytes(), font["atlas_size"], font["padding"],
                    Path(font["path"]).name, result.face_info, glyphs, chars, result.used_rects)


def render_preview(result: BakeResult, text: str, padding: int, scale: float = 1.0,
                   spread: float | None = None) -> np.ndarray:
    """아틀라스와 글리프 테이블만으로 문자열을 다시 그려 배치·메트릭을 눈으로 확인한다.

    TMP 셰이더처럼 사각형 + padding 영역을 샘플링하고 0.5 임계값으로 그린다(행 0 = 위).
    """
    by_cp = {g.unicode: g for g in result.glyphs}
    fi = result.face_info
    asc, desc = fi["m_AscentLine"], fi["m_DescentLine"]
    lines = text.split("\n")
    line_h = fi["m_LineHeight"]
    width = int(max(sum(by_cp[ord(c)].advance if ord(c) in by_cp else fi["m_PointSize"] * 0.5 for c in ln)
                    for ln in lines) + padding * 4)
    height = int(line_h * len(lines) + padding * 2)
    img = np.zeros((height, width), dtype=np.uint8)
    atlas_top_down = result.atlas[::-1]
    A = result.atlas.shape[0]
    for li, ln in enumerate(lines):
        pen_x = float(padding)
        baseline = padding + asc + li * line_h
        for c in ln:
            g = by_cp.get(ord(c))
            if g is None:
                pen_x += fi["m_PointSize"] * 0.5
                continue
            if g.sdf is not None:
                ax0, ay0 = g.x - padding, g.y - padding
                h, w = g.height + 2 * padding, g.width + 2 * padding
                # 아틀라스(아래 원점) → 위 원점 좌표
                patch = atlas_top_down[A - (ay0 + h):A - ay0, ax0:ax0 + w]
                left = int(round(pen_x + g.bearing_x - padding))
                top = int(round(baseline - g.bearing_y - padding))
                mask = (patch >= 128).astype(np.uint8) * 255
                y0, x0 = max(top, 0), max(left, 0)
                y1, x1 = min(top + h, height), min(left + w, width)
                if y1 > y0 and x1 > x0:
                    sub = mask[y0 - top:y1 - top, x0 - left:x1 - left]
                    img[y0:y1, x0:x1] = np.maximum(img[y0:y1, x0:x1], sub)
            pen_x += g.advance
    return img
