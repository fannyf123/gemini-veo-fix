@echo off
setlocal EnableDelayedExpansion
title Gemini Veo Auto Generator
color 0A

rem ================================================================
rem  Semua logic dijalankan lewat :MAIN sehingga window TIDAK
rem  force close - pause selalu tampil di akhir apapun yang terjadi
rem ================================================================
call :MAIN
echo.
pause
exit /b

rem ================================================================
:MAIN
rem ================================================================

cls
echo.
echo  ==============================================================
echo   GEMINI VEO AUTO GENERATOR  ^|  ReenzAuto
echo  ==============================================================
echo   Setup otomatis akan memeriksa dan menginstall semua
echo   kebutuhan. Mohon tunggu - JANGAN tutup window ini.
echo  ==============================================================
echo.


rem ---------------------------------------------------------------
rem  STEP 1 : CEK PYTHON
rem ---------------------------------------------------------------
echo  [1/7] Memeriksa instalasi Python...
python --version >nul 2>&1
if errorlevel 1 (
    color 0C
    echo.
    echo  ==============================================================
    echo  [ERROR] PYTHON TIDAK DITEMUKAN!
    echo  ==============================================================
    echo.
    echo  Cara Install Python ^(MUDAH^):
    echo    1. Browser akan terbuka ke halaman download Python
    echo    2. Klik tombol kuning Download Python
    echo    3. Jalankan installer yang terdownload
    echo    4. WAJIB: centang kotak "Add Python to PATH"
    echo    5. Klik Install Now
    echo    6. Setelah selesai, jalankan Launcher.bat ini lagi
    echo.
    echo  Membuka halaman download Python...
    timeout /t 3 >nul
    start https://www.python.org/downloads/
    exit /b 1
)
for /f "tokens=2" %%V in ('python --version 2^>^&1') do set PY_VER=%%V
echo   [OK] Python !PY_VER! ditemukan.
echo.


rem ---------------------------------------------------------------
rem  STEP 2 : CEK / BUAT VIRTUAL ENVIRONMENT
rem ---------------------------------------------------------------
echo  [2/7] Memeriksa Virtual Environment...
if not exist ".venv\Scripts\activate.bat" (
    echo   Virtual Environment belum ada. Membuat baru...
    python -m venv .venv
    if errorlevel 1 (
        color 0C
        echo.
        echo  [ERROR] Gagal membuat Virtual Environment!
        echo  Coba install ulang Python dari https://www.python.org/downloads/
        echo.
        exit /b 1
    )
    echo   [OK] Virtual Environment berhasil dibuat.
) else (
    echo   [OK] Virtual Environment sudah ada.
)
echo.


rem ---------------------------------------------------------------
rem  STEP 3 : AKTIFKAN VENV
rem ---------------------------------------------------------------
echo  [3/7] Mengaktifkan Virtual Environment...
call .venv\Scripts\activate.bat
if errorlevel 1 (
    color 0C
    echo.
    echo  [ERROR] Gagal mengaktifkan Virtual Environment!
    echo  Hapus folder .venv lalu coba jalankan lagi.
    echo.
    exit /b 1
)
echo   [OK] Virtual Environment aktif.
echo.


rem ---------------------------------------------------------------
rem  STEP 4 : UPGRADE PIP
rem ---------------------------------------------------------------
echo  [4/7] Memperbarui pip...
python -m pip install --upgrade pip --quiet --disable-pip-version-check
echo   [OK] pip siap.
echo.


rem ---------------------------------------------------------------
rem  STEP 5 : INSTALL SEMUA DEPENDENCIES SATU PER SATU
rem ---------------------------------------------------------------
echo  [5/7] Menginstall semua library yang dibutuhkan...
echo   selenium, PySide6, selenium-stealth, beautifulsoup4, dll
echo   Proses ini bisa 2-5 menit saat pertama kali. Mohon tunggu...
echo.

pip install "selenium>=4.0.0" --quiet --disable-pip-version-check
if errorlevel 1 (
    color 0C
    echo   [ERROR] Gagal install: selenium
    goto :dep_error
)
echo   [OK] selenium

pip install selenium-stealth --quiet --disable-pip-version-check
if errorlevel 1 (
    color 0C
    echo   [ERROR] Gagal install: selenium-stealth
    goto :dep_error
)
echo   [OK] selenium-stealth

pip install beautifulsoup4 --quiet --disable-pip-version-check
if errorlevel 1 (
    color 0C
    echo   [ERROR] Gagal install: beautifulsoup4
    goto :dep_error
)
echo   [OK] beautifulsoup4

