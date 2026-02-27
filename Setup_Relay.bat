@echo off
title Firefox Relay Setup
cd /d "%~dp0"

if not exist "venv\Scripts\python.exe" (
    echo [ERR] Virtual environment tidak ditemukan!
    echo       Jalankan Launcher.bat terlebih dahulu untuk setup.
    pause
    exit /b 1
)

call venv\Scripts\activate
python App\relay_setup.py
