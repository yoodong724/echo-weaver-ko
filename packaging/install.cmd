@echo off
chcp 65001 >nul
"%~dp0bin\EchoWeaverPatch.exe" install
set "RESULT=%ERRORLEVEL%"
echo.
if "%RESULT%"=="0" (
  echo 설치 완료. 타이틀 설정의 Language에서 "한국어"를 고르면 한국어가 표시됩니다.
) else (
  echo 설치하지 못했습니다. 위 오류 메시지를 확인하십시오.
)
if not defined EW_NO_PAUSE pause
exit /b %RESULT%
