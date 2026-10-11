"""data.unity3d(UnityFS 번들) 읽기·수정 도우미.

UnityPy로 번들 안의 직렬화 파일을 열고, MonoBehaviour는 게임의 Managed DLL에서
생성한 타입트리로 읽고 쓴다. 원본 파일은 읽기만 하며 저장은 항상 새 경로에 한다.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Iterator

from .common import EWError

try:
    import UnityPy
    from UnityPy.helpers.TypeTreeGenerator import TypeTreeGenerator
except ImportError as exc:  # pragma: no cover - 환경 오류 안내
    raise EWError("DEPENDENCY_MISSING", "UnityPy가 필요합니다. `pip install -r requirements.txt`") from exc

TMP_FONT_ASSET = ("Unity.TextMeshPro", "TMPro", "TMP_FontAsset")
TMP_SETTINGS = ("Unity.TextMeshPro", "TMPro", "TMP_Settings")


class GameBundle:
    def __init__(self, bundle_path: Path, game_root: Path, unity_version: str | None = None):
        if not bundle_path.is_file():
            raise EWError("BUNDLE_MISSING", f"번들 파일이 없습니다: {bundle_path}")
        self.path = bundle_path
        self.game_root = game_root
        self.env = UnityPy.load(str(bundle_path))
        self.bundle = self.env.files[next(iter(self.env.files))]
        self.unity_version = unity_version or self.bundle.version_engine
        self._gen: TypeTreeGenerator | None = None
        self._scripts: dict[tuple[str, int], tuple[str, str, str]] | None = None

    # ---------------------------------------------------------- 파일·객체 탐색
    @property
    def files(self) -> dict[str, Any]:
        return {name: f for name, f in self.bundle.files.items() if hasattr(f, "objects")}

    def file(self, name: str):
        try:
            return self.files[name]
        except KeyError:
            raise EWError("ASSET_FILE_MISSING", f"번들 안에 {name} 이(가) 없습니다.") from None

    def objects(self, type_name: str | None = None) -> Iterator[Any]:
        for sf in self.files.values():
            for obj in sf.objects.values():
                if type_name is None or obj.type.name == type_name:
                    yield obj

    def text_assets(self) -> dict[str, Any]:
        """이름 → ObjectReader. 같은 이름이 여러 개면 리스트 대신 오류를 낸다."""
        found: dict[str, list[Any]] = {}
        for obj in self.objects("TextAsset"):
            name = obj.peek_name()
            found.setdefault(name, []).append(obj)
        return found

    def text_asset(self, name: str):
        hits = self.text_assets().get(name, [])
        if len(hits) != 1:
            raise EWError("TEXTASSET_AMBIGUOUS", f"TextAsset '{name}' 이(가) {len(hits)}개입니다.")
        return hits[0]

    # ---------------------------------------------------------- MonoBehaviour
    @property
    def generator(self) -> TypeTreeGenerator:
        if self._gen is None:
            gen = TypeTreeGenerator(self.unity_version)
            gen.load_local_game(str(self.game_root))
            self._gen = gen
        return self._gen

    def _script_index(self) -> dict[tuple[str, int], tuple[str, str, str]]:
        if self._scripts is None:
            idx = {}
            for obj in self.objects("MonoScript"):
                d = obj.read()
                idx[(obj.assets_file.name, obj.path_id)] = (d.m_AssemblyName, d.m_Namespace, d.m_ClassName)
            self._scripts = idx
        return self._scripts

    def mono_class(self, obj) -> tuple[str, str, str] | None:
        """MonoBehaviour 헤더의 m_Script PPtr를 직접 읽어 클래스를 찾는다."""
        obj.reset()
        rd = obj.reader
        rd.read_int(); rd.read_long()          # m_GameObject
        rd.read_u_byte(); rd.align_stream()    # m_Enabled
        file_id = rd.read_int(); path_id = rd.read_long()
        sf = obj.assets_file
        name = sf.name if file_id == 0 else sf.externals[file_id - 1].path.split("/")[-1]
        return self._script_index().get((name, path_id))

    def monobehaviours(self, cls: tuple[str, str, str]) -> list[Any]:
        return [o for o in self.objects("MonoBehaviour") if self.mono_class(o) == cls]

    def _nodes(self, cls: tuple[str, str, str]):
        asm, ns, name = cls
        return self.generator.get_nodes_up(asm, f"{ns}.{name}" if ns else name)

    def read_mb(self, obj, cls: tuple[str, str, str]) -> dict:
        return obj.read_typetree(self._nodes(cls))

    def write_mb(self, obj, cls: tuple[str, str, str], tree: dict) -> None:
        obj.save_typetree(tree, self._nodes(cls))

    def tmp_font_assets(self) -> dict[str, tuple[Any, dict]]:
        out = {}
        for obj in self.monobehaviours(TMP_FONT_ASSET):
            tree = self.read_mb(obj, TMP_FONT_ASSET)
            out[tree["m_Name"]] = (obj, tree)
        return out

    # ---------------------------------------------------------- 저장
    def save(self, out_path: Path, packer: str = "lz4") -> int:
        data = self.bundle.save(packer=packer)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(data)
        return len(data)
