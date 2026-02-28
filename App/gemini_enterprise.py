"""
gemini_enterprise.py

Otomasi generate video di business.gemini.google
Menggunakan selenium-stealth (regular Chrome) + fresh temp profile.

Alur lengkap (EXACT selectors dari inspect element):
  Step 1  : Buka Chrome profil baru
  Step 2  : Buka mailticking.com - tunggu load penuh
  Step 3  : Loop klik Change sampai email bukan @gmail/@googlemail
  Step 4  : Centang HANYA id="type4" (abc@domain.com) -> Activate
  Step 5  : Buka business.gemini.google di tab baru - tunggu load
  Step 6  : Input email ke input#email-input (jsname="YPqjbf")
  Step 7  : Klik button#log-in-button (Continue with email)
  Step 8  : Tunggu halaman OTP load - kembali ke tab mailticking
  Step 9  : Reload mailticking - klik a[href*='/mail/view/'] (Gemini email)
  Step 10 : Tunggu span.verification-code muncul - baca OTP
  Step 11 : Kembali tab Gemini - input OTP ke input.J6L5wc
  Step 12 : Klik verify button
  Step 13 : Tunggu form nama - input ke input[formcontrolname="fullName"]
  Step 14 : Klik span.mdc-button__label 'Agree & get started'
  Step 15 : Tunggu h1.title 'Signing you in...' hilang
  Step 16 : Tutup popup 'I'll do this later'
             EXACT: <button id="button" class="button"> (Web Component)
             -> cari button yang teks slotnya mengandung 'later' / 'dismiss'
             -> fallback: klik button#button.button yang muncul setelah login
  Step 17 : Klik tools button (md-icon: page_info)
  Step 18 : Pilih 'Create videos with Veo'
  Step 19 : Input prompt ke ProseMirror editor - tekan Enter
  Step 20 : Tunggu div.thinking-message hilang - tunggu video render
  Step 21 : Download video
    21a: Klik button#button[aria-label="Download video file"]
    21b: Tunggu popup konfirmasi muncul -> klik button#button.button
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

OTP_TIMEOUT           = 90
VIDEO_GEN_TIMEOUT     = 600
POLLING_INTERVAL      = 8
MAX_ACCOUNT_RETRY     = 3
MAX_TAB_RETRY         = 3
RATE_LIMIT_THINKING_THRESHOLD = 5.0

CHROME_PATHS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    os.path.expanduser(r"~\AppData\Local\Google\Chrome\Application\chrome.exe"),
    "/usr/bin/google-chrome",
    "/usr/bin/chromium-browser",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
]

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
    log_fn("Checking ChromeDriver compatibility...")
    chrome_major = _get_chrome_version()
    chrome_full  = _get_chrome_full_version()

    if chrome_major:
        log_fn(f"Detected Chrome version: {chrome_major}")
    else:
        log_fn("Could not detect Chrome version", "WARNING")

    local_paths = [
        os.path.join(base_dir, "chromedriver.exe"),
        os.path.join(base_dir, "chromedriver"),
        "chromedriver.exe", "chromedriver",
    ]
    for path in local_paths:
        if os.path.exists(path):
            try:
                r = subprocess.run([path, "--version"],
                    capture_output=True, text=True, timeout=5)
                m = re.search(r"(\d+)\.\d+\.\d+", r.stdout)
                if m and chrome_major and int(m.group(1)) == chrome_major:
                    log_fn(f"ChromeDriver version matches browser.")
                    return path
                elif m:
                    log_fn(f"Local ChromeDriver v{m.group(1)} != Chrome v{chrome_major}, updating...")
            except Exception:
                pass

    log_fn("Downloading ChromeDriver matching browser version...")
    if not chrome_full or not chrome_major:
        log_fn("Cannot auto-download ChromeDriver: Chrome version unknown", "WARNING")
        return None

    try:
        import urllib.request
        import zipfile
        import io

        api_url = "https://googlechromelabs.github.io/chrome-for-testing/known-good-versions-with-downloads.json"
        with urllib.request.urlopen(api_url, timeout=15) as resp:
            data = json.loads(resp.read())

        best = None
        for entry in data.get("versions", []):
            v = entry.get("version", "")
            if v.startswith(f"{chrome_major}."):
                dls = entry.get("downloads", {}).get("chromedriver", [])
                for dl in dls:
                    if "win64" in dl.get("platform", "") or "win32" in dl.get("platform", ""):
                        best = (v, dl["url"])
                        break

        if not best:
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
        log_fn(f"Downloading ChromeDriver {ver}...")

        with urllib.request.urlopen(url, timeout=60) as resp:
            data_zip = resp.read()

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
                    log_fn("ChromeDriver setup complete!")
                    return out_path
    except Exception as e:
        log_fn(f"ChromeDriver download failed: {e}", "WARNING")
    return None


class GeminiEnterpriseProcessor(threading.Thread):

    def __init__(
        self,
        base_dir:          str,
        prompts:           list,
        output_dir:        str,
        config:            dict,
        log_callback:      Optional[Callable] = None,
        progress_callback: Optional[Callable] = None,
        finished_callback: Optional[Callable] = None,
        start_index:       int = 0,
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
            driver.save_screenshot(
                os.path.join(self.debug_dir, f"{label}_{ts}.png"))
        except Exception:
            pass

    def _js_click(self, driver, element):
        driver.execute_script("arguments[0].click();", element)

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
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            self._log("Chrome browser initialized")
            return driver
        except Exception as e:
            self._log(f"Failed to create Chrome driver: {e}", "ERROR")
            return None

    def _quit_driver(self, driver):
        try:
            if driver:
                driver.quit()
        except Exception:
            pass
        if self._temp_profile and os.path.exists(self._temp_profile):
            shutil.rmtree(self._temp_profile, ignore_errors=True)
            self._temp_profile = None

    # ── Selenium helpers ──────────────────────────────────────────────────
    def _wait_for(self, driver, css_selector, timeout=15):
        try:
            return WebDriverWait(driver, timeout).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, css_selector)))
        except TimeoutException:
            return None

    def _wait_visible(self, driver, css_selector, timeout=15):
        try:
            return WebDriverWait(driver, timeout).until(
                EC.visibility_of_element_located((By.CSS_SELECTOR, css_selector)))
        except TimeoutException:
            return None

    def _wait_gone(self, driver, css_selector, timeout=60):
        try:
            WebDriverWait(driver, timeout).until(
                EC.invisibility_of_element_located((By.CSS_SELECTOR, css_selector)))
            return True
        except TimeoutException:
            return False

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
                random.uniform(0.1, 0.3)).click().perform()
        except Exception:
            element.click()

    # ── Main run ──────────────────────────────────────────────────────────
    def run(self):
        os.makedirs(self.output_dir, exist_ok=True)

        total   = len(self.prompts)
        delay   = int(self.config.get("delay", 5))
        retries = int(self.config.get("retry",  1))

        self._log("--- STARTING AUTOMATION ---")
        self._log(f"Total prompts: {total}")
        self._log(f"Settings: delay {delay}s, retry {retries}x")

        current_index   = self.start_index
        re_enter_prompt = None

        while current_index < total and not self._cancelled:
            driver = self._create_driver()
            if driver is None:
                self._done(False, "Failed to create browser.")
                return

            ok = self._register_account(driver)
            if not ok:
                self._quit_driver(driver)
                self._done(False, "Account registration failed.")
                return

            rate_limited = False

            while current_index < total and not self._cancelled:
                prompt = re_enter_prompt or self.prompts[current_index]
                re_enter_prompt = None
                prompt_num = current_index + 1

                self._log(f"--- Processing Prompt {prompt_num}/{total} ---")

                result = self._process_prompt(driver, prompt, prompt_num, total, delay)

                if result == "rate_limit":
                    self._log("Rate limit detected - switching account...")
                    rate_limited    = True
                    re_enter_prompt = prompt
                    break
                elif result == "ok":
                    current_index += 1
                    if current_index < total:
                        time.sleep(delay)
                else:
                    self._log(f"Skipping prompt {prompt_num}", "WARNING")
                    current_index += 1

            self._quit_driver(driver)
            if rate_limited:
                time.sleep(5)

        if not self._cancelled:
            self._log("All prompts processed!")
            self._done(True, f"Done! {current_index} prompts processed.")
        else:
            self._done(False, "Cancelled.")

    # ── Account registration ────────────────────────────────────────────
    def _register_account(self, driver) -> bool:
        for retry in range(1, MAX_ACCOUNT_RETRY + 1):
            self._log(f"--- ACCOUNT REGISTRATION (Attempt {retry}/{MAX_ACCOUNT_RETRY}) ---")
            ok = self._register_once(driver)
            if ok:
                return True
            self._log(f"Attempt {retry} failed, retrying...", "WARNING")
            time.sleep(3)
        return False

    def _register_once(self, driver) -> bool:
        self._log("Step 1: Getting fresh temp email from mailticking.com")
        self._mail_tab = self._mail_client.open_mailticking_tab(driver)
        email = self._mail_client.get_fresh_email(driver)
        if not email or "@" not in email:
            self._log("Failed to get temp email", "ERROR")
            return False
        self._log(f"Temp email: {email}")

        self._log("Step 2: Opening Gemini Business in new tab")
        for tab_try in range(1, MAX_TAB_RETRY + 1):
            try:
                driver.execute_script("window.open('about:blank', '_blank');")
                time.sleep(1)
                if len(driver.window_handles) > 1:
                    driver.switch_to.window(driver.window_handles[-1])
                    self._gemini_tab = driver.current_window_handle
                    break
                raise Exception("Tab not opened")
            except Exception:
                self._log(f"Tab open failed ({tab_try}/{MAX_TAB_RETRY})", "WARNING")
                time.sleep(2)
        else:
            self._log("Failed to open new tab", "ERROR")
            return False

        self._log("Navigating to business.gemini.google...")
        driver.get(GEMINI_HOME_URL)
        try:
            WebDriverWait(driver, 20).until(
                lambda d: d.current_url != "about:blank")
        except Exception:
            pass
        time.sleep(random.uniform(2, 3))
        self._log("Gemini Business page loaded.")

        self._log("Step 3: Entering email address")
        EMAIL_SELECTORS = [
            "input#email-input",
            "input[jsname='YPqjbf']",
            "input[name='loginHint']",
            "input[type='email']",
            "input[type='text']",
        ]
        email_el = None
        for sel in EMAIL_SELECTORS:
            el = self._wait_for(driver, sel, timeout=15)
            if el and el.is_displayed():
                email_el = el
                self._log(f"Email input found: {sel}")
                break

        if not email_el:
            self._log("Email input not found", "ERROR")
            self._debug_dump(driver, "no_email_input")
            return False

        self._human_type(driver, email_el, email)
        self._log(f"Email entered: {email}")
        time.sleep(random.uniform(0.8, 1.5))

        self._log("Step 4: Clicking 'Continue with email'")
        submit_el = None
        for sel in [
            "button#log-in-button",
            "button[aria-label='Continue with email']",
            "button[jsname='jXw9Fb']",
            "button[type='submit']",
        ]:
            try:
                el = driver.find_element(By.CSS_SELECTOR, sel)
                if el.is_displayed() and el.is_enabled():
                    submit_el = el
                    self._log(f"Submit button found: {sel}")
                    break
            except Exception:
                pass

        if submit_el:
            self._human_click(driver, submit_el)
            self._log("Clicked 'Continue with email'")
        else:
            email_el.send_keys(Keys.RETURN)
            self._log("Pressed Enter to submit email")

        self._log("Step 5: Waiting for OTP page to load...")
        time.sleep(random.uniform(3, 5))
        self._log("OTP page loaded.")

        self._log("Step 6: Checking mailticking inbox for verification email")
        found = self._mail_client.wait_for_verification_email(
            driver,
            mail_tab_handle   = self._mail_tab,
            gemini_tab_handle = self._gemini_tab,
            timeout           = OTP_TIMEOUT,
        )
        if not found:
            self._log("Verification email not received (timeout)", "ERROR")
            return False

        self._log("Step 7: Extracting OTP from email")
        otp = self._mail_client.extract_verification_code(
            driver,
            mail_tab_handle = self._mail_tab,
        )
        if not otp:
            self._log("Could not extract OTP", "ERROR")
            return False
        self._log(f"OTP obtained: {otp}")

        self._log("Step 8: Entering OTP on Gemini")
        driver.switch_to.window(self._gemini_tab)
        time.sleep(random.uniform(1, 2))

        otp_submitted = self._submit_otp(driver, otp)
        if not otp_submitted:
            self._log("OTP submission failed", "ERROR")
            return False
        self._log("OTP entered")
        time.sleep(random.uniform(0.8, 1.2))

        self._log("Step 9: Clicking Verify button")
        verify_clicked = False
        for sel in [
            "button[jsname='LgbsSe']",
            "button[type='submit']",
            ".YUhpIc-RLmnJb",
        ]:
            try:
                els = driver.find_elements(By.CSS_SELECTOR, sel)
                for el in els:
                    if el.is_displayed():
                        self._human_click(driver, el)
                        self._log(f"Clicked verify: {sel}")
                        verify_clicked = True
                        break
                if verify_clicked:
                    break
            except Exception:
                pass

        if not verify_clicked:
            for el in driver.find_elements(By.TAG_NAME, "button"):
                try:
                    if any(w in el.text.lower() for w in ["verify", "confirm", "continue"])\
                            and el.is_displayed():
                        self._human_click(driver, el)
                        self._log("Clicked verify (text fallback)")
                        verify_clicked = True
                        break
                except Exception:
                    pass

        time.sleep(random.uniform(2, 4))

        self._log("Step 10: Completing signup - entering name")
        name_el = None
        for sel in [
            "input[formcontrolname='fullName']",
            "input#mat-input-0",
            "input[placeholder='Full name']",
            "input[type='text'][required]",
        ]:
            el = self._wait_for(driver, sel, timeout=10)
            if el and el.is_displayed():
                name_el = el
                self._log(f"Name input found: {sel}")
                break

        if name_el:
            name = _random_name()
            self._human_type(driver, name_el, name)
            self._log(f"Name entered: {name}")
            time.sleep(random.uniform(0.5, 1))
        else:
            self._log("Name form not found, proceeding...", "WARNING")

        self._log("Step 11: Clicking 'Agree & get started'")
        agree_clicked = False
        for sel in [
            ".mdc-button__label",
            "button.mdc-button",
            "button[mat-flat-button]",
        ]:
            try:
                els = driver.find_elements(By.CSS_SELECTOR, sel)
                for el in els:
                    txt = (el.text or "").strip()
                    if "agree" in txt.lower() or "get started" in txt.lower():
                        try:
                            btn = el.find_element(By.XPATH, "./ancestor::button")
                            self._human_click(driver, btn)
                        except Exception:
                            self._human_click(driver, el)
                        self._log("Clicked 'Agree & get started'")
                        agree_clicked = True
                        break
                if agree_clicked:
                    break
            except Exception:
                pass

        if not agree_clicked:
            for el in driver.find_elements(By.TAG_NAME, "button"):
                try:
                    if ("agree" in el.text.lower() or "get started" in el.text.lower())\
                            and el.is_displayed():
                        self._human_click(driver, el)
                        self._log("Clicked agree (fallback)")
                        agree_clicked = True
                        break
                except Exception:
                    pass

        self._log("Step 12: Waiting for 'Signing you in...' to disappear")
        self._wait_gone(driver, "h1.title", timeout=60)
        self._log("Signing in completed.")
        time.sleep(random.uniform(2, 3))

        self._log("Step 13: Initial setup")
        self._initial_setup(driver)
        self._log("Account registration and setup completed successfully!")
        return True

    def _submit_otp(self, driver, otp: str) -> bool:
        for sel in [
            "input.J6L5wc",
            "input[jsname='ovqh0b']",
            "input[name='pinInput']",
        ]:
            try:
                el = driver.find_element(By.CSS_SELECTOR, sel)
                driver.execute_script(
                    "arguments[0].value = arguments[1];"
                    "arguments[0].dispatchEvent(new Event('input', {bubbles:true}));"
                    "arguments[0].dispatchEvent(new Event('change', {bubbles:true}));",
                    el, otp
                )
                self._log(f"OTP entered via {sel}: {otp}")
                time.sleep(0.3)
                try:
                    el.send_keys(otp)
                except Exception:
                    pass
                return True
            except Exception:
                pass

        try:
            inputs = driver.find_elements(By.CSS_SELECTOR,
                "input[type='text'], input[autocomplete='one-time-code']")
            for inp in inputs:
                self._human_type(driver, inp, otp)
                return True
        except Exception:
            pass

        try:
            ActionChains(driver).send_keys(otp).perform()
            return True
        except Exception:
            pass
        return False

    def _initial_setup(self, driver):
        """
        Step 16-18:
          16. Tutup popup 'I'll do this later'
              EXACT: <button id="button" class="button"> (Web Component)
              -> Karena Web Component, teks 'I'll do this later' ada di dalam
                 <slot> yang tidak bisa dibaca langsung lewat el.text
              -> Strategy:
                 1. Cari button#button.button yang muncul setelah login
                 2. Filter: BUKAN yang punya class 'icon-button' / aria-label download
                 3. Fallback: cari via page source innerHTML yang mengandung 'later'
          17. Klik tools button -> md-icon: page_info
          18. Pilih 'Create videos with Veo' -> div[slot='headline']
        """
        self._log("Step 16: Closing 'I'll do this later' popup...")
        dismissed = self._dismiss_later_popup(driver)
        if dismissed:
            self._log("Popup 'I'll do this later' dismissed.")
        else:
            self._log("No 'do this later' popup found, proceeding...", "WARNING")
        time.sleep(random.uniform(1, 2))

        self._log("Step 17: Clicking tools button (page_info icon)...")
        tools_clicked = False
        for sel in [
            "md-icon-button[aria-label*='tool' i]",
            "button[aria-label*='tool' i]",
            "[slot='icon-button']",
        ]:
            try:
                els = driver.find_elements(By.CSS_SELECTOR, sel)
                for el in els:
                    if el.is_displayed():
                        self._human_click(driver, el)
                        self._log(f"Tools button clicked: {sel}")
                        tools_clicked = True
                        break
                if tools_clicked:
                    break
            except Exception:
                pass

        if not tools_clicked:
            try:
                icons = driver.find_elements(By.TAG_NAME, "md-icon")
                for icon in icons:
                    if "page_info" in (icon.text or "").strip():
                        try:
                            btn = icon.find_element(
                                By.XPATH, "./ancestor::button | ./ancestor::md-icon-button")
                            self._human_click(driver, btn)
                            self._log("Clicked tools button via md-icon page_info")
                            tools_clicked = True
                        except Exception:
                            self._js_click(driver, icon)
                            tools_clicked = True
                        break
            except Exception:
                pass

        if not tools_clicked:
            self._log("Tools button not found", "WARNING")
            return

        time.sleep(random.uniform(1, 1.5))

        self._log("Step 18: Selecting 'Create videos with Veo'...")
        veo_clicked = False
        for sel in ["div[slot='headline']", "[slot='headline']"]:
            try:
                els = driver.find_elements(By.CSS_SELECTOR, sel)
                for el in els:
                    txt = (el.text or "").strip().lower()
                    if "create video" in txt or "veo" in txt:
                        try:
                            item = el.find_element(
                                By.XPATH,
                                "./ancestor::md-menu-item | "
                                "./ancestor::li | "
                                "./ancestor::*[@role='menuitem']"
                            )
                            self._human_click(driver, item)
                        except Exception:
                            self._human_click(driver, el)
                        self._log("Clicked 'Create videos with Veo'")
                        veo_clicked = True
                        break
                if veo_clicked:
                    break
            except Exception:
                pass

        if not veo_clicked:
            for el in driver.find_elements(By.XPATH,
                    "//*[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ',"
                    "'abcdefghijklmnopqrstuvwxyz'),'create video') or "
                    "contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ',"
                    "'abcdefghijklmnopqrstuvwxyz'),'veo')]"):
                try:
                    if el.is_displayed():
                        self._human_click(driver, el)
                        self._log("Clicked Veo (fallback text)")
                        veo_clicked = True
                        break
                except Exception:
                    pass

        time.sleep(random.uniform(1, 2))
        self._log("Initial setup completed!")

    def _dismiss_later_popup(self, driver) -> bool:
        """
        Tutup popup 'I'll do this later' setelah login.

        EXACT dari inspect:
          <button id="button" class="button">
            <span class="touch"></span>
            <slot name="icon"></slot>
            <span class="label"><slot></slot></span>
          </button>

        Karena ini Web Component dengan <slot>, teks 'I'll do this later'
        tidak tersedia via .text / .get_attribute("textContent") biasa.

        Strategy (urutan prioritas):
          1. Cari via innerHTML page source yang mengandung 'later' / 'dismiss'
             -> lalu cari button#button.button yang ada di sekitarnya
          2. Tunggu button#button.button muncul -> klik yang paling baru
             (bukan download button - tidak punya class icon-button)
          3. Fallback: span.touch yang visible (dismiss / close)
        """
        # Tunggu halaman settle dulu setelah login
        time.sleep(random.uniform(1.5, 2.5))

        # Strategy 1: Cari via page source innerHTML
        # Teks 'later' / 'dismiss' / 'skip' mungkin ada di slot content
        try:
            src = driver.page_source.lower()
            keywords = ["do this later", "i'll do this later", "skip", "dismiss", "not now"]
            if any(k in src for k in keywords):
                self._log("Popup text detected in page source, looking for button...")
                # Cari button#button.button yang visible dan bukan icon-button
                for sel in [
                    "button#button.button",
                    "button#button",
                    "button.button",
                ]:
                    try:
                        els = driver.find_elements(By.CSS_SELECTOR, sel)
                        for btn in els:
                            cls  = (btn.get_attribute("class") or "").lower()
                            aria = (btn.get_attribute("aria-label") or "").lower()
                            # Skip tombol download (icon-button) dan tombol yang jelas bukan dismiss
                            if "icon-button" in cls:
                                continue
                            if "download" in aria:
                                continue
                            if btn.is_displayed():
                                self._js_click(driver, btn)
                                self._log(f"Clicked dismiss popup: {sel} (via page source detection)")
                                return True
                    except Exception:
                        pass
        except Exception:
            pass

        # Strategy 2: Cari button#button.button yang muncul
        # Tunggu max 8 detik
        deadline = time.time() + 8
        while time.time() < deadline:
            for sel in [
                "button#button.button",
                "button#button",
                "button.button",
            ]:
                try:
                    els = driver.find_elements(By.CSS_SELECTOR, sel)
                    for btn in els:
                        cls  = (btn.get_attribute("class") or "").lower()
                        aria = (btn.get_attribute("aria-label") or "").lower()
                        if "icon-button" in cls or "download" in aria:
                            continue
                        if btn.is_displayed():
                            self._js_click(driver, btn)
                            self._log(f"Clicked dismiss popup: {sel}")
                            return True
                except Exception:
                    pass
            time.sleep(0.5)

        # Strategy 3: Fallback span.touch (teks visible lama)
        try:
            els = driver.find_elements(By.CSS_SELECTOR, "span.touch")
            for el in els:
                if el.is_displayed():
                    self._js_click(driver, el)
                    self._log("Clicked span.touch (fallback dismiss)")
                    return True
        except Exception:
            pass

        return False

    # ── Process single prompt ───────────────────────────────────────────
    def _process_prompt(
        self, driver, prompt: str, prompt_num: int, total: int, delay: int
    ) -> str:
        if self._gemini_tab:
            try:
                driver.switch_to.window(self._gemini_tab)
            except Exception:
                pass

        self._progress(int((prompt_num / total) * 100), f"Prompt {prompt_num}/{total}")

        self._log(f"Step 14: Inputting prompt {prompt_num}/{total}")
        prompt_el = None
        for sel in [
            "div.ProseMirror",
            "div[contenteditable='true'].ProseMirror",
            "[contenteditable='true']",
            "div[role='textbox']",
            "textarea",
        ]:
            el = self._wait_for(driver, sel, timeout=10)
            if el and el.is_displayed():
                prompt_el = el
                self._log(f"Prompt input found: {sel}")
                break

        if not prompt_el:
            self._log("Prompt input not found", "ERROR")
            return "error"

        driver.execute_script("arguments[0].click();", prompt_el)
        time.sleep(0.3)
        ActionChains(driver).key_down(Keys.CONTROL).send_keys("a").key_up(
            Keys.CONTROL).perform()
        time.sleep(0.2)
        ActionChains(driver).send_keys(Keys.DELETE).perform()
        time.sleep(0.2)

        ac = ActionChains(driver)
        for char in prompt:
            ac.send_keys(char)
            ac.pause(random.uniform(0.04, 0.10))
        ac.perform()
        self._log("Prompt entered")
        time.sleep(random.uniform(0.7, 1.2))

        self._log("Pressing Enter to generate...")
        ActionChains(driver).send_keys(Keys.RETURN).perform()
        self._log("Generation started")
        time.sleep(random.uniform(2, 3))

        return self._wait_for_generation(driver, prompt_num)

    def _wait_for_generation(self, driver, prompt_num: int) -> str:
        thinking_appeared = False
        thinking_start    = None
        for _ in range(10):
            try:
                els = driver.find_elements(By.CSS_SELECTOR, "div.thinking-message")
                if any(el.is_displayed() for el in els):
                    thinking_appeared = True
                    thinking_start    = time.time()
                    self._log("Thinking...")
                    break
            except Exception:
                pass
            time.sleep(0.5)

        if thinking_appeared and thinking_start:
            time.sleep(2)
            try:
                els = driver.find_elements(By.CSS_SELECTOR, "div.thinking-message")
                thinking_gone = not any(el.is_displayed() for el in els)
                elapsed       = time.time() - thinking_start
                if thinking_gone and elapsed < RATE_LIMIT_THINKING_THRESHOLD:
                    self._log(f"Thinking gone in {elapsed:.1f}s - RATE LIMIT!")
                    return "rate_limit"
            except Exception:
                pass

        self._log("Waiting for thinking to complete...")
        self._wait_gone(driver, "div.thinking-message", timeout=120)
        self._log("Thinking completed. Waiting for video render...")

        start = time.time()
        while time.time() - start < VIDEO_GEN_TIMEOUT:
            if self._cancelled:
                return "error"
            elapsed = int(time.time() - start)

            try:
                src = driver.page_source.lower()

                if any(k in src for k in [
                    "rate limit", "quota exceeded", "try again later", "too many requests"
                ]):
                    self._log("Rate limit message on page")
                    return "rate_limit"

                dl_btns = driver.find_elements(
                    By.CSS_SELECTOR,
                    "button#button[aria-label='Download video file']"
                )
                if dl_btns and any(b.is_displayed() for b in dl_btns):
                    break

                dl_btns = driver.find_elements(
                    By.CSS_SELECTOR,
                    "button[aria-label*='Download' i], "
                    "button[aria-label*='download' i], "
                    "a[download]"
                )
                if dl_btns and any(b.is_displayed() for b in dl_btns):
                    break

                if elapsed % 15 == 0 and elapsed > 0:
                    self._log(f"Still rendering... ({elapsed}s)")

            except Exception:
                pass

            time.sleep(POLLING_INTERVAL)
        else:
            self._log("Video generation timeout", "WARNING")
            return "error"

        self._log("Video render complete!")
        return self._download_video(driver, prompt_num)

    def _download_video(self, driver, prompt_num: int) -> str:
        """
        Step 21 - Download video:

        21a: Klik tombol download utama
             EXACT: <button id="button" class="icon-button filled"
                           aria-label="Download video file">

        21b: Tunggu popup konfirmasi muncul, lalu klik tombol konfirmasi
             EXACT: <button id="button" class="button"> (di dalam popup/dialog)
        """
        self._log("Step 21a: Clicking download button...")
        dl_btn = None

        for sel in [
            "button#button[aria-label='Download video file']",
            "button[aria-label='Download video file']",
            "button#button.icon-button[aria-label*='Download' i]",
            "button#button[aria-label*='Download' i]",
            "button.icon-button[aria-label*='Download' i]",
            "button[aria-label*='download' i]",
            "a[download]",
        ]:
            try:
                els = driver.find_elements(By.CSS_SELECTOR, sel)
                for el in els:
                    if el.is_displayed():
                        dl_btn = el
                        self._log(f"Download button found: {sel}")
                        break
                if dl_btn:
                    break
            except Exception:
                pass

        if not dl_btn:
            self._log("Download button not found", "ERROR")
            self._debug_dump(driver, "no_download_btn")
            return "error"

        driver.execute_script(
            "arguments[0].scrollIntoView({block:'center'});", dl_btn)
        time.sleep(0.5)
        self._js_click(driver, dl_btn)
        self._log("Download button clicked")
        time.sleep(random.uniform(1.5, 2.5))

        # Step 21b: Konfirmasi popup
        self._log("Step 21b: Waiting for download confirmation popup...")
        confirm_clicked = False

        POPUP_CONTAINERS = [
            "md-dialog",
            "[role='dialog']",
            "[role='alertdialog']",
            ".dialog",
            ".modal",
            "dialog",
        ]
        popup_el = None
        deadline = time.time() + 5
        while time.time() < deadline and not popup_el:
            for sel in POPUP_CONTAINERS:
                try:
                    els = driver.find_elements(By.CSS_SELECTOR, sel)
                    for el in els:
                        if el.is_displayed():
                            popup_el = el
                            self._log(f"Popup container found: {sel}")
                            break
                    if popup_el:
                        break
                except Exception:
                    pass
            if not popup_el:
                time.sleep(0.3)

        if popup_el:
            for sel in [
                "button#button.button",
                "button#button",
                "button.button",
            ]:
                try:
                    btn = popup_el.find_element(By.CSS_SELECTOR, sel)
                    if btn.is_displayed():
                        self._js_click(driver, btn)
                        self._log(f"Confirmation button clicked in popup: {sel}")
                        confirm_clicked = True
                        break
                except Exception:
                    pass
        else:
            self._log("Popup container not found, searching whole page...", "WARNING")
            for sel in [
                "button#button.button",
                "button#button",
                "button.button",
            ]:
                try:
                    els = driver.find_elements(By.CSS_SELECTOR, sel)
                    for btn in els:
                        aria = (btn.get_attribute("aria-label") or "").lower()
                        cls  = (btn.get_attribute("class") or "").lower()
                        if "icon-button" in cls or "download" in aria:
                            continue
                        if btn.is_displayed():
                            self._js_click(driver, btn)
                            self._log(f"Confirmation button clicked (fallback): {sel}")
                            confirm_clicked = True
                            break
                    if confirm_clicked:
                        break
                except Exception:
                    pass

        if not confirm_clicked:
            self._log("No confirmation popup - download may proceed directly", "WARNING")

        time.sleep(random.uniform(1, 2))

        self._log("Waiting for video file to appear...")
        for _ in range(120):
            time.sleep(1)
            try:
                files = [
                    f for f in os.listdir(self.output_dir)
                    if f.lower().endswith((".mp4", ".webm"))
                    and not f.endswith(".crdownload")
                    and not f.endswith(".tmp")
                ]
            except Exception:
                files = []

            if files:
                newest = max(
                    [os.path.join(self.output_dir, f) for f in files],
                    key=os.path.getmtime
                )
                fname = (
                    f"ReenzAuto_G-Business_{prompt_num}_"
                    f"{int(time.time() * 1000)}.mp4"
                )
                dest = os.path.join(self.output_dir, fname)
                try:
                    if newest != dest:
                        os.rename(newest, dest)
                    newest = dest
                except Exception:
                    pass
                self._log(f"Video saved: {os.path.basename(newest)}")
                self._log(f"Successfully processed prompt {prompt_num}")
                return "ok"

        self._log("File did not appear after 120s", "WARNING")
        self._debug_dump(driver, "no_file_after_download")
        return "error"
