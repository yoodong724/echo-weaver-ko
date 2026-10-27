# Echo Weaver 한글패치

**PC 게임패스(Xbox 앱)판 1.0.8.0 / Windows x64**용 비공식 한국어 패치 1.0.8.0 시험 배포본입니다. 패치 버전은 지원 게임 버전과 같으며, 같은 게임 버전의 추가 수정은 `-rc1`, `-rc2` 순으로 붙습니다. **스팀판에서의 작동은 보장하지 않습니다.**

[패치 다운로드](https://github.com/yoodong724/echo-weaver-ko/releases/download/v1.0.8.0/EchoWeaver-KO-1.0.8.0.zip) · [SHA-256 체크섬](https://github.com/yoodong724/echo-weaver-ko/releases/download/v1.0.8.0/EchoWeaver-KO-1.0.8.0.sha256) · `Source code (zip)`은 설치 파일이 아닙니다. Python 설치는 필요 없습니다.

1. 게임을 종료하세요. 기존 패치를 사용했다면 기존 `KoreanPatch` 폴더를 제거하세요. 게임이 아직 업데이트되지 않았다면 먼저 기존 `KoreanPatch\restore.cmd`로 복구하세요. 게임이 이미 업데이트됐다면 기존 `restore.cmd`는 동작하지 않으므로 폴더만 제거하면 됩니다. 이전 버전이 남긴 원본 백업(`*.original`)은 새 설치기가 확인 후 정리합니다.
2. ZIP을 `Echo Weaver_Data`가 있는 게임 폴더(예: `E:\XboxGames\Echo Weaver\Content`)에 풀어 `KoreanPatch` 폴더가 생기게 하세요.
3. `KoreanPatch\install.cmd`를 실행하세요. 설치 중 한글 폰트를 생성하므로 잠시 기다리세요.
4. 게임 설정의 Language에서 **한국어**를 선택하면 한국어가 표시됩니다.

복구는 게임을 종료한 뒤 `KoreanPatch\restore.cmd`를 실행하세요. 복구가 끝나면 게임 폴더의 원본 백업(`*.original`)도 정리됩니다. 게임 업데이트 후이거나 원본 백업이 없으면 Xbox 앱의 **게임 관리 → 파일 → 확인 및 복구**를 사용하세요. 지원 버전과 게임 파일이 다르면 설치가 거부됩니다.

1.0.8.0은 게임 1.0.8.0에 대응합니다. 신규 텍스트 8개와 원문 변경 14개를 반영하고, 기존 동일 원문 3,075개의 번역을 유지했습니다. 새 게임 번들과 DLL에 맞춰 설치 호환성을 갱신했습니다.

공개 소스에는 게임 원문·번역 텍스트, 폰트, 게임 리소스와 중간 산출물을 포함하지 않습니다. **이 자료들이 빠져 있으므로 공개된 소스코드만으로 배포 패치를 재현할 수 없습니다.** 설치에는 Releases의 패치 ZIP을 사용하세요.
