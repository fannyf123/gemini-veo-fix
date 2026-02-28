"""
gemini_enterprise.py

Otomasi generate video di business.gemini.google
Menggunakan selenium-stealth (regular Chrome) + fresh temp profile.

Alur lengkap:
  Step 1 : Buka mailticking.com → dapat email temp baru
  Step 2 : Register di Gemini Business dengan email temp
  Step 3 : Tunggu email verifikasi di mailticking
  Step 4 : Ekstrak kode verifikasi dari email
  Step 5 : Masukkan kode verifikasi
  Step 6 : Selesaikan signup (isi nama, klik Agree)
  Step 7 : Initial setup (tutup dialog, pilih Veo)
  Lanjut : Process prompts satu per satu
  Rate limit: auto switch account
"""
import os
import re
import sys
import json
import time
import random
import shutil
import string
import tempfile
import threading
import subprocess
from typing import Optional, Callable

try:
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.common.exceptions import TimeoutException, WebDriverException
    from selenium.webdriver.common.action_chains import ActionChains
    from selenium.webdriver.common.keys import Keys
except ImportError:
    pass

try:
    from selenium_stealth import stealth
except ImportError:
    stealth = None

from App.mailticking import MailtickingClient

GEMINI_HOME_URL  = "https://business.gemini.google/"
GEMINI_LOGIN_URL = "https://gemini.google.com/corp/signin"

OTP_TIMEOUT      = 90
VIDEO_GEN_TIMEOUT = 600
POLLING_INTERVAL  = 8
MAX_ACCOUNT_RETRY = 3
MAX_TAB_RETRY     = 3

# Thinking disappears < 5s → rate limit
RATE_LIMIT_THINKING_THRESHOLD = 5.0

CHROME_PATHS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    os.path.expanduser(r"~\AppData\Local\Google\Chrome\Application\chrome.exe"),
    "/usr/bin/google-chrome",
    "/usr/bin/chromium-browser",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
]

# Nama acak untuk signup
FIRST_NAMES = [
    "Tyler", "Jordan", "Casey", "Morgan", "Avery", "Riley", "Quinn",
    "Parker", "Hayden", "Blake", "Drew", "Reese", "Sage", "Cameron",
    "Alex", "Rowan", "Jamie", "Skyler", "Logan", "Peyton",
]
LAST_NAMES = [
    "Miller", "Clark", "Davis", "Wilson", "Moore", "Taylor", "Anderson",
    "Thomas", "Jackson", "White", "Harris", "Martin", "Thompson", "Garcia",
    "Martinez", "Robinson", "Lewis", "Lee", "Walker", "Hall",
]

# OTP error keywords di halaman Google
OTP_ERROR_KEYWORDS = [
    "wrong code", "incorrect code", "invalid code",
    "code expired", "didn't match", "try again",
    "that code didn't work", "please check",
]


def _random_name() -> str:
    return f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"


def _get_chrome_version() -> Optional[int]:
    try:
        import winreg
        for kp in [r"SOFTWARE\Google\Chrome\BLBeacon",
                   r"SOFTWARE\Wow6432Node\Google\Chrome\BLBeacon"]:
            for hive in [winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE]:
                try:
                    k = winreg.OpenKey(hive, kp)
                    v, _ = winreg.QueryValueEx(k, "version")
                    return int(v.split(".")[0])
                except Exception:
                    pass
    except ImportError:
        pass
    for path in CHROME_PATHS:
        if os.path.exists(path):
            try:
                r = subprocess.run([path, "--version"],
                    capture_output=True, text=True, timeout=5)
                m = re.search(r"(\d+)\.\d+\.\d+\.\d+", r.stdout)
                if m:
                    return int(m.group(1))
            except Exception:
                pass
    return None


def _get_chrome_full_version() -> Optional[str]:
    for path in CHROME_PATHS:
        if os.path.exists(path):
            try:
                r = subprocess.run([path, "--version"],
                    capture_output=True, text=True, timeout=5)
                m = re.search(r"([\d.]+)", r.stdout)
                if m:
                    return m.group(1)
            except Exception:
                pass
    return None


