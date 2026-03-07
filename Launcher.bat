@echo off
chcp 65001 > nul
setlocal EnableDelayedExpansion
title Gemini Veo Auto Generator
color 0A

:: ============================================================
::  GEMINI VEO AUTO GENERATOR — LAUNCHER
::  Sekali klik: install semua kebutuhan + langsung jalan
:: ============================================================

cls
echo.
echo  ╔══════════════════════════════════════════════════╗
echo  ║        GEMINI VEO AUTO GENERATOR               ║
echo  ║        Automation Tool by ReenzAuto             ║
echo  ╚══════════════════════════════════════════════════╝
echo.
echo  Launcher akan otomatis setup semua kebutuhan...
echo  Mohon tunggu dan jangan tutup window ini.
echo.
echo  ────────────────────────────────────────────────────
echo.

:: ─── STEP 1: CEK PYTHON ──────────────────────────────────
echo  [1/6] Memeriksa instalasi Python...
python --version > nul 2>&1
if errorlevel 1 (
    color 0C
    echo.
    echo  ╔══════════════════════════════════════════════════╗
    echo  ║  [ERROR] PYTHON TIDAK DITEMUKAN!                ║
    echo  ╚══════════════════════════════════════════════════╝
    echo.
    echo  Python belum terinstall atau tidak ada di PATH.
    echo.
    echo  Cara install Python:
    echo  1. Buka browser, pergi ke: https://www.python.org/downloads/
    echo  2. Download Python 3.9 atau lebih baru
    echo  3. Saat install, CENTANG "Add Python to PATH"
    echo  4. Setelah selesai, jalankan Launcher.bat lagi
    echo.
    echo  Tekan tombol apapun untuk membuka halaman download Python...
    pause > nul
    start https://www.python.org/downloads/
    exit /b 1
)
for /f "tokens=2" %%V in ('python --version 2^>^&1') do set PY_VER=%%V
echo      [OK] Python %PY_VER% ditemukan.
echo.

:: ─── STEP 2: CEK / BUAT VIRTUAL ENVIRONMENT ─────────────
echo  [2/6] Memeriksa Virtual Environment...
if not exist ".venv\Scripts\activate.bat" (
    echo      Membuat Virtual Environment baru (.venv)...
    python -m venv .venv
    if errorlevel 1 (
        color 0C
        echo.
        echo  [ERROR] Gagal membuat Virtual Environment!
        echo     Pastikan modul 'venv' tersedia.
        echo.
        pause
        exit /b 1
    )
    echo      [OK] Virtual Environment berhasil dibuat.
) else (
    echo      [OK] Virtual Environment sudah ada.
)
echo.

:: ─── STEP 3: AKTIFKAN VENV ───────────────────────────────
echo  [3/6] Mengaktifkan Virtual Environment...
call .venv\Scripts\activate.bat
echo      [OK] Virtual Environment aktif.
echo.

:: ─── STEP 4: INSTALL / UPDATE DEPENDENCIES ───────────────
echo  [4/6] Menginstall / memperbarui dependencies...
echo      (selenium, selenium-stealth, beautifulsoup4, PySide6, dll)
echo.
pip install -r requirements.txt --quiet --disable-pip-version-check
if errorlevel 1 (
    color 0C
    echo.
    echo  [ERROR] Gagal install dependencies!
    echo.
    echo  Kemungkinan penyebab:
    echo  - Tidak ada koneksi internet
    echo  - pip bermasalah
    echo.
    echo  Coba jalankan manual:
    echo     pip install -r requirements.txt
    echo.
    pause
    exit /b 1
)
echo      [OK] Semua dependencies terinstall.
echo.

:: ─── STEP 5: CEK CONFIG.JSON ─────────────────────────────
echo  [5/6] Memeriksa file konfigurasi...
if not exist "config.json" (
    if exist "config.default.json" (
        copy "config.default.json" "config.json" > nul
        echo      [INFO] config.json dibuat dari template.
        echo.
        echo  ┌─────────────────────────────────────────────────┐
        echo  │  config.json baru dibuat!                      │
        echo  │                                                 │
        echo  │  Kamu bisa edit pengaturan di config.json:     │
        echo  │   - delay  : jeda antar prompt (detik)         │
        echo  │   - retry  : jumlah retry jika error           │
        echo  │   - headless: true = tanpa tampilan browser    │
        echo  └─────────────────────────────────────────────────┘
        echo.
        set /p OPEN_CFG="  Buka config.json sekarang? (y/n): "
        if /i "!OPEN_CFG!"=="y" (
            start notepad config.json
            echo.
            echo  Tutup Notepad setelah selesai edit, lalu...
            pause
        )
    ) else (
        echo      [WARN] config.default.json tidak ditemukan, skip.
    )
) else (
    echo      [OK] config.json sudah ada.
)
echo.

:: ─── STEP 6: CEK PROMPTS.TXT ─────────────────────────────
echo  [6/6] Memeriksa file prompts...
if not exist "prompts.txt" (
    echo      [WARN] prompts.txt tidak ditemukan!
    echo      Membuat file prompts.txt contoh...
    (
        echo A golden sunset over a mountain lake with reflections
        echo A futuristic city at night with flying cars
        echo A close-up of a butterfly landing on a flower in slow motion
    ) > prompts.txt
    echo      [OK] prompts.txt dibuat dengan 3 contoh prompt.
    echo.
    echo  ┌─────────────────────────────────────────────────┐
    echo  │  Edit prompts.txt untuk menambah prompt        │
    echo  │     video kamu (satu prompt per baris)         │
    echo  └─────────────────────────────────────────────────┘
    echo.
    set /p OPEN_PRM="  Buka prompts.txt untuk diedit sekarang? (y/n): "
    if /i "!OPEN_PRM!"=="y" (
        start notepad prompts.txt
        echo.
        echo  Tutup Notepad setelah selesai, lalu...
        pause
    )
) else (
    set LINE_COUNT=0
    for /f "usebackq" %%A in ("prompts.txt") do set /a LINE_COUNT+=1
    echo      [OK] prompts.txt ditemukan (!LINE_COUNT! baris prompt).
)
echo.

:: ─── SIAP JALAN ──────────────────────────────────────────
echo  ────────────────────────────────────────────────────
echo.
echo  [OK] Semua setup selesai! Memulai aplikasi...
echo.
echo  ────────────────────────────────────────────────────
echo.
timeout /t 2 > nul

python gui.py

:: ─── SETELAH APP TUTUP ───────────────────────────────────
if errorlevel 1 (
    color 0C
    echo.
    echo  ╔══════════════════════════════════════════════════╗
    echo  ║  [ERROR] APLIKASI BERHENTI KARENA ERROR         ║
    echo  ╚══════════════════════════════════════════════════╝
    echo.
    echo  Cek folder DEBUG\ untuk screenshot error.
    echo  Atau jalankan diagnosa dengan perintah:
    echo.
    echo     python diagnose.py
    echo.
) else (
    echo.
    echo  ╔══════════════════════════════════════════════════╗
    echo  ║  Aplikasi selesai. Sampai jumpa!               ║
    echo  ╚══════════════════════════════════════════════════╝
    echo.
    echo  Video tersimpan di folder: OUTPUT_GEMINI\
)
echo.
pause
