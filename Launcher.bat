@echo off
setlocal EnableDelayedExpansion
title Gemini Veo Auto Generator
color 0A

cls
echo.
echo  ==============================================================
echo   GEMINI VEO AUTO GENERATOR  -  ReenzAuto
echo  ==============================================================
echo   Launcher akan otomatis setup semua kebutuhan.
echo   Mohon tunggu dan JANGAN tutup window ini.
echo  ==============================================================
echo.

:: ---------------------------------------------------------------
:: STEP 1 : CEK PYTHON
:: ---------------------------------------------------------------
echo  [1/6] Memeriksa instalasi Python...
python --version >nul 2>&1
if errorlevel 1 (
    color 0C
    echo.
    echo  ==============================================================
    echo  [!] PYTHON TIDAK DITEMUKAN
    echo  ==============================================================
    echo.
    echo  Python belum terinstall atau belum ditambahkan ke PATH.
    echo.
    echo  Cara Install Python (mudah):
    echo    1. Buka: https://www.python.org/downloads/
    echo    2. Klik Download Python (versi terbaru)
    echo    3. Jalankan installer
    echo    4. WAJIB: centang "Add Python to PATH" sebelum install
    echo    5. Setelah selesai, jalankan Launcher.bat ini lagi
    echo.
    echo  Tekan sembarang tombol untuk membuka halaman download...
    pause >nul
    start https://www.python.org/downloads/
    exit /b 1
)
for /f "tokens=2" %%V in ('python --version 2^>^&1') do set PY_VER=%%V
echo   [OK] Python !PY_VER! ditemukan.
echo.

:: ---------------------------------------------------------------
:: STEP 2 : BUAT VIRTUAL ENVIRONMENT (jika belum ada)
:: ---------------------------------------------------------------
echo  [2/6] Memeriksa Virtual Environment...
if not exist ".venv\Scripts\activate.bat" (
    echo   Membuat Virtual Environment (.venv)...
    python -m venv .venv
    if errorlevel 1 (
        color 0C
        echo.
        echo  [!] Gagal membuat Virtual Environment!
        echo  Pastikan Python terinstall dengan benar.
        echo.
        pause
        exit /b 1
    )
    echo   [OK] Virtual Environment berhasil dibuat.
) else (
    echo   [OK] Virtual Environment sudah ada.
)
echo.

:: ---------------------------------------------------------------
:: STEP 3 : AKTIFKAN VENV
:: ---------------------------------------------------------------
echo  [3/6] Mengaktifkan Virtual Environment...
call .venv\Scripts\activate.bat
echo   [OK] Virtual Environment aktif.
echo.

:: ---------------------------------------------------------------
:: STEP 4 : INSTALL DEPENDENCIES
:: ---------------------------------------------------------------
echo  [4/6] Menginstall dependencies...
echo   (selenium, PySide6, selenium-stealth, dll - mungkin butuh
 echo    beberapa menit saat pertama kali)
echo.
pip install -r requirements.txt --quiet --disable-pip-version-check
if errorlevel 1 (
    color 0C
    echo.
    echo  [!] Gagal install dependencies!
    echo.
    echo  Kemungkinan penyebab:
    echo    - Tidak ada koneksi internet
    echo    - requirements.txt tidak ditemukan
    echo.
    echo  Coba jalankan manual:
    echo    pip install -r requirements.txt
    echo.
    pause
    exit /b 1
)
echo   [OK] Semua dependencies terinstall.
echo.

:: ---------------------------------------------------------------
:: STEP 5 : CEK CONFIG.JSON
:: ---------------------------------------------------------------
echo  [5/6] Memeriksa konfigurasi...
if not exist "config.json" (
    if exist "config.default.json" (
        copy "config.default.json" "config.json" >nul
        echo   [INFO] config.json dibuat otomatis dari template.
        echo.
        echo  --------------------------------------------------------------
        echo   config.json berhasil dibuat!
        echo.
        echo   Kamu bisa mengubah pengaturan di config.json:
        echo     - delay   : jeda antar video (dalam detik)
        echo     - retry   : berapa kali coba ulang jika gagal
        echo     - headless: true = browser tidak tampil (background)
        echo  --------------------------------------------------------------
        echo.
        set /p OPEN_CFG=  Buka config.json untuk diedit sekarang? (y/n): 
        if /i "!OPEN_CFG!"=="y" (
            start notepad config.json
            echo.
            echo   Tutup Notepad setelah selesai, lalu...
            pause
        )
    ) else (
        echo   [WARN] config.default.json tidak ditemukan, skip.
    )
) else (
    echo   [OK] config.json sudah ada.
)
echo.

:: ---------------------------------------------------------------
:: STEP 6 : CEK PROMPTS.TXT
:: ---------------------------------------------------------------
echo  [6/6] Memeriksa file prompts...
if not exist "prompts.txt" (
    echo   [INFO] prompts.txt tidak ada. Membuat contoh...
    (
        echo A golden sunset over a mountain lake with reflections in 4K
        echo A futuristic city at night with flying cars and neon lights
        echo A close-up of a butterfly landing on a flower in slow motion
    ) > prompts.txt
    echo   [OK] prompts.txt dibuat dengan 3 contoh prompt.
    echo.
    echo  --------------------------------------------------------------
    echo   Edit prompts.txt untuk menambahkan prompt video kamu.
    echo   Satu prompt = satu baris. Simpan lalu jalankan lagi.
    echo  --------------------------------------------------------------
    echo.
    set /p OPEN_PRM=  Buka prompts.txt untuk diedit sekarang? (y/n): 
    if /i "!OPEN_PRM!"=="y" (
        start notepad prompts.txt
        echo.
        echo   Tutup Notepad setelah selesai, lalu...
        pause
    )
) else (
    set LINE_COUNT=0
    for /f "usebackq" %%A in ("prompts.txt") do set /a LINE_COUNT+=1
    echo   [OK] prompts.txt ditemukan - !LINE_COUNT! prompt siap diproses.
)
echo.

:: ---------------------------------------------------------------
:: JALANKAN APLIKASI
:: ---------------------------------------------------------------
echo  ==============================================================
echo   Setup selesai! Menjalankan aplikasi...
echo  ==============================================================
echo.
timeout /t 2 >nul

python gui.py

:: ---------------------------------------------------------------
:: SETELAH APLIKASI TUTUP
:: ---------------------------------------------------------------
if errorlevel 1 (
    color 0C
    echo.
    echo  ==============================================================
    echo  [!] APLIKASI BERHENTI KARENA ERROR
    echo  ==============================================================
    echo.
    echo  Yang bisa kamu lakukan:
    echo    1. Cek folder DEBUG\ untuk screenshot error
    echo    2. Jalankan diagnosa:
    echo         python diagnose.py
    echo    3. Hubungi support dengan menyertakan isi folder DEBUG\
    echo.
) else (
    echo.
    echo  ==============================================================
    echo   Selesai! Terima kasih sudah menggunakan Gemini Veo Generator
    echo  ==============================================================
    echo.
    echo   Video tersimpan di folder: OUTPUT_GEMINI\
    echo.
)
pause
