#!/usr/bin/env bash
set -e

echo ""
echo " ============================================"
echo "   Gemini Veo Tester"
echo "   business.gemini.google automation"
echo " ============================================"
echo ""

echo "[INFO] Menginstall dependencies..."
pip3 install -r requirements.txt --quiet

echo "[INFO] Install Playwright Chromium..."
playwright install chromium

echo "[INFO] Menjalankan tester..."
echo ""
python3 main.py
