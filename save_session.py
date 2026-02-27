"""
save_session.py  —  Login manual ke Gemini Enterprise, simpan session (format Selenium/UC)

Cara pakai:
    python save_session.py  (atau klik Save_Session.bat)

1. Browser Chrome (undetected) akan terbuka
2. Login MANUAL (ketik email + OTP sendiri)
3. Setelah halaman business.gemini.google terbuka, tekan Enter di terminal
4. Session (cookies) tersimpan di: session/gemini_session.json
"""

import os
import sys
import json
import time
import tempfile
import shutil

SESSION_DIR  = os.path.join(os.path.dirname(os.path.abspath(__file__)), "session")
SESSION_FILE = os.path.join(SESSION_DIR, "gemini_session.json")
GEMINI_HOME  = "https://business.gemini.google/"


def main():
    try:
        import undetected_chromedriver as uc
    except ImportError:
        print("[ERR] undetected-chromedriver tidak terinstall!")
        print("      Jalankan: pip install undetected-chromedriver selenium")
        sys.exit(1)

    os.makedirs(SESSION_DIR, exist_ok=True)

    print()
    print("=" * 55)
    print("  Gemini Session Saver (undetected-chromedriver)")
    print("=" * 55)
    print()
    print("[INFO] Browser Chrome akan terbuka dengan fresh profile.")
    print("[INFO] Login MANUAL seperti biasa di browser.")
    print("[INFO] Setelah masuk ke business.gemini.google,")
    print("       kembali ke sini dan tekan ENTER.")
    print()

    # Fresh temp profile
    temp_profile = tempfile.mkdtemp(prefix="gemini_save_session_")
    print(f"[INFO] Temp profile: {temp_profile}")
    print()

    options = uc.ChromeOptions()
    options.add_argument(f"--user-data-dir={temp_profile}")
    options.add_argument("--no-first-run")
    options.add_argument("--no-default-browser-check")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--disable-infobars")
    options.add_argument("--lang=en-US")
    options.add_argument("--window-size=1280,900")

    driver = None
    try:
        driver = uc.Chrome(options=options, use_subprocess=True)
        driver.execute_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )

        print("[INFO] Membuka https://business.gemini.google/ ...")
        driver.get(GEMINI_HOME)
        time.sleep(3)

        print("[INFO] Browser terbuka. Silakan login manual.")
        print()
        input(">>> Setelah berhasil masuk ke business.gemini.google, tekan ENTER: ")
        print()

        current = driver.current_url
        print(f"[INFO] URL saat ini: {current}")

        if "business.gemini.google" not in current:
            print("[WRN] Sepertinya belum di halaman Gemini.")
            confirm = input(">>> Lanjut simpan session? (y/n): ").strip().lower()
            if confirm != "y":
                print("[INFO] Dibatalkan.")
                return

        # Ambil semua cookies dari driver
        cookies = driver.get_cookies()
        with open(SESSION_FILE, "w", encoding="utf-8") as f:
            json.dump(cookies, f, indent=2)

        google_ck = [c for c in cookies if ".google.com" in c.get("domain", "")]
        print(f"[OK]  Session tersimpan : {SESSION_FILE}")
        print(f"[OK]  Total cookies     : {len(cookies)}")
        print(f"[OK]  Google cookies    : {len(google_ck)}")
        print()
        print("[DONE] Jalankan Launcher.bat untuk generate video.")

    except Exception as e:
        print(f"[ERR] {e}")
        import traceback
        traceback.print_exc()
    finally:
        try:
            if driver:
                driver.quit()
        except Exception:
            pass
        # Bersihkan temp profile
        try:
            shutil.rmtree(temp_profile, ignore_errors=True)
        except Exception:
            pass


if __name__ == "__main__":
    main()
    input("\nPress any key to continue . . . ")