def _setup_chromedriver(base_dir: str, log_fn: Callable) -> Optional[str]:
    """
    Cek / download ChromeDriver yang cocok dengan versi Chrome terinstal.
    Return path ke chromedriver executable.
    """
    log_fn("Checking ChromeDriver compatibility...")
    chrome_major = _get_chrome_version()
    chrome_full  = _get_chrome_full_version()

    if chrome_major:
        log_fn(f"Detected Chrome version: {chrome_major}")
    else:
        log_fn("Could not detect Chrome version", "WARNING")

    # Cek lokal dulu
    local_paths = [
        os.path.join(base_dir, "chromedriver.exe"),
        os.path.join(base_dir, "chromedriver"),
        "chromedriver.exe",
        "chromedriver",
    ]
    for path in local_paths:
        if os.path.exists(path):
            # Cek versinya
            try:
                r = subprocess.run([path, "--version"],
                    capture_output=True, text=True, timeout=5)
                m = re.search(r"(\d+)\.\d+\.\d+", r.stdout)
                if m and chrome_major and int(m.group(1)) == chrome_major:
                    log_fn(f"Local ChromeDriver version: {m.group(1)}")
                    log_fn("ChromeDriver version matches browser.")
                    return path
                elif m:
                    log_fn(f"Local ChromeDriver v{m.group(1)} != Chrome v{chrome_major}, updating...")
            except Exception:
                pass

    log_fn("No ChromeDriver found locally.")
    log_fn("Downloading ChromeDriver matching browser version...")

    if not chrome_full or not chrome_major:
        log_fn("Cannot auto-download ChromeDriver: Chrome version unknown", "WARNING")
        return None

    log_fn(f"Browser version: {chrome_full} (Major: {chrome_major})")

    try:
        import urllib.request
        import zipfile
        import io

        log_fn("Fetching ChromeDriver versions from Chrome for Testing API...")
        api_url = "https://googlechromelabs.github.io/chrome-for-testing/known-good-versions-with-downloads.json"
        with urllib.request.urlopen(api_url, timeout=15) as resp:
            data = json.loads(resp.read())

        # Cari versi yang cocok (major match, ambil terbaru)
        best = None
        for entry in data.get("versions", []):
            v = entry.get("version", "")
            if v.startswith(f"{chrome_major}."):
                # Pastikan ada download chromedriver win64
                dls = entry.get("downloads", {}).get("chromedriver", [])
                for dl in dls:
                    if "win64" in dl.get("platform", "") or "win32" in dl.get("platform", ""):
                        best = (v, dl["url"])
                        break

        if not best:
            # Fallback: linux64
            for entry in data.get("versions", []):
                v = entry.get("version", "")
                if v.startswith(f"{chrome_major}."):
                    dls = entry.get("downloads", {}).get("chromedriver", [])
                    if dls:
                        best = (v, dls[0]["url"])
                        break

        if not best:
            log_fn(f"No ChromeDriver found for Chrome {chrome_major}", "WARNING")
            return None

        ver, url = best
        log_fn(f"Found matching ChromeDriver version: {ver}")
        log_fn("Downloading ChromeDriver...")

        with urllib.request.urlopen(url, timeout=60) as resp:
            data_zip = resp.read()

        log_fn("Download complete. Extracting...")
        with zipfile.ZipFile(io.BytesIO(data_zip)) as zf:
            for name in zf.namelist():
                if name.endswith("chromedriver.exe") or name.endswith("/chromedriver"):
                    exe_data = zf.read(name)
                    out_name = "chromedriver.exe" if sys.platform == "win32" else "chromedriver"
                    out_path = os.path.join(base_dir, out_name)
                    with open(out_path, "wb") as f:
                        f.write(exe_data)
                    if sys.platform != "win32":
                        os.chmod(out_path, 0o755)
                    log_fn("ChromeDriver saved to application directory.")
                    log_fn("ChromeDriver setup complete!")
                    return out_path

    except Exception as e:
        log_fn(f"ChromeDriver download failed: {e}", "WARNING")

    return None


