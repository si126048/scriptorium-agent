@echo off
title Scriptorium Agent - Desktop Dev
echo ============================================
echo   Scriptorium Agent - Desktop Development
echo ============================================
echo.

:: Ensure data directory exists
if not exist "%~dp0data" mkdir "%~dp0data"

:: Resolve Python: prefer .venv, fallback to system
if exist "%~dp0.venv\Scripts\python.exe" (
    set "PYTHON=%~dp0.venv\Scripts\python.exe"
) else (
    echo [WARN] .venv not found -- falling back to system python
    set "PYTHON=python"
)

:: Check if backend is already running
curl -s http://127.0.0.1:8000/health >nul 2>&1
if %errorlevel% equ 0 (
    echo [OK] Backend already running on :8000
) else (
    echo [..] Starting backend...
    start "Scriptorium Backend" cmd /c "cd /d %~dp0 && "%~dp0.venv\Scripts\python.exe" -m uvicorn scriptorium.api:app --host 127.0.0.1 --port 8000 2>nul || python -m uvicorn scriptorium.api:app --host 127.0.0.1 --port 8000"
    timeout /t 3 /nobreak >nul
)

:: Launch Tauri dev
echo [..] Starting Tauri desktop...
echo.
set "PATH=%USERPROFILE%\.cargo\bin;%PATH%"
cargo tauri dev
