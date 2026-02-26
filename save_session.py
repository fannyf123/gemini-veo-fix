"""
save_session.py  —  Login manual di Chrome profile ASLI, simpan session

Google mendeteksi Playwright via CDP (DevTools Protocol).
Solusi: Pakai Chrome User Data Dir (profile nyata kamu) sehingga
Google melihat browser yang sama persis seperti kamu buka manual.

Cara pakai:
    python save_session.py

1. Pastikan Google Chrome TERTUTUP dulu sebelum jalankan ini
2. Browser Chrome akan terbuka dengan profile ASLI kamu
3. Login manual ke business.gemini.google
4. Tekan Enter di terminal setelah berhasil masuk
5. Session tersimpan di: session/gemini_session.json
"""

import os
import sys
import json
import time
import shutil
import tempfile

SESSION_DIR  = os.path.join(os.path.dirname(os.path.abspath(__file__)), "session")
SESSION_FILE = os.path.join(SESSION_DIR, "gemini_session.json")

GEMINI_LOGIN_URL = "https://auth.business.gemini.google/login?continueUrl=https://business.gemini.google/"
GEMINI_HOME_URL  = "https://business.gemini.google/"

# Path Chrome + User Data
CHROME_PATHS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    os.path.expanduser(r"~\AppData\Local\Google\Chrome\Application\chrome.exe"),
]

USER_DATA_PATHS = [
    os.path.expanduser(r"~\AppData\Local\Google\Chrome\User Data"),
    os.path.expanduser(r"~\AppData\Local\Google\Chrome Beta\User Data"),
]

def find_chrome():
    for p in CHROME_PATHS:
        if os.path.exists(p):
            return p
    return None

def find_user_data():
    for p in USER_DATA_PATHS:
        if os.path.exists(p):
            return p
    return None

def main():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("[ERR] playwright tidak terinstall!")
        sys.exit(1)

    os.makedirs(SESSION_DIR, exist_ok=True)

    chrome_path  = find_chrome()
    user_data    = find_user_data()

    print()
    print("=" * 60)
    print("  Gemini Session Saver")
    print("=" * 60)

    if not chrome_path:
        print("[ERR] Google Chrome tidak ditemukan!")
        sys.exit(1)

    print(f"[OK]  Chrome   : {chrome_path}")

    if user_data:
        print(f"[OK]  Profile  : {user_data}")
    else:
        print("[WRN] Chrome User Data tidak ditemukan, pakai profile kosong.")

    print()
    print("[!!!] PASTIKAN GOOGLE CHROME SUDAH TERTUTUP SEBELUM LANJUT!")
    print()
    input(">>> Sudah tutup Chrome? Tekan ENTER untuk mulai...")
    print()

    with sync_playwright() as pw:

        launch_kwargs = dict(
            executable_path=chrome_path,
            headless=False,
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-sync",
                "--disable-extensions",
            ],
            ignore_default_args=["--enable-automation"],
        )

        if user_data:
            # Pakai profile asli Chrome kamu
            ctx = pw.chromium.launch_persistent_context(
                user_data_dir=user_data,
                **launch_kwargs,
                viewport={"width": 1280, "height": 900},
                locale="en-US",
                timezone_id="Asia/Jakarta",
            )
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            print("[OK]  Pakai Chrome profile asli kamu")
        else:
            # Fallback: profile kosong
            browser = pw.chromium.launch(**launch_kwargs)
            ctx = browser.new_context(
                viewport={"width": 1280, "height": 900},
                locale="en-US",
                timezone_id="Asia/Jakarta",
            )
            page = ctx.new_page()
            print("[WRN] Pakai profile kosong (Chrome User Data tidak ditemukan)")

        print("[INFO] Membuka halaman Gemini Enterprise...")
        try:
            page.goto(GEMINI_HOME_URL, wait_until="domcontentloaded", timeout=20_000)
        except Exception:
            page.goto(GEMINI_LOGIN_URL, wait_until="domcontentloaded", timeout=30_000)

        print()
        print("[INFO] Silakan login manual di browser yang terbuka.")
        print("[INFO] Setelah masuk ke halaman business.gemini.google,")
        print("       kembali ke sini dan tekan ENTER.")
        print()
        input(">>> Tekan ENTER setelah berhasil login: ")
        print()

        current_url = page.url
        print(f"[INFO] URL saat ini: {current_url}")

        if "business.gemini.google" not in current_url:
            print("[WRN] Sepertinya belum di halaman Gemini.")
            confirm = input(">>> Lanjut simpan session? (y/n): ").strip().lower()
            if confirm != "y":
                print("[INFO] Dibatalkan.")
                ctx.close()
                return

        # Simpan cookies
        try:
            storage = ctx.storage_state()
            with open(SESSION_FILE, "w", encoding="utf-8") as f:
                json.dump(storage, f, indent=2)
            n_cookies = len(storage.get("cookies", []))
            print(f"[OK]  Session tersimpan: {SESSION_FILE}")
            print(f"[OK]  Jumlah cookies   : {n_cookies}")
        except Exception as e:
            print(f"[ERR] Gagal simpan session: {e}")

        print()
        print("[DONE] Sekarang jalankan Launcher.bat untuk generate video.")
        ctx.close()

if __name__ == "__main__":
    main()
    input("\nPress any key to continue . . . ")
