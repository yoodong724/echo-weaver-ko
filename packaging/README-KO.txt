Echo Weaver 비공식 한국어 패치 1.1.1 (시험 배포)
============================================

지원: PC 게임패스(Xbox 앱)판 1.0.2.0 / Windows x64
스팀판에서의 작동은 보장하지 않습니다. Python 설치나 인터넷 연결은 필요 없습니다.

설치
1. 게임을 종료하세요. 기존 패치를 사용했다면 기존 KoreanPatch\restore.cmd로
   먼저 복구하고 기존 KoreanPatch 폴더를 제거하세요. 새 ZIP을 덮어쓰기 전에 복구해야 합니다.
2. ZIP을 Echo Weaver_Data가 있는 게임 폴더에 풀어 KoreanPatch 폴더가 생기게 하세요.
   예: E:\XboxGames\Echo Weaver\Content\KoreanPatch
3. KoreanPatch\install.cmd를 실행하세요. 한글 폰트를 생성하므로 잠시 기다리세요.
4. 게임 설정의 Language에서 日本語(일본어)를 선택하면 한국어가 표시됩니다.

복구
게임을 종료한 뒤 KoreanPatch\restore.cmd를 실행하세요.
게임 업데이트 후이거나 원본 백업이 없으면 Xbox 앱의 게임 관리 → 파일 → 확인 및 복구를
사용하세요. 지원 버전과 게임 파일이 다르면 설치가 거부됩니다.

변경과 확인 범위
1.1.1에서는 단말의 사용자 표기를 한국어로 바꾸었으며, 기존 꺾쇠 크기 수정도 포함합니다.
이전 버전에서 타이틀·설정·인트로·저장 후 재실행을 확인했고,
1.1.1은 Windows 게임 사본에서 설치·복구를 확인했습니다.
최신 변경의 실제 게임 화면과 NPC 대화·후반부·엔딩 등 전체 플레이는 확인하지 못했습니다.
이미지·로고 속 글자는 번역하지 않았습니다.

다운로드와 공개 소스
https://github.com/yoodong724/echo-weaver-ko/releases
Source code (zip)은 설치 파일이 아닙니다.
공개 소스에는 게임 원문·번역 텍스트, 폰트, 게임 리소스와 중간 산출물을 포함하지 않습니다.
이 자료들이 빠져 있으므로 공개된 소스코드만으로 배포 패치를 재현할 수 없습니다.
배포 ZIP에는 설치에 필요한 번역과 원본 Pretendard 폰트가 들어 있으며,
원본 게임 파일과 변환한 폰트는 포함하지 않습니다. 폰트는 사용자 PC에서 생성합니다.
Pretendard 폰트 라이선스는 payload\Pretendard-OFL.txt에,
실행기와 라이브러리 라이선스는 licenses 폴더에 동봉했습니다.
This software is based in part on the work of the FreeType Team.

문제 제보
https://github.com/yoodong724/echo-weaver-ko/issues
패치·게임 버전, 오류 메시지 또는 문제 장면의 스크린샷을 남겨 주세요.
