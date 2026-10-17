@echo off
cd /d "%~dp0"
call uv run --locked --no-dev python launcher.py --stop
if errorlevel 1 pause
