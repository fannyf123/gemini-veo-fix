"""
save_session.py  —  Login manual ke Gemini Enterprise, simpan session

Cara pakai:
    python save_session.py  (atau klik Save_Session.bat)

1. Browser Chrome akan terbuka
2. Login MANUAL (ketik email + OTP sendiri)
3. Setelah halaman business.gemini.google terbuka, tekan Enter di terminal
4. Session tersimpan di: session/gemini_session.json
"""

import os
import sys
import json

SESSION_DIR  = os.path.join(os.path.dirname(os.path.abspath(__file__)), "session")
SESSION_FILE = os.path.join(SESSION_DIR, "gemini_session.json")

GEMINI_HOME_URL = "https://business.gemini.google/"

CHROME_PATHS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    os.path.expanduser(r"~\AppData\Local\Google\Chrome\Application\chrome.exe"),
]

def find_chrome():
    for p in CHROME_PATHS:
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
    chrome_path = find_chrome()

    print()
    print("=" * 55)
    print("  Gemini Session Saver")
    print("=" * 55)
    print()
    print("[INFO] Browser akan terbuka.")
    print("[INFO] Buka: https://business.gemini.google/")
    print("[INFO] Login MANUAL seperti biasa.")
    print("[INFO] Setelah berhasil masuk, kembali ke sini dan tekan ENTER.")
    print()

    with sync_playwright() as pw:
        launch_kwargs = dict(
            headless=False,
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--no-first-run",
                "--no-default-browser-check",
            ],
            ignore_default_args=["--enable-automation"],
        )

        if chrome_path:
            print(f"[INFO] Pakai Chrome: {chrome_path}")
            browser = pw.chromium.launch(executable_path=chrome_path, **launch_kwargs)
        else:
            try:
                browser = pw.chromium.launch(channel="chrome", **launch_kwargs)
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
        # Buka URL yang benar: biarkan redirect otomatis ke login
        page.goto(GEMINI_HOME_URL, wait_until="domcontentloaded", timeout=30_000)

        print("[INFO] Browser terbuka. Login manual...")
        print()
        input(">>> Setelah berhasil masuk ke business.gemini.google, tekan ENTER: ")
        print()

        current_url = page.url
        print(f"[INFO] URL: {current_url}")

        if "business.gemini.google" not in current_url:
            print("[WRN] Belum di halaman Gemini.")
            confirm = input(">>> Lanjut simpan session? (y/n): ").strip().lower()
            if confirm != "y":
                browser.close()
                return

        storage = ctx.storage_state()
        with open(SESSION_FILE, "w", encoding="utf-8") as f:
            json.dump(storage, f, indent=2)

        n = len(storage.get("cookies", []))
        print(f"[OK]  Session tersimpan: {SESSION_FILE}")
        print(f"[OK]  Cookies          : {n}")
        print()
        print("[DONE] Jalankan Launcher.bat untuk generate video.")
        browser.close()

if __name__ == "__main__":
    main()
    input("\nPress any key to continue . . . ")
