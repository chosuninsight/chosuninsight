@echo off
cd /d "%~dp0backend"
"%~dp0venv\Scripts\python.exe" -m uvicorn main:app --reload --port 8000
pause
