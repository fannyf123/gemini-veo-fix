@echo off
title Gemini Session Saver
chcp 65001 > nul
color 0B

echo.
echo  ============================================
echo    Gemini Session Saver
echo    Login manual sekali, simpan session
echo  ============================================
echo.
echo  Langkah:
echo  1. Browser Chrome akan terbuka
echo  2. Login MANUAL dengan email kamu
echo  3. Setelah masuk ke halaman Gemini, tekan ENTER
echo  4. Session tersimpan otomatis
echo.
pause

python save_session.py

pause