pip install lxml --quiet --disable-pip-version-check
if errorlevel 1 (
    color 0C
    echo   [ERROR] Gagal install: lxml
    goto :dep_error
)
echo   [OK] lxml

pip install requests --quiet --disable-pip-version-check
if errorlevel 1 (
    color 0C
    echo   [ERROR] Gagal install: requests
    goto :dep_error
)
echo   [OK] requests

pip install PySide6 --quiet --disable-pip-version-check
if errorlevel 1 (
    color 0C
    echo   [ERROR] Gagal install: PySide6
    goto :dep_error
)
echo   [OK] PySide6

pip install qtawesome --quiet --disable-pip-version-check
if errorlevel 1 (
    color 0C
    echo   [ERROR] Gagal install: qtawesome
    goto :dep_error
)
echo   [OK] qtawesome

pip install pyperclip --quiet --disable-pip-version-check
if errorlevel 1 (
    color 0C
    echo   [ERROR] Gagal install: pyperclip
    goto :dep_error
)
echo   [OK] pyperclip

echo.
echo   [OK] Semua dependencies berhasil terinstall!
echo.
goto :step6

:dep_error
echo.
echo  ==============================================================
echo  [ERROR] Gagal menginstall salah satu library!
echo  ==============================================================
echo.
echo  Kemungkinan penyebab:
echo    - Tidak ada koneksi internet
echo    - Antivirus memblokir pip
echo    - Firewall kantor/kampus
echo.
echo  Solusi:
echo    1. Pastikan terhubung ke internet
echo    2. Matikan antivirus sementara lalu coba lagi
echo    3. Coba klik kanan Launcher.bat - Run as Administrator
echo.
exit /b 1


rem ---------------------------------------------------------------
:step6
rem  STEP 6 : CEK CONFIG.JSON
rem ---------------------------------------------------------------
echo  [6/7] Memeriksa file konfigurasi...
if not exist "config.json" (
    if exist "config.default.json" (
        copy "config.default.json" "config.json" >nul
        echo   [OK] config.json dibuat dari template.
    ) else (
        echo   Membuat config.json...
        echo {> config.json
        echo   "delay": 5,>> config.json
        echo   "retry": 2,>> config.json
        echo   "headless": false,>> config.json
        echo   "max_workers": 1,>> config.json
        echo   "stealth": true>> config.json
        echo }>> config.json
        echo   [OK] config.json dibuat.
    )
    echo.
    echo  --------------------------------------------------------------
    echo   Keterangan config.json:
    echo     delay       = jeda antar video ^(detik^)
    echo     retry       = berapa kali coba ulang jika gagal
    echo     headless    = false=browser terlihat, true=background
    echo     max_workers = jumlah akun paralel ^(1 = disarankan^)
    echo  --------------------------------------------------------------
    echo.
    set /p OPEN_CFG=  Buka config.json sekarang? ^(y/n^): 
    if /i "!OPEN_CFG!"=="y" (
        start notepad config.json
        echo   Tutup Notepad setelah selesai lalu tekan tombol apapun...
        pause >nul
    )
) else (
    echo   [OK] config.json sudah ada.
)
echo.


rem ---------------------------------------------------------------
rem  JALANKAN APLIKASI GUI
rem ---------------------------------------------------------------
echo  ==============================================================
echo   Semua setup selesai! Memulai aplikasi GUI...
echo  ==============================================================
echo.
timeout /t 2 >nul

python gui.py
set APP_EXIT=!errorlevel!


rem ---------------------------------------------------------------
rem  PESAN SETELAH APLIKASI TUTUP
rem ---------------------------------------------------------------
if !APP_EXIT! NEQ 0 (
    color 0C
    echo.
    echo  ==============================================================
    echo  [ERROR] Aplikasi berhenti dengan error ^(kode: !APP_EXIT!^)
    echo  ==============================================================
    echo.
    echo  Langkah troubleshoot:
    echo    1. Cek folder DEBUG\ untuk screenshot error
    echo    2. Pastikan Google Chrome terinstall
    echo       Download: https://www.google.com/chrome/
    echo    3. Jalankan diagnosa: klik kanan folder ini - Open in Terminal
    echo       lalu ketik:  python diagnose.py
    echo.
) else (
    color 0A
    echo.
    echo  ==============================================================
    echo   Selesai! Video tersimpan di folder: OUTPUT_GEMINI\
    echo  ==============================================================
    echo.
)

exit /b !APP_EXIT!
