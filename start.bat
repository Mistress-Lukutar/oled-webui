@echo off
rem Bootstrap and start LuminaFlowUI on Windows.
setlocal
cd /d "%~dp0"

if not exist .venv (
    echo Creating virtual environment...
    py -3.11 -m venv .venv || python -m venv .venv || goto :error
)

call .venv\Scripts\activate.bat
pip install --quiet -e ".[dev]" || goto :error

if not exist static\dist\index.html (
    echo Building frontend...
    pushd frontend
    call npm install || goto :error
    call npm run build || goto :error
    popd
)

echo Starting LuminaFlowUI on http://127.0.0.1:8090
python run.py
goto :eof

:error
echo Startup failed.
exit /b 1
