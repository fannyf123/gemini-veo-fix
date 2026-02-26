@echo off
title Gemini Veo Tester
chcp 65001 > nul
color 0A

echo.
echo  ============================================
echo    Gemini Veo Tester
echo    business.gemini.google automation
echo  ============================================
echo.

echo [INFO] Menginstall dependencies...
pip install -r requirements.txt
if errorlevel 1 (
    echo [ERROR] pip install requirements.txt gagal!
    pause
    exit /b 1
)

echo.
echo [INFO] Menginstall playwright-stealth (anti-bot)...
pip install playwright-stealth
if errorlevel 1 (
    echo [ERROR] pip install playwright-stealth gagal!
    pause
    exit /b 1
)

echo.
echo [INFO] Install Playwright Chromium...
playwright install chromium

echo.
echo [INFO] Verifikasi stealth terinstall...
python -c "from playwright_stealth import stealth_sync; print('[OK]  playwright-stealth OK')" 2>nul
if errorlevel 1 (
    echo [ERR] playwright-stealth gagal diimport!
    echo       Coba manual: pip install playwright-stealth --force-reinstall
    pause
    exit /b 1
)

echo.
echo [INFO] Menjalankan tester...
echo.
python main.py

if errorlevel 1 (
    echo.
    echo [ERROR] Ada error saat berjalan.
    pause
)
pause
