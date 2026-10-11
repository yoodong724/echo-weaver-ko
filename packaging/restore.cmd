@echo off
chcp 65001 >nul
"%~dp0bin\EchoWeaverPatch.exe" restore
set "RESULT=%ERRORLEVEL%"
echo.
if "%RESULT%"=="0" (
  echo 원본 상태를 확인했습니다. "日本語"를 고르면 원래 일본어가 표시됩니다.
) else (
  echo 복구하지 못했습니다. 위 오류 메시지를 확인하십시오.
)
if not defined EW_NO_PAUSE pause
exit /b %RESULT%