class GeminiEnterpriseProcessor(threading.Thread):
    """
    Thread utama yang memproses batch prompts.
    Mengelola satu browser + satu akun, auto-switch jika rate limit.
    """

    def __init__(
        self,
        base_dir:          str,
        prompts:           list,        # list of str
        output_dir:        str,
        config:            dict,
        log_callback:      Optional[Callable] = None,
        progress_callback: Optional[Callable] = None,
        finished_callback: Optional[Callable] = None,
        start_index:       int = 0,     # index prompt yang belum diproses
    ):
        super().__init__(daemon=True)
        self.base_dir       = base_dir
        self.prompts        = prompts
        self.output_dir     = output_dir or os.path.join(base_dir, "OUTPUT_GEMINI")
        self.config         = config
        self.log_cb         = log_callback
        self.progress_cb    = progress_callback
        self.finished_cb    = finished_callback
        self.start_index    = start_index
        self._cancelled     = False
        self._driver        = None
        self._temp_profile  = None
        self._mail_tab      = None
        self._gemini_tab    = None
        self._mail_client   = MailtickingClient(log_callback=log_callback)
        self.debug_dir      = os.path.join(base_dir, "DEBUG")

    def _log(self, msg, level="INFO"):
        if self.log_cb:
            self.log_cb(msg, level)

    def _progress(self, pct, msg):
        if self.progress_cb:
            self.progress_cb(pct, msg)

    def _done(self, ok, msg, path=""):
        if self.finished_cb:
            self.finished_cb(ok, msg, path)

    def cancel(self):
        self._cancelled = True

    def _debug_dump(self, driver, label: str):
        try:
            os.makedirs(self.debug_dir, exist_ok=True)
            ts = int(time.time())
            driver.save_screenshot(os.path.join(self.debug_dir, f"{label}_{ts}.png"))
        except Exception:
            pass

    # ── Driver setup ──────────────────────────────────────────────────────
    def _create_driver(self) -> Optional[object]:
        self._log("Setting up fresh Chrome browser...")

        cd_path = _setup_chromedriver(self.base_dir, self._log)

        self._temp_profile = tempfile.mkdtemp(prefix="gemini_profile_")
        self._log("Using fresh browser profile")

        headless = self.config.get("headless", False)

        opts = Options()
        opts.add_argument(f"--user-data-dir={self._temp_profile}")
        opts.add_argument("--no-first-run")
        opts.add_argument("--no-default-browser-check")
        opts.add_argument("--disable-blink-features=AutomationControlled")
        opts.add_argument("--disable-infobars")
        opts.add_argument("--lang=en-US")
        opts.add_argument("--window-size=1280,900")
        opts.add_argument("--disable-popup-blocking")
        opts.add_experimental_option("excludeSwitches", ["enable-automation"])
        opts.add_experimental_option("useAutomationExtension", False)
        opts.add_experimental_option("prefs", {
            "intl.accept_languages": "en,en_US",
            "download.default_directory": self.output_dir,
            "download.prompt_for_download": False,
            "download.directory_upgrade": True,
            "safebrowsing.enabled": True,
        })
        if headless:
            opts.add_argument("--headless=new")

        try:
            if cd_path:
                svc    = Service(executable_path=cd_path)
                driver = webdriver.Chrome(service=svc, options=opts)
            else:
                driver = webdriver.Chrome(options=opts)

            if stealth:
                stealth(driver,
                    languages=["en-US", "en"],
                    vendor="Google Inc.",
                    platform="Win32",
                    webgl_vendor="Intel Inc.",
                    renderer="Intel Iris OpenGL Engine",
                    fix_hairline=True,
                )

            driver.execute_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
            )

            chrome_major = _get_chrome_version()
            if chrome_major:
                self._log(f"ChromeDriver matched with browser v{chrome_major}")
            self._log("Chrome browser initialized")
            return driver

        except Exception as e:
            self._log(f"Failed to create Chrome driver: {e}", "ERROR")
            return None

    def _quit_driver(self, driver):
        try:
            if driver:
                pid = driver.service.process.pid if hasattr(driver, 'service') else None
                driver.quit()
                if pid:
                    self._log(f"Closed automation Chrome (PID: {pid})")
        except Exception:
            pass
        if self._temp_profile and os.path.exists(self._temp_profile):
            shutil.rmtree(self._temp_profile, ignore_errors=True)
            self._log("Temp profile directory cleaned up.")
            self._temp_profile = None

    # ── Selenium helpers ──────────────────────────────────────────────────
    def _wait_for(self, driver, css_selector, timeout=15):
        try:
            return WebDriverWait(driver, timeout).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, css_selector))
            )
        except TimeoutException:
            return None

    def _human_type(self, driver, element, text: str):
        element.click()
        time.sleep(random.uniform(0.3, 0.6))
        element.clear()
        time.sleep(random.uniform(0.1, 0.2))
        ac = ActionChains(driver)
        for char in text:
            ac.send_keys(char)
            ac.pause(random.uniform(0.06, 0.14))
        ac.perform()
        time.sleep(random.uniform(0.3, 0.6))

    def _human_click(self, driver, element):
        try:
            ActionChains(driver).move_to_element(element).pause(
                random.uniform(0.1, 0.3)
            ).click().perform()
        except Exception:
            element.click()

    # ── Main run ──────────────────────────────────────────────────────────
    def run(self):
        os.makedirs(self.output_dir, exist_ok=True)

        total    = len(self.prompts)
        delay    = int(self.config.get("delay", 5))
        retries  = int(self.config.get("retry",  1))

        self._log("--- STARTING AUTOMATION ---")
        self._log(f"Total prompts: {total}")
        self._log("Account switching: automatic on rate limit")
        self._log(f"Settings: delay {delay}s, retry {retries}x")
        self._log("Account switching: automatic on rate limit detection")

        current_index = self.start_index
        account_attempt = 0

        while current_index < total and not self._cancelled:
            account_attempt += 1

            # ── Setup browser + akun baru ──────────────────────────────────
            driver = self._create_driver()
            if driver is None:
                self._done(False, "Failed to create browser.")
                return

            ok = self._register_account(driver, account_attempt)
            if not ok:
                self._quit_driver(driver)
                self._done(False, "Account registration failed after retries.")
                return

            self._log("Account registration and setup completed successfully!")
            self._log("Ready to process prompts.")

            # ── Process prompts dengan akun ini ───────────────────────────
            rate_limited = False
            re_enter_prompt = None  # prompt yang perlu di-re-enter setelah switch

            while current_index < total and not self._cancelled:
                prompt = self.prompts[current_index]
                prompt_num = current_index + 1

                # Re-enter prompt jika ini adalah prompt yang interrupted
                if re_enter_prompt:
                    self._log(f"Re-entering prompt on new account...")
                    prompt = re_enter_prompt
                    re_enter_prompt = None

                self._log(f"--- Processing Prompt {prompt_num}/{total} ---")
                self._log(f"Prompt: {prompt[:40]}...")
                self._log("Snapshot last process")

                result = self._process_prompt(
                    driver, prompt, prompt_num, total, delay
                )

                if result == "rate_limit":
                    self._log("--- RATE LIMIT DETECTED ---")
                    self._log("Switching to new account...")
                    rate_limited = True
                    re_enter_prompt = prompt  # jangan increment, re-try prompt ini
                    break
                elif result == "ok":
                    current_index += 1
                    if current_index < total:
                        self._log(f"Waiting {delay} seconds before next prompt...")
                        time.sleep(delay)
                else:
                    # Error lain, skip prompt ini
                    self._log(f"Skipping prompt {prompt_num} due to error.", "WARNING")
                    current_index += 1

            # ── Switch akun ──────────────────────────────────────────────────────
            if rate_limited:
                self._log("--- SWITCHING TO NEW ACCOUNT ---")
                self._log("Step 1: Closing browser")
                self._quit_driver(driver)
                self._log(f"Step 2: Waiting 5 seconds...")
                time.sleep(5)
                self._log("Step 3: Opening new browser")
            else:
                self._quit_driver(driver)

        if not self._cancelled:
            self._log("All prompts processed!")
            self._done(True, f"Done! {current_index} prompts processed.")
        else:
            self._done(False, "Cancelled.")

    # ── Account registration (Steps 1-7) ────────────────────────────────
    def _register_account(self, driver, attempt_num: int = 1) -> bool:
        for retry in range(1, MAX_ACCOUNT_RETRY + 1):
            self._log(f"--- ACCOUNT REGISTRATION (Attempt {retry}/{MAX_ACCOUNT_RETRY}) ---")
            ok = self._register_once(driver)
            if ok:
                return True
            self._log(f"Registration attempt {retry} failed, retrying...", "WARNING")
            time.sleep(3)
        return False

    def _register_once(self, driver) -> bool:
        """
        Jalankan 7 step registrasi. Return True jika berhasil.
        """
        # ── Step 1: Temp email ─────────────────────────────────────────────
        self._log("Step 1: Getting fresh temp email")
        self._mail_tab = self._mail_client.open_mailticking_tab(driver)
        email = self._mail_client.get_fresh_email(driver)
        if not email or "@" not in email:
            self._log("Failed to get temp email", "ERROR")
            return False

        # ── Step 2: Buka Gemini Business di tab baru ────────────────────────
        self._log("Step 2: Registering on Gemini Business")
        time.sleep(random.uniform(1, 2))

        gemini_opened = False
        for tab_try in range(1, MAX_TAB_RETRY + 1):
            try:
                driver.execute_script("window.open('about:blank', '_blank');")
                time.sleep(1)
                if len(driver.window_handles) > 1:
                    driver.switch_to.window(driver.window_handles[-1])
                    self._gemini_tab = driver.current_window_handle
                    gemini_opened = True
                    self._log("Opened new tab for Gemini Business")
                    break
                else:
                    raise Exception("Tab not opened")
            except Exception:
                self._log(f"Tab open failed (attempt {tab_try}/{MAX_TAB_RETRY}), retrying...", "WARNING")
                time.sleep(random.uniform(2, 4))

        if not gemini_opened:
            self._log("Failed to open new tab after all methods", "ERROR")
            return False

        self._log("Registering on Gemini Business")
        time.sleep(random.uniform(1.5, 2.5))

        # ── Navigasi ke login page ─────────────────────────────────────────
        self._log("Navigating to Gemini Enterprise login page...")
        driver.get(GEMINI_HOME_URL)
        try:
            WebDriverWait(driver, 20).until(
                lambda d: d.current_url != "about:blank"
            )
        except Exception:
            pass
        self._log("Login page loaded.")
        time.sleep(random.uniform(2, 3))

        # Input email
        EMAIL_SELECTORS = [
            "input[name='loginHint']",
            "input[id='email-input']",
            "input[jsname='YPqjbf']",
            "input[type='email']",
            "input[name='email']",
            "input[autocomplete='email']",
            "input[type='text']",
        ]
        email_el = None
        for sel in EMAIL_SELECTORS:
            el = self._wait_for(driver, sel, timeout=12)
            if el and el.is_displayed():
                email_el = el
                break

        if not email_el:
            self._log("Email input not found on login page", "ERROR")
            self._debug_dump(driver, "no_email_input")
            return False

        self._human_type(driver, email_el, email)
        val = email_el.get_attribute("value")
        self._log(f"Email entered: {val}")
        time.sleep(random.uniform(0.8, 1.5))

        # Klik Continue / Submit
        submit_el = None
        for sel in ["button[type='submit']", "button"]:
            for el in driver.find_elements(By.CSS_SELECTOR, sel):
                if el.is_displayed() and el.is_enabled():
                    txt = el.text.lower()
                    if any(w in txt for w in ["continue", "next", "submit", "sign"]):
                        submit_el = el
                        break
                    elif not submit_el:
                        submit_el = el
            if submit_el:
                break

        if submit_el:
            self._human_click(driver, submit_el)
            self._log("Clicked 'Continue with email' button.")
        else:
            email_el.send_keys(Keys.RETURN)
            self._log("Pressed Enter to submit email.")

        self._log("Waiting for verification page...")
        time.sleep(random.uniform(3, 5))
        self._log("Verification page loaded.")

        # ── Step 3: Tunggu email verifikasi ────────────────────────────────
        self._log("Step 3: Waiting for verification email")
        found = self._mail_client.wait_for_verification_email(
            driver,
            mail_tab_handle   = self._mail_tab,
            gemini_tab_handle = self._gemini_tab,
            timeout           = OTP_TIMEOUT,
        )
        if not found:
            self._log("Verification email not received (timeout)", "ERROR")
            return False

        # ── Step 4: Ekstrak kode verifikasi ────────────────────────────────
        self._log("Step 4: Extracting verification code")
        otp = self._mail_client.extract_verification_code(
            driver,
            mail_tab_handle = self._mail_tab,
        )
        if not otp:
            self._log("Could not extract verification code", "ERROR")
            return False
        self._log(f"Verification code obtained: {otp}")

        # ── Step 5: Masukkan kode OTP di Gemini ────────────────────────────
        self._log("Step 5: Entering verification code")
        driver.switch_to.window(self._gemini_tab)
        self._log("Entering verification code")

        otp_submitted = self._submit_otp(driver, otp)
        if not otp_submitted:
            self._log("OTP submission failed", "ERROR")
            return False
        self._log("Verification code entered")
        time.sleep(random.uniform(1, 2))

        # Klik Verify
        for el in driver.find_elements(By.CSS_SELECTOR, "button"):
            if any(w in el.text.lower() for w in ["verify", "confirm", "continue"]):
                self._human_click(driver, el)
                self._log("Clicked 'Verify' button.")
                break
        time.sleep(random.uniform(2, 3))

        # ── Step 6: Signup form (isi nama) ─────────────────────────────────
        self._log("Step 6: Completing signup")
        self._log("Waiting for signup page to load...")
        time.sleep(random.uniform(3, 5))

        # Cek apakah ada form nama
        name_el = None
        for sel in [
            "input[name='name']", "input[id*='name']",
            "input[placeholder*='name' i]", "input[type='text']",
        ]:
            el = self._wait_for(driver, sel, timeout=8)
            if el and el.is_displayed():
                name_el = el
                break

        if name_el:
            self._log("Signup page loaded. Filling name form...")
            name = _random_name()
            self._human_type(driver, name_el, name)
            self._log(f"Name entered: {name}")
            time.sleep(random.uniform(0.5, 1))

            # Klik Agree / Get started
            for el in driver.find_elements(By.CSS_SELECTOR, "button"):
                if any(w in el.text.lower() for w in ["agree", "get started", "continue", "next"]):
                    self._human_click(driver, el)
                    self._log("Clicked 'Agree & get started' button.")
                    break
        else:
            self._log("No name form found, proceeding...", "WARNING")

        # ── Tunggu home page ───────────────────────────────────────────────
        self._log("Waiting for Gemini Business home page to load (signing in)...")
        loaded = False
        for _ in range(40):
            time.sleep(2)
            url = driver.current_url
            if "business.gemini.google" in url and "sign" not in url.lower():
                loaded = True
                break
        if loaded:
            self._log("Gemini Business home page loaded")
        else:
            self._log("Home page load timeout, continuing anyway...", "WARNING")

        time.sleep(random.uniform(2, 3))

        # ── Step 7: Initial setup ──────────────────────────────────────────
        self._log("Step 7: Initial setup")
        self._log("Performing initial setup...")
        self._initial_setup(driver)

        self._log("Account registration and setup completed successfully!")
        return True

    def _submit_otp(self, driver, otp: str) -> bool:
        """Masukkan kode OTP ke form Google."""
        try:
            # Coba input per-karakter
            otp_inputs = driver.find_elements(By.CSS_SELECTOR,
                "input[type='text'][maxlength='1'],"
                "input[autocomplete='one-time-code'],"
                "input[name*='otp'],input[name*='code']"
            )
            if len(otp_inputs) > 1:
                for i, digit in enumerate(otp[:len(otp_inputs)]):
                    otp_inputs[i].clear()
                    otp_inputs[i].send_keys(digit)
                    time.sleep(random.uniform(0.1, 0.2))
                return True
            elif len(otp_inputs) == 1:
                self._human_type(driver, otp_inputs[0], otp)
                return True
            else:
                ActionChains(driver).send_keys(otp).perform()
                return True
        except Exception as e:
            self._log(f"OTP input error: {e}", "WARNING")
            return False

    def _initial_setup(self, driver):
        """Step 7: Tutup welcome dialog, pilih Veo tool."""
        self._log("Closing welcome dialog...")
        try:
            for sel in [
                "button[aria-label*='close' i]", "button[aria-label*='dismiss' i]",
                "[role='dialog'] button", ".modal button",
            ]:
                els = driver.find_elements(By.CSS_SELECTOR, sel)
                for el in els:
                    if el.is_displayed():
                        self._human_click(driver, el)
                        break
        except Exception:
            pass
        self._log("Welcome dialog closed")
        time.sleep(random.uniform(1, 2))

        self._log("Clicking tools button...")
        tools_btn = None
        for sel in [
            "button[aria-label*='tool' i]",
            "button[aria-label*='attach' i]",
            "button[aria-label*='more' i]",
            "[role='button'][aria-label*='tool' i]",
        ]:
            el = self._wait_for(driver, sel, timeout=8)
            if el and el.is_displayed():
                tools_btn = el
                break
        if not tools_btn:
            btns = driver.find_elements(By.CSS_SELECTOR, "form button")
            if btns:
                tools_btn = btns[0]

        if tools_btn:
            self._human_click(driver, tools_btn)
            self._log("Tools button clicked. Waiting for menu...")
            time.sleep(random.uniform(1, 2))

            veo_el = None
            for sel in ["[role='menuitem']", "[role='option']", "li"]:
                for el in driver.find_elements(By.CSS_SELECTOR, sel):
                    if "veo" in el.text.lower() or "video" in el.text.lower():
                        veo_el = el
                        break
                if veo_el:
                    break

            if veo_el:
                self._human_click(driver, veo_el)
                self._log("Clicking 'Create videos with Veo'...")
                time.sleep(random.uniform(1, 2))
                self._log("'Create videos with Veo' selected")

        self._log("Initial setup completed successfully!")

    # ── Process single prompt ───────────────────────────────────────────────
    def _process_prompt(
        self, driver, prompt: str, prompt_num: int, total: int, delay: int
    ) -> str:
        """
        Process satu prompt.
        Return: 'ok' | 'rate_limit' | 'error'
        """
        if self._gemini_tab:
            try:
                driver.switch_to.window(self._gemini_tab)
            except Exception:
                pass

        self._progress(
            int((prompt_num / total) * 100),
            f"Prompt {prompt_num}/{total}"
        )

        # Input prompt
        self._log(f"Inputting prompt: {prompt[:40]}...")
        prompt_el = None
        for sel in ["textarea", "[contenteditable='true']", "[role='textbox']"]:
            el = self._wait_for(driver, sel, timeout=10)
            if el and el.is_displayed():
                prompt_el = el
                break

        if not prompt_el:
            self._log("Prompt input not found", "ERROR")
            return "error"

        self._human_type(driver, prompt_el, prompt)
        self._log("Prompt inputted successfully")
        time.sleep(random.uniform(0.7, 1.2))

        # Klik generate
        self._log("Clicking generate button...")
        send_els = driver.find_elements(By.CSS_SELECTOR,
            "button[aria-label*='send' i],button[aria-label*='generate' i],"
            "button[aria-label*='Submit' i],button[type='submit']"
        )
        if send_els:
            self._human_click(driver, send_els[0])
        else:
            prompt_el.send_keys(Keys.RETURN)
        self._log("Generate button clicked")
        time.sleep(random.uniform(2, 3))

        # Tunggu + deteksi rate limit
        self._log("Waiting for video generation...")
        return self._wait_for_generation(driver, prompt_num)

    def _wait_for_generation(self, driver, prompt_num: int) -> str:
        """
        Tunggu generasi video. Deteksi rate limit via 'thinking' yang hilang terlalu cepat.
        Return: 'ok' | 'rate_limit' | 'error'
        """
        # Deteksi thinking indicator muncul
        thinking_start = None
        thinking_appeared = False

        # Poll singkat untuk cek thinking muncul
        for _ in range(10):
            try:
                src = driver.page_source.lower()
                if any(k in src for k in ["thinking", "generating", "loading"]):
                    if not thinking_appeared:
                        thinking_appeared = True
                        thinking_start = time.time()
                        self._log("Thinking...")
                    break
            except Exception:
                pass
            time.sleep(0.5)

        # Cek apakah thinking langsung hilang (rate limit)
        if thinking_appeared and thinking_start:
            time.sleep(2)
            try:
                src = driver.page_source.lower()
                thinking_still = any(k in src for k in ["thinking", "generating"])
                elapsed = time.time() - thinking_start
                if not thinking_still and elapsed < RATE_LIMIT_THINKING_THRESHOLD:
                    self._log(
                        f"Thinking disappeared after only {elapsed:.1f}s "
                        f"- RATE LIMIT detected!"
                    )
                    return "rate_limit"
            except Exception:
                pass

        # Tunggu video selesai
        start = time.time()
        while time.time() - start < VIDEO_GEN_TIMEOUT:
            if self._cancelled:
                return "error"
            elapsed = int(time.time() - start)

            try:
                src = driver.page_source.lower()

                # Cek rate limit di halaman
                if any(k in src for k in [
                    "rate limit", "quota exceeded", "try again later",
                    "too many requests"
                ]):
                    self._log("Rate limit message detected on page")
                    return "rate_limit"

                # Cek selesai
                if driver.find_elements(By.CSS_SELECTOR,
                    "button[aria-label*='download' i],a[download]"):
                    break
                for btn in driver.find_elements(By.TAG_NAME, "button"):
                    if "download" in btn.text.lower():
                        break

                # Cek masih loading
                if any(k in src for k in ["thinking", "generating", "rendering"]):
                    if elapsed % 12 == 0 and elapsed > 0:
                        self._log(f"Still generating... ({elapsed}s elapsed)")
                else:
                    # Thinking selesai, tunggu render
                    if elapsed > 5:
                        if elapsed % 12 == 0:
                            self._log("Thinking completed. Waiting for video to render...")

            except Exception:
                pass

            time.sleep(POLLING_INTERVAL)
        else:
            self._log("Video generation timeout", "WARNING")
            return "error"

        self._log("Video generation complete!")
        return self._download_video(driver, prompt_num)

    def _download_video(self, driver, prompt_num: int) -> str:
        """Klik download, tunggu file."""
        self._log("Downloading video...")
        try:
            dl_btn = None
            for sel in ["button[aria-label*='download' i]", "a[download]"]:
                els = driver.find_elements(By.CSS_SELECTOR, sel)
                if els:
                    dl_btn = els[0]
                    break
            if not dl_btn:
                for btn in driver.find_elements(By.TAG_NAME, "button"):
                    if "download" in btn.text.lower():
                        dl_btn = btn
                        break
            if not dl_btn:
                self._log("Download button not found", "ERROR")
                return "error"

            self._human_click(driver, dl_btn)
            self._log("Download button clicked")
            time.sleep(random.uniform(1, 2))

            # Cek popup konfirmasi download
            self._log("Looking for download confirmation popup...")
            try:
                for el in driver.find_elements(By.CSS_SELECTOR, "button"):
                    if any(w in el.text.lower() for w in ["download", "confirm", "save"]):
                        if el.is_displayed():
                            self._human_click(driver, el)
                            self._log("Download confirmation clicked")
                            break
            except Exception:
                pass

            self._log("Video download initiated successfully")

            # Tunggu file muncul
            for _ in range(120):
                time.sleep(1)
                files = [
                    f for f in os.listdir(self.output_dir)
                    if f.endswith((".mp4", ".webm"))
                    and not f.endswith(".crdownload")
                ]
                if files:
                    newest = max(
                        [os.path.join(self.output_dir, f) for f in files],
                        key=os.path.getmtime
                    )
                    fname = f"ReenzAuto_G-Business_{prompt_num}_{int(time.time()*1000)}.mp4"
                    dest  = os.path.join(self.output_dir, fname)
                    try:
                        if newest != dest:
                            os.rename(newest, dest)
                        newest = dest
                    except Exception:
                        pass
                    self._log(f"Saved: {os.path.basename(newest)}")
                    self._log(f"Successfully processed prompt {prompt_num}")
                    return "ok"

            self._log("File did not appear after 120s", "WARNING")
            return "error"

        except Exception as e:
            self._log(f"Download error: {e}", "ERROR")
            return "error"
