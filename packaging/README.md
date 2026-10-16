# 패치 실행기 소스

이 저장소에는 설치·복구 실행기, Unity 번들 편집, 한글 SDF 폰트 생성 코드와 Windows 실행기 빌드·검사 스크립트만 포함합니다.
번역 작업 도구·프롬프트·검수 기록·중간 산출물은 제외했습니다.

게임 원문·번역 텍스트, 폰트, 원본 게임 파일과 배포용 입력 자료는 포함하지 않습니다.
따라서 **공개된 소스코드만으로 Releases의 배포 패치를 재현할 수 없습니다.**
빌드·게임 사본 검사 스크립트도 별도의 로컬 입력 자료가 필요합니다.

`launcher.py` → `tools/ew/ewlib/applier.py`가 설치·복구를 처리합니다.
`build-windows.ps1`과 `build_windows.py`는 별도로 준비된 `KoreanPatch` 입력 폴더를 Windows 실행기와 함께 묶는 코드입니다.
라이브러리 의존성은 `requirements.txt`, 외부 라이선스·출처 고지는 `licenses/`에 있습니다.

게임 자료 없이 실행 가능한 기본 검사는 다음과 같습니다. 원본 DLL이 필요한 검사는 건너뜁니다.

```sh
python3 -m unittest discover -s tools/ew/tests -v
```

패치 사용자는 [Releases](https://github.com/yoodong724/echo-weaver-ko/releases)의 설치 ZIP을 받으세요.

배포 ZIP은 게임 버전을 기준으로 `EchoWeaver-KO-1.0.5.0.zip`처럼 이름을 붙입니다.
같은 게임 버전의 추가 업데이트는 `-rc1.zip`, `-rc2.zip`, `-rc3.zip` 순입니다.
1.0.5.0부터 패치 버전은 파일명과 같습니다(예: `1.0.5.0`, `1.0.5.0-rc1`).
