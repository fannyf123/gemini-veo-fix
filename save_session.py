"""
save_session.py  —  Login MANUAL ke Gemini Enterprise, simpan cookies/session

Cara pakai:
    python save_session.py

1. Browser Chrome akan terbuka
2. Login MANUAL (ketik email + OTP sendiri)
3. Setelah halaman business.gemini.google terbuka, tekan Enter di terminal
4. Session tersimpan di: session/gemini_session.json
5. Jalankan Launcher.bat seperti biasa

Session berlaku sampai Google logout otomatis (~beberapa hari).
Ulangi save_session.py kalau muncul error login lagi.
"""

import os
import sys
import json
import time

SESSION_DIR  = os.path.join(os.path.dirname(os.path.abspath(__file__)), "session")
SESSION_FILE = os.path.join(SESSION_DIR, "gemini_session.json")

CHROME_PATHS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    os.path.expanduser(r"~\AppData\Local\Google\Chrome\Application\chrome.exe"),
]

GEMINI_LOGIN_URL = "https://auth.business.gemini.google/login?continueUrl=https://business.gemini.google/"

def find_chrome():
    for p in CHROME_PATHS:
        if os.path.exists(p):
            return p
    return None

def main():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("[ERR] playwright tidak terinstall! Jalankan: pip install playwright")
        sys.exit(1)

    os.makedirs(SESSION_DIR, exist_ok=True)
    chrome_path = find_chrome()

    print()
    print("=" * 55)
    print("  Gemini Session Saver")
    print("=" * 55)
    print()
    print("[INFO] Browser akan terbuka.")
    print("[INFO] Silakan LOGIN MANUAL:")
    print("       1. Ketik email kamu")
    print("       2. Masukkan OTP yang dikirim ke email")
    print("       3. Tunggu sampai halaman business.gemini.google terbuka")
    print("       4. Kembali ke terminal ini, tekan ENTER")
    print()

    with sync_playwright() as pw:
        launch_kwargs = dict(
            headless=False,
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-features=IsolateOrigins,site-per-process",
            ],
            ignore_default_args=["--enable-automation"],
        )

        if chrome_path:
            print(f"[INFO] Pakai Chrome: {chrome_path}")
            browser = pw.chromium.launch(executable_path=chrome_path, **launch_kwargs)
        else:
            try:
                browser = pw.chromium.launch(channel="chrome", **launch_kwargs)
                print("[INFO] Pakai Chrome via channel")
            except Exception:
                browser = pw.chromium.launch(**launch_kwargs)
                print("[WRN] Pakai Chromium (Chrome tidak ditemukan)")

        ctx = browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.6261.112 Safari/537.36"
            ),
            locale="en-US",
            timezone_id="Asia/Jakarta",
        )

        page = ctx.new_page()
        page.goto(GEMINI_LOGIN_URL, wait_until="domcontentloaded", timeout=30_000)

        print("[INFO] Browser terbuka. Silakan login manual...")
        print()
        input(">>> Setelah berhasil masuk ke business.gemini.google, tekan ENTER di sini: ")
        print()

        # Verifikasi URL
        current_url = page.url
        if "business.gemini.google" not in current_url:
            print(f"[WRN] URL saat ini: {current_url}")
            print("[WRN] Sepertinya belum sampai halaman utama Gemini.")
            confirm = input(">>> Lanjut simpan session ini? (y/n): ").strip().lower()
            if confirm != "y":
                print("[INFO] Dibatalkan.")
                browser.close()
                return

        # Simpan storage state (cookies + localStorage)
        storage = ctx.storage_state()
        with open(SESSION_FILE, "w", encoding="utf-8") as f:
            json.dump(storage, f, indent=2)

        print(f"[OK]  Session tersimpan: {SESSION_FILE}")
        print(f"[OK]  Jumlah cookies   : {len(storage.get('cookies', []))}")
        print()
        print("[INFO] Sekarang jalankan Launcher.bat untuk generate video.")
        print("[INFO] Session akan dipakai otomatis, tidak perlu login lagi.")
        print()

        browser.close()

if __name__ == "__main__":
    main()
    input("Press any key to continue . . . ")
