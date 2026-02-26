@echo off
title Gemini Session Saver
chcp 65001 > nul
color 0B

echo.
echo  ============================================
echo    Gemini Session Saver
echo  ============================================
echo.
echo  PENTING: Tutup Google Chrome sebelum lanjut!
echo.
echo  Langkah:
echo  1. Tutup semua jendela Google Chrome
echo  2. Tekan ENTER di terminal
echo  3. Login manual di browser yang terbuka
echo  4. Tekan ENTER lagi setelah berhasil masuk
echo  5. Session tersimpan otomatis
echo.
pause

python save_session.py

pause
