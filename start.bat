@echo off
rem Start Word Bank and open it in the browser. Requires uv: https://docs.astral.sh/uv/
cd /d "%~dp0"
uv run server.py
pause
