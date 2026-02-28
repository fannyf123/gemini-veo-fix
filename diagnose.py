"""
diagnose.py — Cek semua requirement sebelum run main.py
Jalankan: python diagnose.py
"""
import os
import sys
import subprocess

PASS = "[OK] "
FAIL = "[ERR]"
WARN = "[WRN]"

CHROME_PATHS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    os.path.expanduser(r"~\AppData\Local\Google\Chrome\Application\chrome.exe"),
    r"C:\Program Files\Google\Chrome Beta\Application\chrome.exe",
]

print()
print("=" * 55)
print("  Gemini Veo Tester — Diagnosa Sistem")
print("=" * 55)
print()

errors = []

# ── 1. Python version ──────────────────────────────────────────────
v = sys.version_info
if v >= (3, 10):
    print(f"{PASS} Python {v.major}.{v.minor}.{v.micro}")
else:
    print(f"{FAIL} Python {v.major}.{v.minor} — butuh 3.10+")
    errors.append("Python < 3.10")

# ── 2. Playwright ──────────────────────────────────────────────────
try:
    import playwright
    try:
        pw_ver = playwright.__version__
    except AttributeError:
        from importlib.metadata import version as pkg_version
        pw_ver = pkg_version("playwright")
    print(f"{PASS} playwright terinstall: {pw_ver}")
except ImportError:
    print(f"{FAIL} playwright TIDAK terinstall")
    print(f"       Jalankan: pip install playwright && playwright install")
    errors.append("playwright missing")

# ── 3. playwright-stealth ──────────────────────────────────────────
try:
    from playwright_stealth import stealth_sync
    print(f"{PASS} playwright-stealth terinstall")
except ImportError:
    print(f"{FAIL} playwright-stealth TIDAK terinstall  ← INI PENYEBAB BOT DETECTED")
    print(f"       Jalankan: pip install playwright-stealth")
    errors.append("playwright-stealth missing")

# ── 4. Google Chrome executable ────────────────────────────────────
chrome_found = None
for path in CHROME_PATHS:
    if os.path.exists(path):
        chrome_found = path
        break

if chrome_found:
    print(f"{PASS} Google Chrome ditemukan:")
    print(f"       {chrome_found}")
else:
    print(f"{FAIL} Google Chrome TIDAK ditemukan di:")
    for p in CHROME_PATHS:
        print(f"       - {p}")
    print(f"       Download: https://google.com/chrome")
    errors.append("Chrome not found")

# ── 5. Chromium Playwright (fallback) ──────────────────────────────
try:
    result = subprocess.run(
        [sys.executable, "-c",
         "from playwright.sync_api import sync_playwright; "
         "p=sync_playwright().start(); "
         "b=p.chromium.launch(headless=True); "
         "print('OK'); b.close(); p.stop()"],
        capture_output=True, text=True, timeout=30
    )
    if "OK" in result.stdout:
        print(f"{PASS} Playwright Chromium bisa launch")
    else:
        print(f"{WARN} Playwright Chromium error: {result.stderr[:100]}")
except Exception as e:
    print(f"{WARN} Tidak bisa test Chromium launch: {e}")

# ── 6. Test Chrome launch (stealth mode) ───────────────────────────
if chrome_found:
    try:
        test_script = f'''
import sys
from playwright.sync_api import sync_playwright
try:
    from playwright_stealth import stealth_sync
    has_stealth = True
except: has_stealth = False
with sync_playwright() as pw:
    browser = pw.chromium.launch(
        executable_path=r"{chrome_found}",
        headless=False,
        args=["--no-sandbox","--disable-blink-features=AutomationControlled"],
        ignore_default_args=["--enable-automation"]
    )
    ctx = browser.new_context()
    page = ctx.new_page()
    if has_stealth: stealth_sync(page)
    page.goto("https://www.google.com", wait_until="domcontentloaded", timeout=15000)
    title = page.title()
    wd = page.evaluate("navigator.webdriver")
    print(f"TITLE={{title}} | webdriver={{wd}}")
    browser.close()
'''
        result = subprocess.run(
            [sys.executable, "-c", test_script],
            capture_output=True, text=True, timeout=30
        )
        if "TITLE=" in result.stdout:
            out = result.stdout.strip()
            print(f"{PASS} Chrome launch test: {out}")
            if "webdriver=None" in out or "webdriver=undefined" in out:
                print(f"{PASS} navigator.webdriver = hidden (stealth OK)")
            else:
                wd_val = out.split('webdriver=')[-1] if 'webdriver=' in out else '?'
                print(f"{WARN} navigator.webdriver = {wd_val} (masih terdeteksi!)")
                errors.append("webdriver still visible")
        else:
            print(f"{WARN} Chrome launch test gagal: {result.stderr[:150]}")
    except Exception as e:
        print(f"{WARN} Chrome test error: {e}")

# ── 7. config.json ─────────────────────────────────────────────────
import json
cfg_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
if os.path.exists(cfg_path):
    try:
        with open(cfg_path) as f:
            cfg = json.load(f)
        mask = cfg.get("mask_email", "")
        headless = cfg.get("headless", None)
        if mask and mask != "ISI_EMAIL_MASK_MOZMAIL_DISINI":
            print(f"{PASS} config.json mask_email: {mask}")
        else:
            print(f"{FAIL} config.json mask_email belum diisi!")
            errors.append("mask_email kosong")
        if headless == False:
            print(f"{PASS} config.json headless: false (correct)")
        else:
            print(f"{WARN} config.json headless: {headless} — sebaiknya false!")
    except Exception as e:
        print(f"{WARN} config.json error: {e}")
else:
    print(f"{FAIL} config.json tidak ditemukan!")
    errors.append("config.json missing")

# ── 8. credentials.json ────────────────────────────────────────────
creds_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "credentials.json")
if os.path.exists(creds_path):
    print(f"{PASS} credentials.json ada")
else:
    print(f"{FAIL} credentials.json TIDAK ditemukan (Gmail API)!")
    errors.append("credentials.json missing")

# ── 9. prompts.txt ─────────────────────────────────────────────────
prompts_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "prompts.txt")
if os.path.exists(prompts_path):
    with open(prompts_path) as f:
        lines = [l.strip() for l in f if l.strip()]
    print(f"{PASS} prompts.txt: {len(lines)} prompt(s)")
else:
    print(f"{FAIL} prompts.txt tidak ditemukan!")
    errors.append("prompts.txt missing")

# ── Ringkasan ──────────────────────────────────────────────────────
print()
print("=" * 55)
if not errors:
    print("  ✅ Semua OK! Siap jalankan: Launcher.bat")
else:
    print(f"  ❌ {len(errors)} masalah ditemukan:")
    for e in errors:
        print(f"     - {e}")
    print()
    print("  Perbaiki masalah di atas lalu jalankan lagi.")
print("=" * 55)
print()
