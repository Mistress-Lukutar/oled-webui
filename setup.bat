@echo off
rem File:    setup.bat
rem Brief:   Double-click entry point for scripts\setup.ps1 (one-time install).
rem Author:  Mistress-Lukutar
rem Date:    2026-10-01
rem Version: v0.5.2
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\setup.ps1" %*
set "SETUP_EXITCODE=%ERRORLEVEL%"
echo.
rem Pause only when launched by double-click, so the summary stays visible.
echo %cmdcmdline% | find /i "%~f0" >nul && pause
exit /b %SETUP_EXITCODE%
