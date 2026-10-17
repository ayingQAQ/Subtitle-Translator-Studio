@echo off
cd /d "%~dp0"
where uv >nul 2>&1
if errorlevel 1 (
    echo Install uv first: https://docs.astral.sh/uv/
    pause
    exit /b 1
)
call uv run --locked --no-dev python launcher.py
if errorlevel 1 pause

