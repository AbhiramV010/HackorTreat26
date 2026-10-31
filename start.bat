@echo off
REM Rigor one-shot launcher: Ollama up, Gemma loaded and kept warm, then the demo with standby.
REM Usage:  start.bat [COM4] [gemma3:4b] [extra spider.py args...]
REM Examples:
REM   start.bat                     -> COM4, gemma3:4b, fullscreen
REM   start.bat COM4 gemma3:1b      -> faster model
REM   start.bat COM4 gemma3:4b --windowed --sim   (--sim ignores the port)
setlocal
cd /d "%~dp0"

set PORT=%~1
if "%PORT%"=="" set PORT=COM4
set MODEL=%~2
if "%MODEL%"=="" set MODEL=gemma3:4b
set EXTRA=%3 %4 %5 %6 %7 %8

set OLLAMA=%LOCALAPPDATA%\Programs\Ollama\ollama.exe
if not exist "%OLLAMA%" set OLLAMA=ollama

echo [1/4] Ollama server
curl -s -m 2 http://localhost:11434/api/tags >nul 2>&1
if errorlevel 1 (
    start "ollama serve" /min "%OLLAMA%" serve
    REM wait up to 20 s for the API
    for /l %%i in (1,1,20) do (
        curl -s -m 1 http://localhost:11434/api/tags >nul 2>&1 && goto :up
        timeout /t 1 /nobreak >nul
    )
    echo       [FAIL] Ollama did not come up, demo will use canned lines
    goto :warm_skip
)
:up
echo       [OK] Ollama responding

echo [2/4] Loading %MODEL% into memory with keep_alive -1 (first load can take ~20 s)
curl -s -m 180 http://localhost:11434/api/generate -d "{\"model\":\"%MODEL%\",\"keep_alive\":-1,\"prompt\":\"ok\",\"stream\":false}" >nul 2>&1
if errorlevel 1 (echo       [FAIL] model load, check "ollama list") else (echo       [OK] model loaded)

echo [3/4] Keep-warm pinger (every 4 min, closes when this window closes)
start "gemma keep-warm" /min python -c "import requests,time;exec(\"while 1:\n try: requests.post('http://localhost:11434/api/generate',json={'model':'%MODEL%','keep_alive':-1,'prompt':'ok','stream':False},timeout=60)\n except Exception: pass\n time.sleep(240)\")"
:warm_skip

echo [4/4] Rigor  (port %PORT%, model %MODEL%) %EXTRA%
python -u spider.py --standby --port %PORT% --model %MODEL% %EXTRA%

echo.
echo Rigor exited. Stopping keep-warm pinger.
taskkill /fi "WINDOWTITLE eq gemma keep-warm*" /f >nul 2>&1
endlocal
