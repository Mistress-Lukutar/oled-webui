@echo off
rem File:    start.bat
rem Brief:   Launch LuminaFlowUI after setup.bat has prepared the machine.
rem Author:  Mistress-Lukutar
rem Date:    2026-10-01
rem Version: v0.5.2
setlocal
cd /d "%~dp0"

if not exist .venv\Scripts\python.exe (
    echo .venv not found - run setup.bat first.
    exit /b 2
)

if not exist static\dist\index.html (
    echo static\dist is missing - run setup.bat first.
    exit /b 2
)

rem Prefer a locally unpacked ffmpeg (setup.bat fallback) over PATH.
if exist "%~dp0tools\ffmpeg\bin\ffmpeg.exe" set "PATH=%~dp0tools\ffmpeg\bin;%PATH%"

echo Starting LuminaFlowUI on http://127.0.0.1:8090
.venv\Scripts\python.exe run.py
