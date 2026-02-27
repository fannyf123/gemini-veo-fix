"""
save_session.py  —  Login manual ke Gemini Enterprise, simpan session

Cara pakai:
    python save_session.py  (atau klik Save_Session.bat)
"""

import os
import sys
import re
import json
import time
import shutil
import tempfile
import subprocess

SESSION_DIR  = os.path.join(os.path.dirname(os.path.abspath(__file__)), "session")
SESSION_FILE = os.path.join(SESSION_DIR, "gemini_session.json")
GEMINI_HOME  = "https://business.gemini.google/"

CHROME_PATHS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    os.path.expanduser(r"~\AppData\Local\Google\Chrome\Application\chrome.exe"),
]


def get_chrome_version():
    try:
        import winreg
        for key_path in [
            r"SOFTWARE\Google\Chrome\BLBeacon",
            r"SOFTWARE\Wow6432Node\Google\Chrome\BLBeacon",
        ]:
            for hive in [winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE]:
                try:
                    key = winreg.OpenKey(hive, key_path)
                    ver, _ = winreg.QueryValueEx(key, "version")
                    return int(ver.split(".")[0])
                except Exception:
                    pass
    except ImportError:
        pass

    for path in CHROME_PATHS:
        if os.path.exists(path):
            try:
                result = subprocess.run([path, "--version"],
                    capture_output=True, text=True, timeout=5)
                m = re.search(r"(\d+)\.\d+\.\d+\.\d+", result.stdout)
                if m:
                    return int(m.group(1))
            except Exception:
                pass
    return None


def main():
    try:
        import undetected_chromedriver as uc
    except ImportError:
        print("[ERR] undetected-chromedriver tidak terinstall!")
        print("      pip install undetected-chromedriver selenium")
        sys.exit(1)

    os.makedirs(SESSION_DIR, exist_ok=True)

    chrome_ver = get_chrome_version()

    print()
    print("=" * 55)
    print("  Gemini Session Saver")
    print("=" * 55)
    if chrome_ver:
        print(f"[INFO] Chrome versi terdeteksi: {chrome_ver}")
    else:
        print("[WRN] Versi Chrome tidak terdeteksi (akan auto-detect)")
    print()
    print("[INFO] Browser akan terbuka. Login MANUAL seperti biasa.")
    print("[INFO] Setelah masuk ke business.gemini.google,")
    print("       kembali ke sini dan tekan ENTER.")
    print()

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
        # Coba dengan versi yang terdeteksi, fallback auto
        versions_to_try = ([chrome_ver, None] if chrome_ver else [None])
        for ver in versions_to_try:
            try:
                ver_label = str(ver) if ver else "auto"
                print(f"[INFO] Mencoba UC version_main={ver_label}...")
                driver = uc.Chrome(options=options, use_subprocess=True, version_main=ver)
                print(f"[OK]  UC driver berhasil (version_main={ver_label})")
                break
            except Exception as e:
                err = str(e)
                print(f"[WRN] version_main={ver_label} gagal: {err[:100]}")
                # Coba parse versi dari error message
                m = re.search(r"Current browser version is (\d+)", err)
                if m:
                    detected = int(m.group(1))
                    print(f"[INFO] Retry dengan version_main={detected} dari error msg...")
                    try:
                        driver = uc.Chrome(options=options, use_subprocess=True, version_main=detected)
                        print(f"[OK]  UC driver berhasil (version_main={detected})")
                        break
                    except Exception as e2:
                        print(f"[ERR] Juga gagal: {str(e2)[:80]}")
                driver = None

        if driver is None:
            print("[ERR] Gagal membuat UC driver!")
            return

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
        print(f"[INFO] URL: {current}")

        if "business.gemini.google" not in current:
            confirm = input(">>> Belum di halaman Gemini. Tetap simpan? (y/n): ").strip().lower()
            if confirm != "y":
                print("[INFO] Dibatalkan.")
                return

        cookies = driver.get_cookies()
        with open(SESSION_FILE, "w", encoding="utf-8") as f:
            json.dump(cookies, f, indent=2)

        google_ck = [c for c in cookies if ".google.com" in c.get("domain", "")]
        print(f"[OK]  Session tersimpan : {SESSION_FILE}")
        print(f"[OK]  Total cookies     : {len(cookies)}")
        print(f"[OK]  Google cookies    : {len(google_ck)}")
        print()
        print("[DONE] Sekarang jalankan Launcher.bat")

    except Exception as e:
        print(f"[ERR] {e}")
        import traceback
        traceback.print_exc()
    finally:
        try:
            if driver: driver.quit()
        except Exception:
            pass
        shutil.rmtree(temp_profile, ignore_errors=True)


if __name__ == "__main__":
    main()
    input("\nPress any key to continue . . . ")
