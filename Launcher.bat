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
pip install -r requirements.txt --quiet

echo [INFO] Install Playwright Chromium...
playwright install chromium

echo [INFO] Menjalankan tester...
echo.
python main.py

if errorlevel 1 (
    echo.
    echo [ERROR] Ada error saat berjalan.
    pause
)
pause
