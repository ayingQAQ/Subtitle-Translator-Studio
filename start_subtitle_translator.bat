@echo off
setlocal enableextensions
cd /d "%~dp0"

echo [INFO] Subtitle Translator quick launcher

where uv >nul 2>&1
if errorlevel 1 (
    echo [ERROR] uv is not installed or not in PATH.
    echo         Install uv first: https://docs.astral.sh/uv/
    pause
    exit /b 1
)

if not exist ".env" (
    if exist ".env.example" (
        copy /y ".env.example" ".env" >nul
        echo [INFO] Created .env from .env.example
    )
)

if not exist ".venv\Scripts\python.exe" (
    echo [INFO] First run detected. Installing dependencies...
    call uv sync --all-groups
    if errorlevel 1 (
        echo [ERROR] Dependency install failed.
        pause
        exit /b 1
    )
)

echo [INFO] Opening browser: http://localhost:8501
start "" "http://localhost:8501"

echo [INFO] Starting Streamlit server...
call uv run streamlit run app.py

