@echo off
rem File:    supervisor.bat
rem Brief:   Restart loop for the "LuminaFlowUI" scheduled task (runs at logon).
rem Author:  Mistress-Lukutar
rem Date:    2026-10-01
rem Version: v0.5.2
setlocal
:loop
rem Exit code 2 from start.bat means "fix setup first" - stop looping.
call "%~dp0..\start.bat"
if errorlevel 2 (
    echo start.bat reports a setup problem - supervisor stopped. Run setup.bat, then start the task again.
    exit /b 1
)
echo LuminaFlowUI exited, restarting in 3 seconds...
timeout /t 3 /nobreak >nul
goto loop
