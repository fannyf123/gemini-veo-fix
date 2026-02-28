@echo off
title Gemini Veo Tester
chcp 65001 > nul
color 0A

echo.
echo  ============================================
echo    Gemini Veo Tester (GUI Mode)
echo    business.gemini.google automation
echo  ============================================
echo.

if exist .venv\Scripts\activate.bat (
    echo [INFO] Mengaktifkan Virtual Environment...
    call .venv\Scripts\activate.bat
)

echo [INFO] Menginstall dependencies...
pip install -r requirements.txt
if errorlevel 1 (
    echo [ERROR] pip install gagal!
    echo         Pastikan Python dan pip sudah terinstall.
    pause
    exit /b 1
)

echo.
echo [INFO] Menjalankan tester...
echo.
python gui.py

if errorlevel 1 (
    echo.
    echo [ERROR] Ada error saat berjalan.
    pause
)
pause
