@echo off
cd /d "%~dp0"
call uv run --locked python launcher.py --stop
if errorlevel 1 pause
