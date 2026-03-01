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
  Step 6  : Input email ke document.querySelector("#email-input")
  Step 7  : Klik button document.querySelector("#log-in-button > span.UywwFc-RLmnJb")
             -> Jika muncul error page (couldn't sign in / disallowed / access denied)
                navigate ulang ke GEMINI_HOME_URL dan retry submit email
  Step 8  : Tunggu halaman OTP load - kembali ke tab mailticking
  Step 9  : Reload mailticking - klik document.querySelector("#message-list > tr.unread > td.col-6 > a")
  Step 10 : Tunggu verification code muncul - baca document.querySelector("#content-wrapper > table > tbody > tr > td > table > tbody > tr:nth-child(1) > td > table > tbody > tr > td > p.verification-code-container > span")
  Step 11 : Kembali tab Gemini - input OTP ke document.querySelector("#yDmH0d > c-wiz > div > div > div.keerLb > div > div > div > form > div:nth-child(1) > div > div.AFffCd > div > input")
  Step 12 : Klik verify button document.querySelector("#yDmH0d > c-wiz > div > div > div.keerLb > div > div > div > form > div.rPlx0b > div > div:nth-child(1) > span > div.VfPpkd-dgl2Hf-ppHlrf-sM5MNb > button > span.YUhpIc-RLmnJb")
  Step 13 : Tunggu form nama - input ke document.querySelector("#mat-input-0")
  Step 14 : Klik document.querySelector("body > saasfe-root > main > saasfe-onboard-component > div > div > div > form > button > span.mat-mdc-button-touch-target")
  Step 15 : Tunggu h1.title 'Signing you in...' hilang
  Step 16 : Tutup popup dengan shadow DOM path
  Step 17 : Klik tools button dengan shadow DOM path
  Step 18 : Pilih 'Create videos with Veo' dengan shadow DOM path
  Step 19 : Input prompt ke ProseMirror editor dengan shadow DOM path - tekan Enter
  Step 20 : Tunggu thinking-message hilang - tunggu video render
  Step 21 : Download video
    21a: Klik button download dengan shadow DOM path
    21b: Tunggu popup konfirmasi muncul -> klik button konfirmasi dengan shadow DOM path
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

from PySide6.QtCore import QThread, Signal

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
POLLING_INTERVAL      = 3
MAX_ACCOUNT_RETRY     = 3
MAX_TAB_RETRY         = 3
MAX_EMAIL_SUBMIT_RETRY = 3
RATE_LIMIT_THINKING_THRESHOLD = 5.0

EMAIL_SUBMIT_ERROR_KEYWORDS = [
    "couldn't sign you in",
    "couldn't sign in",
    "can't sign you in",
    "disallowed_useragent",
    "access_denied",
    "error 400",
    "error 403",
    "something went wrong",
    "try again",
    "sign-in is not allowed",
    "not supported",
    "browser not supported",
    "let's try something else",
    "try something else",
    "had trouble retrieving",
]

# JavaScript: Step 16 - Dismiss popup 'I'll do this later'
_JS_DISMISS_POPUP = """
return document.querySelector("body > ucs-standalone-app").shadowRoot
    .querySelector("ucs-welcome-dialog").shadowRoot
    .querySelector("div > md-dialog > div:nth-child(3) > md-text-button").shadowRoot
    .querySelector("#button > span.touch");
"""

# JavaScript: Step 17 - Click tools button
_JS_CLICK_TOOLS = """
return document.querySelector("body > ucs-standalone-app").shadowRoot
    .querySelector("div > div.ucs-standalone-outer-row-container > div > ucs-chat-landing").shadowRoot
    .querySelector("div > div > div > div.fixed-content > ucs-search-bar").shadowRoot
    .querySelector("#tool-selector-menu-anchor").shadowRoot
    .querySelector("#button > span.touch");
"""

# JavaScript: Step 18 - Click 'Create videos with Veo'
_JS_CLICK_VEO = """
return document.querySelector("body > ucs-standalone-app").shadowRoot
    .querySelector("div > div.ucs-standalone-outer-row-container > div > ucs-chat-landing").shadowRoot
    .querySelector("div > div > div > div.fixed-content > ucs-search-bar").shadowRoot
    .querySelector("div > form > div > div.actions-buttons.omnibar.multiline-input-actions-buttons > div.tools-button-container > md-menu > div:nth-child(7) > md-menu-item > div");
"""

# JavaScript: Step 19 - Get prompt input element
_JS_GET_PROMPT_INPUT = """
return document.querySelector("body > ucs-standalone-app").shadowRoot
    .querySelector("div > div.ucs-standalone-outer-row-container > div > ucs-chat-landing").shadowRoot
    .querySelector("div > div > div > div.fixed-content > ucs-search-bar").shadowRoot
    .querySelector("#agent-search-prosemirror-editor").shadowRoot
    .querySelector("div > div > div > p");
"""

# JavaScript: Step 20 - Get thinking message element
_JS_GET_THINKING = """
return document.querySelector("body > ucs-standalone-app").shadowRoot
    .querySelector("div > div.ucs-standalone-outer-row-container > div > div.search-bar-and-results-container > div > ucs-results").shadowRoot
    .querySelector("div > div > div.tile.chat-mode-conversation.chat-mode-conversation > div.chat-mode-scroller.tile-content > ucs-conversation").shadowRoot
    .querySelector("div > div.turn.last > ucs-summary").shadowRoot
    .querySelector("div > div > div.summary-contents > div.header.agent-thoughts-header > ucs-agent-thoughts").shadowRoot
    .querySelector("div.header > div.thinking-message");
"""

# JavaScript: Step 21a - Click download button
_JS_CLICK_DOWNLOAD = """
return document.querySelector("body > ucs-standalone-app").shadowRoot
    .querySelector("div > div.ucs-standalone-outer-row-container > div > div.search-bar-and-results-container > div > ucs-results").shadowRoot
    .querySelector("div > div > div.tile.chat-mode-conversation.chat-mode-conversation > div.chat-mode-scroller.tile-content > ucs-conversation").shadowRoot
    .querySelector("div > div > ucs-summary").shadowRoot
    .querySelector("div > div > div.summary-contents > ucs-summary-attachments").shadowRoot
    .querySelector("div > ucs-markdown-video").shadowRoot
    .querySelector("div > div.video-actions > md-filled-icon-button").shadowRoot
    .querySelector("#button > span.touch");
"""

# JavaScript: Step 21b - Click download confirmation
_JS_CLICK_CONFIRM = """
return document.querySelector("body > ucs-standalone-app").shadowRoot
    .querySelector("div > div.ucs-standalone-outer-row-container > div > div.search-bar-and-results-container > div > ucs-results").shadowRoot
    .querySelector("div > div > div.tile.chat-mode-conversation.chat-mode-conversation > div.chat-mode-scroller.tile-content > ucs-conversation").shadowRoot
    .querySelector("div > div > ucs-summary").shadowRoot
    .querySelector("div > div > div.summary-contents > ucs-summary-attachments").shadowRoot
    .querySelector("div > ucs-markdown-video").shadowRoot
    .querySelector("ucs-download-warning-dialog").shadowRoot
    .querySelector("md-dialog > div:nth-child(3) > md-text-button.action-button").shadowRoot
    .querySelector("#button > span.touch");
"""

# JavaScript: Get attachment status/error text inside shadow DOM
_JS_GET_ATTACHMENT_STATUS = """
try {
    var span = document.querySelector("body > ucs-standalone-app").shadowRoot
        .querySelector("div > div.ucs-standalone-outer-row-container > div > div.search-bar-and-results-container > div > ucs-results").shadowRoot
        .querySelector("div > div > div.tile.chat-mode-conversation.chat-mode-conversation > div.chat-mode-scroller.tile-content > ucs-conversation").shadowRoot
        .querySelector("div > div > ucs-summary").shadowRoot
        .querySelector("div > div > div.summary-contents > ucs-summary-attachments").shadowRoot
        .querySelector("div > div > span");
    return span ? span.textContent : null;
} catch(e) {
    return null;
}
"""

# JavaScript: list semua button di shadow DOM untuk debug
_JS_LIST_BUTTONS = """
(function() {
    var result = [];
    function scan(root, depth) {
        if (depth > 10) return;
        var btns = root.querySelectorAll('button, gds-button, gmp-button');
        btns.forEach(function(b) {
            result.push({
                tag: b.tagName,
                id: b.id || '',
                cls: b.getAttribute('class') || '',
                aria: b.getAttribute('aria-label') || '',
                text: (b.innerText || b.textContent || '').trim().substring(0, 80),
                visible: b.offsetParent !== null
            });
        });
        var all = root.querySelectorAll('*');
        all.forEach(function(el) {
            if (el.shadowRoot) scan(el.shadowRoot, depth + 1);
        });
    }
    scan(document, 0);
    return JSON.stringify(result);
})();
"""

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
    return None


class GeminiEnterpriseProcessor(QThread):
    log_signal      = Signal(str, str)
    progress_signal = Signal(int, str)
    finished_signal = Signal(bool, str, str)

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
        super().__init__()
        self.base_dir       = base_dir
        self.prompts        = prompts
        self.output_dir     = output_dir or os.path.join(base_dir, "OUTPUT_GEMINI")
        self.config         = config
        self.log_cb         = log_callback
        self.progress_cb    = progress_callback
        self.finished_cb    = finished_callback
        self.start_index    = start_index
        self._cancelled     = False
        self._mail_client   = MailtickingClient(log_callback=log_callback)
        self.debug_dir      = os.path.join(base_dir, "DEBUG")

    def _log(self, msg, level="INFO"):
        if self.log_cb:
            self.log_cb(msg, level)
        self.log_signal.emit(msg, level)

    def _progress(self, pct, msg):
        if self.progress_cb:
            self.progress_cb(pct, msg)
        self.progress_signal.emit(pct, msg)

    def _done(self, ok, msg, path=""):
        if self.finished_cb:
            self.finished_cb(ok, msg, path)
        self.finished_signal.emit(ok, msg, path)

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

    # ── Driver setup ───────────────────────────────────────────────────────
    def _create_driver(self) -> tuple[Optional[object], Optional[str]]:
        self._log("Setting up fresh Chrome browser...")
        cd_path = _setup_chromedriver(self.base_dir, self._log)
        temp_profile = tempfile.mkdtemp(prefix="gemini_profile_")
        self._log(f"Using fresh browser profile: {temp_profile}")

        headless = self.config.get("headless", False)
        opts = Options()
        opts.add_argument(f"--user-data-dir={temp_profile}")
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

            if stealth and self.config.get("stealth", True):
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
            return driver, temp_profile
        except Exception as e:
            self._log(f"Failed to create Chrome driver: {e}", "ERROR")
            return None, None

    def _quit_driver(self, driver, temp_profile):
        try:
            if driver:
                driver.quit()
        except Exception:
            pass
        if temp_profile and os.path.exists(temp_profile):
            shutil.rmtree(temp_profile, ignore_errors=True)

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

    def _wait_page_ready(self, driver, timeout=30, extra_selector=None, label=""):
        """Wait until document.readyState == 'complete', network idle, and optionally for an extra element."""
        tag = f" [{label}]" if label else ""
        try:
            WebDriverWait(driver, timeout).until(
                lambda d: d.execute_script("return document.readyState") == "complete"
            )
        except TimeoutException:
            self._log(f"Page readyState timeout{tag} ({timeout}s)", "WARNING")
        # Wait for network to settle (no pending XHR/fetch)
        try:
            for _ in range(min(timeout, 15)):
                pending = driver.execute_script(
                    "try { return (window.performance.getEntriesByType('resource')"
                    ".filter(r => !r.responseEnd).length) } catch(e) { return 0; }"
                )
                if pending == 0:
                    break
                time.sleep(1)
        except Exception:
            pass
        # Wait a tiny bit more for lazy-loaded JS to render
        time.sleep(0.5)
        if extra_selector:
            el = self._wait_visible(driver, extra_selector, timeout=min(timeout, 20))
            if not el:
                self._log(f"Extra element '{extra_selector}' not found{tag}", "WARNING")
        self._log(f"Page ready{tag}")

    def _close_extra_tabs(self, driver):
        """Close all tabs except the first one and switch to it."""
        try:
            handles = driver.window_handles
            if len(handles) > 1:
                main = handles[0]
                for h in handles[1:]:
                    try:
                        driver.switch_to.window(h)
                        driver.close()
                    except Exception:
                        pass
                driver.switch_to.window(main)
                self._log(f"Closed {len(handles) - 1} extra tab(s)")
        except Exception as e:
            self._log(f"Error closing tabs: {e}", "WARNING")

    def _verified_type(self, driver, element, text: str, field_name="field") -> bool:
        """Type text into an element and VERIFY it was actually entered."""
        for attempt in range(3):
            try:
                # Clear first
                element.click()
                time.sleep(0.1)
                driver.execute_script(
                    "arguments[0].value = '';"
                    "arguments[0].value = arguments[1];"
                    "arguments[0].dispatchEvent(new Event('input', {bubbles:true}));"
                    "arguments[0].dispatchEvent(new Event('change', {bubbles:true}));",
                    element, text
                )
                time.sleep(0.3)
                # Verify
                actual = driver.execute_script(
                    "return arguments[0].value;", element
                ) or ""
                if actual.strip() == text.strip():
                    self._log(f"{field_name} verified OK: '{text}'")
                    return True
                # Fallback: use send_keys
                self._log(f"{field_name} mismatch (got '{actual}'), retrying with send_keys...", "WARNING")
                element.clear()
                time.sleep(0.1)
                element.send_keys(text)
                time.sleep(0.3)
                actual2 = driver.execute_script(
                    "return arguments[0].value;", element
                ) or ""
                if actual2.strip() == text.strip():
                    self._log(f"{field_name} verified OK (send_keys): '{text}'")
                    return True
                self._log(f"{field_name} still mismatch: expected '{text}', got '{actual2}'", "WARNING")
            except Exception as e:
                self._log(f"{field_name} input error (attempt {attempt+1}): {e}", "WARNING")
            time.sleep(0.5)
        self._log(f"Failed to verify {field_name} input after 3 attempts!", "ERROR")
        return False

    def _validate_step(self, driver, step_name: str, success_indicators: list,
                       failure_indicators: list = None, timeout: int = 10) -> bool:
        """Validate a step by checking page source/URL for success or failure indicators."""
        self._wait_page_ready(driver, timeout=timeout, label=f"Validate: {step_name}")
        for check in range(3):
            try:
                src = driver.page_source.lower()
                url = driver.current_url.lower()
                combined = src + " " + url
                # Check for failure first
                if failure_indicators:
                    if any(k in combined for k in failure_indicators):
                        self._log(f"STEP VALIDATION FAILED [{step_name}]: failure indicator found", "WARNING")
                        self._debug_dump(driver, f"validate_fail_{step_name}")
                        return False
                # Check for success
                if any(k in combined for k in success_indicators):
                    self._log(f"STEP VALIDATED [{step_name}]: OK ✓")
                    return True
                if check < 2:
                    time.sleep(2)
            except Exception as e:
                self._log(f"Validation error [{step_name}]: {e}", "WARNING")
                time.sleep(2)
        self._log(f"STEP VALIDATION [{step_name}]: indicators not found, proceeding cautiously", "WARNING")
        self._debug_dump(driver, f"validate_uncertain_{step_name}")
        return True  # proceed cautiously

    def _fast_type(self, driver, element, text: str):
        """Fast input via JS — for email, OTP, name fields."""
        try:
            element.click()
            time.sleep(0.1)
            driver.execute_script(
                "arguments[0].value = '';"
                "arguments[0].value = arguments[1];"
                "arguments[0].dispatchEvent(new Event('input', {bubbles:true}));"
                "arguments[0].dispatchEvent(new Event('change', {bubbles:true}));",
                element, text
            )
            time.sleep(0.15)
        except Exception:
            # Fallback to human_type if JS fails
            self._human_type(driver, element, text)

    def _human_type(self, driver, element, text: str):
        element.click()
        time.sleep(random.uniform(0.1, 0.2))
        element.clear()
        time.sleep(0.1)
        ac = ActionChains(driver)
        for char in text:
            ac.send_keys(char)
            ac.pause(random.uniform(0.03, 0.08))
        ac.perform()
        time.sleep(random.uniform(0.1, 0.3))

    def _human_click(self, driver, element):
        try:
            ActionChains(driver).move_to_element(element).pause(
                random.uniform(0.05, 0.15)).click().perform()
        except Exception:
            element.click()

    def _is_error_page(self, driver) -> bool:
        try:
            src = driver.page_source.lower()
            url = driver.current_url.lower()
            if any(k in src for k in EMAIL_SUBMIT_ERROR_KEYWORDS):
                return True
            if any(k in url for k in [
                "error=", "disallowed", "access_denied",
                "authError", "servicerestricted"
            ]):
                return True
        except Exception:
            pass
        return False

    def _navigate_to_gemini_home(self, driver):
        self._log(f"Navigating to {GEMINI_HOME_URL} ...")
        try:
            driver.get(GEMINI_HOME_URL)
            WebDriverWait(driver, 20).until(
                lambda d: d.current_url != "about:blank")
        except Exception:
            pass
        self._wait_page_ready(driver, timeout=30, extra_selector="#email-input", label="Gemini Home")

    # ── Main run ─────────────────────────────────────────────────────
    def run(self):
        os.makedirs(self.output_dir, exist_ok=True)
        total = len(self.prompts)
        delay = int(self.config.get("delay", 5))
        retries = int(self.config.get("retry", 1))
        max_workers = int(self.config.get("max_workers", 1))

        self._log("--- STARTING AUTOMATION ---")
        self._log(f"Total prompts: {total} | Max Workers: {max_workers}")
        self._log(f"Settings: delay {delay}s, retry {retries}x")

        self._completed_lock = threading.Lock()
        self._completed_count = self.start_index
        
        from concurrent.futures import ThreadPoolExecutor
        import math

        todos = self.prompts[self.start_index:]
        if not todos:
            self._done(True, "All prompts already processed.")
            return

        # Chunk the prompts evenly based on number of workers
        if max_workers <= 1:
            chunks = [todos]
        else:
            chunk_size = math.ceil(len(todos) / max_workers)
            chunks = [todos[i:i + chunk_size] for i in range(0, len(todos), chunk_size)]

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = []
            curr_global_idx = self.start_index
            for w_idx, chunk in enumerate(chunks, 1):
                futures.append(executor.submit(self._worker_run, w_idx, chunk, curr_global_idx, total))
                curr_global_idx += len(chunk)
                # FIX: 10-second delay between each worker start
                if w_idx < len(chunks):
                    self._log(f"Waiting 10s before starting Worker {w_idx + 1}...")
                    time.sleep(10)

            # Wait for all workers to finish
            for f in futures:
                try:
                    f.result()
                except Exception as e:
                    self._log(f"Worker crashed: {e}", "ERROR")

        if not self._cancelled:
            self._log("All workers finished!")
            self._done(True, f"Done! {self._completed_count} prompts processed.")
        else:
            self._done(False, "Cancelled.")

    def _worker_run(self, worker_id: int, chunk: list, start_global_idx: int, total_prompts: int):
        self._log(f"[W-{worker_id}] Started processing {len(chunk)} prompts")
        delay   = int(self.config.get("delay", 5))
        retries = int(self.config.get("retry",  1))
        
        current_idx = 0
        re_enter_prompt = None
        
        while current_idx < len(chunk) and not self._cancelled:
            driver, temp_profile = self._create_driver()
            if driver is None:
                self._log(f"[W-{worker_id}] Failed to create browser.", "ERROR")
                return

            ok = self._register_account(driver, worker_id)
            if not ok:
                self._quit_driver(driver, temp_profile)
                self._log(f"[W-{worker_id}] Account registration failed.", "ERROR")
                return

            rate_limited = False
            gen_retries  = {}

            while current_idx < len(chunk) and not self._cancelled:
                prompt = re_enter_prompt or chunk[current_idx]
                re_enter_prompt = None
                prompt_num = start_global_idx + current_idx + 1

                self._log(f"[W-{worker_id}] --- Processing Prompt {prompt_num}/{total_prompts} ---")

                result = self._process_prompt(driver, prompt, prompt_num, total_prompts, delay)

                if result == "rate_limit":
                    self._log(f"[W-{worker_id}] Rate limit detected - switching account...")
                    rate_limited    = True
                    re_enter_prompt = prompt
                    break
                elif result == "ok":
                    gen_retries.pop(current_idx, None)
                    current_idx += 1
                    
                    # Update global progress safely
                    with self._completed_lock:
                        self._completed_count += 1
                        pct = int((self._completed_count / total_prompts) * 100)
                        self._progress(pct, f"Processed {self._completed_count}/{total_prompts} prompts")
                    
                    if current_idx < len(chunk):
                        time.sleep(delay)
                else:
                    count = gen_retries.get(current_idx, 0) + 1
                    gen_retries[current_idx] = count
                    if count < retries:
                        self._log(
                            f"[W-{worker_id}] Prompt {prompt_num} failed (attempt {count}/{retries}), "
                            f"retrying after {delay}s...", "WARNING"
                        )
                        time.sleep(delay)
                        try:
                            driver.get(GEMINI_HOME_URL)
                            self._wait_page_ready(driver, timeout=20, label="Worker Retry Nav")
                            self._initial_setup(driver)
                        except Exception:
                            pass
                        re_enter_prompt = prompt
                    else:
                        self._log(f"[W-{worker_id}] Skipping prompt {prompt_num} after {count} failed attempts", "WARNING")
                        gen_retries.pop(current_idx, None)
                        current_idx += 1
                        with self._completed_lock:
                            self._completed_count += 1

            self._quit_driver(driver, temp_profile)
            if rate_limited:
                time.sleep(5)

    # ── Account registration ──────────────────────────────────────────────
    def _register_account(self, driver, worker_id=0) -> bool:
        for retry in range(1, MAX_ACCOUNT_RETRY + 1):
            self._log(f"[W-{worker_id}] --- ACCOUNT REGISTRATION (Attempt {retry}/{MAX_ACCOUNT_RETRY}) ---")
            # FIX 1: Close all extra tabs before each retry
            if retry > 1:
                self._close_extra_tabs(driver)
            ok = self._register_once(driver, worker_id)
            if ok:
                return True
            self._log(f"[W-{worker_id}] Attempt {retry} failed, retrying...", "WARNING")
            time.sleep(3)
        return False

    def _register_once(self, driver, worker_id=0) -> bool:
        self._log(f"[W-{worker_id}] Step 1: Getting fresh temp email from mailticking.com")
        mail_tab = self._mail_client.open_mailticking_tab(driver)
        email = self._mail_client.get_fresh_email(driver)
        if not email or "@" not in email:
            self._log("Failed to get temp email", "ERROR")
            return False
        self._log(f"Temp email: {email}")

        self._log("Step 2: Opening Gemini Business in new tab")
        for tab_try in range(1, MAX_TAB_RETRY + 1):
            try:
                driver.execute_script("window.open('about:blank', '_blank');")
                time.sleep(0.5)
                if len(driver.window_handles) > 1:
                    driver.switch_to.window(driver.window_handles[-1])
                    gemini_tab = driver.current_window_handle
                    break
                raise Exception("Tab not opened")
            except Exception:
                self._log(f"Tab open failed ({tab_try}/{MAX_TAB_RETRY})", "WARNING")
                time.sleep(2)
        else:
            self._log("Failed to open new tab", "ERROR")
            return False

        self._log("Step 3: Entering email and submitting (with error page retry)")
        submitted = self._submit_email_with_retry(driver, email)
        if not submitted:
            self._log("Failed to submit email after all retries", "ERROR")
            return False

        # Step 5: Verify OTP page actually loaded
        self._log("Step 5: Waiting for OTP page to load...")
        self._wait_page_ready(driver, timeout=20, label="OTP Page")
        otp_page_ok = False
        for otp_check in range(3):
            try:
                src = driver.page_source.lower()
                url = driver.current_url.lower()
                if any(k in src for k in ["verification", "verify", "code", "pin", "otp"]):
                    otp_page_ok = True
                    break
                if any(k in url for k in ["verify", "otp", "challenge"]):
                    otp_page_ok = True
                    break
                if self._is_error_page(driver):
                    self._log(f"Error page on OTP step (check {otp_check+1}/3)", "WARNING")
                    self._debug_dump(driver, f"otp_page_error_{otp_check}")
                    time.sleep(2)
                    continue
                # Page might just be slow loading
                otp_page_ok = True
                break
            except Exception as e:
                self._log(f"OTP page check error: {e}", "WARNING")
                time.sleep(2)
        if not otp_page_ok:
            self._log("OTP page failed to load properly", "ERROR")
            return False
        self._log("OTP page loaded.")

        # Step 6: Check mailticking inbox with error wrapping
        self._log("Step 6: Checking mailticking inbox for verification email")
        found = False
        try:
            found = self._mail_client.wait_for_verification_email(
                driver,
                mail_tab_handle   = mail_tab,
                gemini_tab_handle = gemini_tab,
                timeout           = OTP_TIMEOUT,
            )
        except Exception as e:
            self._log(f"Error checking inbox: {e}", "ERROR")
            self._debug_dump(driver, "inbox_check_error")
        if not found:
            self._log("Verification email not received (timeout)", "ERROR")
            return False

        # Step 7: Extract OTP with retry
        self._log("Step 7: Extracting OTP from email")
        otp = None
        for otp_try in range(1, 4):
            try:
                otp = self._mail_client.extract_verification_code(
                    driver,
                    mail_tab_handle = mail_tab,
                )
                if otp:
                    break
                self._log(f"OTP extraction attempt {otp_try}/3 - not found", "WARNING")
            except Exception as e:
                self._log(f"OTP extraction error (attempt {otp_try}/3): {e}", "WARNING")
            time.sleep(2)
        if not otp:
            self._log("Could not extract OTP after 3 attempts", "ERROR")
            self._debug_dump(driver, "otp_extract_failed")
            return False
        self._log(f"OTP obtained: {otp}")

        # Step 8: Enter OTP with retry
        self._log("Step 8: Entering OTP on Gemini")
        try:
            driver.switch_to.window(gemini_tab)
        except Exception as e:
            self._log(f"Failed to switch to Gemini tab: {e}", "ERROR")
            return False
        self._wait_page_ready(driver, timeout=15, label="Gemini Tab (OTP)")

        otp_submitted = False
        for otp_sub_try in range(1, 4):
            otp_submitted = self._submit_otp(driver, otp)
            if otp_submitted:
                break
            self._log(f"OTP submission attempt {otp_sub_try}/3 failed, retrying...", "WARNING")
            time.sleep(2)
        if not otp_submitted:
            self._log("OTP submission failed after 3 attempts", "ERROR")
            self._debug_dump(driver, "otp_submit_failed")
            return False
        self._log("OTP entered")
        time.sleep(random.uniform(0.3, 0.6))

        # Step 9: Click verify with retry
        self._log("Step 9: Clicking Verify button")
        verify_clicked = False
        for verify_try in range(1, 4):
            verify_clicked = self._click_verify_button(driver)
            if verify_clicked:
                break
            self._log(f"Verify button attempt {verify_try}/3 failed", "WARNING")
            # Check if page already moved past verification
            try:
                src = driver.page_source.lower()
                if any(k in src for k in ["full name", "fullname", "agree", "get started"]):
                    self._log("Page already past verification, continuing...")
                    verify_clicked = True
                    break
            except Exception:
                pass
            time.sleep(2)
        if not verify_clicked:
            self._log("Verify button click failed after retries", "WARNING")
            self._debug_dump(driver, "verify_btn_failed")

        # VALIDATE: Step 9 - check page moved past OTP verification
        if not self._validate_step(driver, "Post-Verify",
                success_indicators=["full name", "fullname", "agree", "get started",
                                    "signing you in", "welcome"],
                failure_indicators=["error", "invalid code", "incorrect", "try again"],
                timeout=30):
            self._log("Step 9 validation: still on OTP page after verify", "ERROR")
            self._debug_dump(driver, "verify_not_progressed")
            return False

        # Step 10: Enter name with retry
        self._log("Step 10: Completing signup - entering name")
        name_entered = False
        for name_try in range(1, 4):
            try:
                name_entered = self._enter_name(driver)
                if name_entered:
                    break
                # Check if page already moved past name entry
                src = driver.page_source.lower()
                if any(k in src for k in ["signing you in", "welcome", "i'll do this later"]):
                    self._log("Page already past name entry, continuing...")
                    name_entered = True
                    break
            except Exception as e:
                self._log(f"Name entry error (attempt {name_try}/3): {e}", "WARNING")
            self._log(f"Name entry attempt {name_try}/3 failed, waiting...", "WARNING")
            time.sleep(3)
        if not name_entered:
            self._log("Name form not found after retries, proceeding...", "WARNING")

        # VALIDATE: Step 10 - check name was accepted
        self._validate_step(driver, "Post-Name",
            success_indicators=["agree", "get started", "signing you in", "welcome"],
            timeout=10)

        # Step 11: Click agree with retry
        self._log("Step 11: Clicking 'Agree & get started'")
        agree_clicked = False
        for agree_try in range(1, 4):
            try:
                agree_clicked = self._click_agree_button(driver)
                if agree_clicked:
                    break
                # Check if page already moved past agree
                src = driver.page_source.lower()
                if any(k in src for k in ["signing you in", "welcome", "i'll do this later"]):
                    self._log("Page already past agree step, continuing...")
                    agree_clicked = True
                    break
            except Exception as e:
                self._log(f"Agree button error (attempt {agree_try}/3): {e}", "WARNING")
            time.sleep(2)
        if not agree_clicked:
            self._log("Agree button not clicked after retries", "WARNING")

        # VALIDATE: Step 11 - check page moved to signing in
        if not self._validate_step(driver, "Post-Agree",
                success_indicators=["signing you in", "welcome", "do this later",
                                    "gemini", "search"],
                failure_indicators=["error", "something went wrong"],
                timeout=30):
            self._log("Step 11 validation: agree step did not progress", "ERROR")
            self._debug_dump(driver, "agree_not_progressed")
            return False

        # Step 12: Wait for signing in with error detection
        self._log("Step 12: Waiting for 'Signing you in...' to disappear")
        sign_in_ok = self._wait_gone(driver, "h1.title", timeout=60)
        if not sign_in_ok:
            # Check if we're actually on the Gemini page already
            try:
                src = driver.page_source.lower()
                url = driver.current_url.lower()
                if "gemini" in url and ("welcome" in src or "search" in src):
                    self._log("Signing in seems complete despite h1.title still present")
                elif self._is_error_page(driver):
                    self._log("Error page during sign-in", "ERROR")
                    self._debug_dump(driver, "signin_error")
                    return False
                else:
                    self._log("Sign-in may have stalled", "WARNING")
                    self._debug_dump(driver, "signin_stalled")
            except Exception:
                pass
        self._log("Signing in completed.")
        self._wait_page_ready(driver, timeout=20, label="Post-SignIn")

        # Step 13: Initial setup with retry
        self._log("Step 13: Initial setup")
        setup_ok = False
        for setup_try in range(1, 4):
            try:
                self._initial_setup(driver)
                setup_ok = True
                break
            except Exception as e:
                self._log(f"Initial setup error (attempt {setup_try}/3): {e}", "WARNING")
                self._debug_dump(driver, f"setup_error_{setup_try}")
                time.sleep(3)
                try:
                    driver.refresh()
                    time.sleep(random.uniform(3, 5))
                except Exception:
                    pass
        if not setup_ok:
            self._log("Initial setup failed after retries", "WARNING")
            return False

        # VALIDATE: Step 13 - check Gemini is ready for prompt input
        self._validate_step(driver, "Post-InitialSetup",
            success_indicators=["veo", "create", "prompt", "search", "prosemirror"],
            timeout=15)
        self._log("Account registration and setup completed successfully!")
        return True

    # ── Submit email with error page retry ───────────────────────────────────────
    def _submit_email_with_retry(self, driver, email: str) -> bool:
        for attempt in range(1, MAX_EMAIL_SUBMIT_RETRY + 1):
            self._log(f"Step 3-4: Submit email attempt {attempt}/{MAX_EMAIL_SUBMIT_RETRY}")
            self._navigate_to_gemini_home(driver)

            # Step 6: Input email menggunakan JS path yang sudah diverifikasi
            email_el = None
            try:
                email_el = driver.execute_script('return document.querySelector("#email-input");')
                if email_el and email_el.is_displayed():
                    self._log("Email input found: #email-input")
                else:
                    email_el = None
            except Exception:
                pass

            if not email_el:
                self._log("Email input not found", "WARNING")
                self._debug_dump(driver, f"no_email_input_attempt{attempt}")
                time.sleep(2)
                continue

            # FIX 4: Use _verified_type to guarantee the text is entered correctly
            if not self._verified_type(driver, email_el, email, field_name="Email"):
                self._log("Email input verification failed!", "ERROR")
                self._debug_dump(driver, f"email_verify_fail_{attempt}")
                continue

            # FIX 2: Cross-check - read back what is actually in the input field
            actual_email = driver.execute_script(
                "return arguments[0].value;", email_el
            ) or ""
            if actual_email.strip().lower() != email.strip().lower():
                self._log(
                    f"EMAIL MISMATCH! Expected: '{email}', Got: '{actual_email}'",
                    "ERROR"
                )
                self._debug_dump(driver, f"email_mismatch_{attempt}")
                continue
            self._log(f"Email cross-check OK: '{actual_email}'")
            time.sleep(random.uniform(0.3, 0.6))

            # Step 7: Klik submit button menggunakan JS path yang sudah diverifikasi
            submit_el = None
            try:
                submit_el = driver.execute_script(
                    'return document.querySelector("#log-in-button > span.UywwFc-RLmnJb");'
                )
                if submit_el and submit_el.is_displayed():
                    self._log("Submit button found: #log-in-button > span.UywwFc-RLmnJb")
            except Exception:
                pass

            if submit_el:
                self._human_click(driver, submit_el)
                self._log("Clicked 'Continue with email'")
            else:
                email_el.send_keys(Keys.RETURN)
                self._log("Pressed Enter to submit email")

            # FIX: Wait for Gemini to ACTUALLY redirect to OTP/verification page
            # The old 'OR' condition passed immediately because readyState was already complete.
            old_url = driver.current_url
            self._log(f"Waiting for Gemini redirect from: {old_url}")
            try:
                # Wait for URL to actually CHANGE (not just readyState)
                WebDriverWait(driver, 45).until(
                    lambda d: d.current_url != old_url
                )
                self._log(f"URL changed to: {driver.current_url}")
            except TimeoutException:
                self._log("URL did not change after 45s — may still be on same page", "WARNING")
                self._debug_dump(driver, "email_redirect_timeout")

            # Now wait for the NEW page to fully load
            self._wait_page_ready(driver, timeout=30, label="OTP/Verification Page")

            # Verify we actually landed on the verification page
            current_url = driver.current_url.lower()
            if any(k in current_url for k in ["verify", "accountverification", "oob-code", "challenge"]):
                self._log(f"Confirmed on verification page: {driver.current_url}")
            else:
                self._log(f"Unexpected page after email submit: {driver.current_url}", "WARNING")
                self._debug_dump(driver, "unexpected_page_after_email")

            if self._is_error_page(driver):
                self._log(
                    f"Error page detected after email submit (attempt {attempt}). "
                    "Navigating back to Gemini home...",
                    "WARNING"
                )
                self._debug_dump(driver, f"email_submit_error_{attempt}")
                if attempt < MAX_EMAIL_SUBMIT_RETRY:
                    time.sleep(random.uniform(2, 3))
                    continue
                else:
                    self._log("All email submit attempts failed due to error page", "ERROR")
                    return False
            else:
                self._log(
                    f"Email submitted successfully on attempt {attempt}, "
                    f"page URL now: {driver.current_url}"
                )
                return True

        return False

    def _submit_otp(self, driver, otp: str) -> bool:
        """
        Enter OTP into Google's 6-box verification page.
        The page has 6 separate <input> boxes, one per character.
        Clicking the first box and typing auto-advances to the next.
        """
        self._log(f"Attempting to enter OTP: {otp} ({len(otp)} chars)")

        # --- Step A: Wait for the OTP page to be ready ---
        self._wait_page_ready(driver, timeout=15, label="OTP Form")

        # --- Step B: Find OTP input boxes ---
        # Google's 6-box OTP page: find all visible input elements in the form
        otp_inputs = []
        for attempt in range(3):
            try:
                # Look for all inputs on the page
                all_inputs = driver.find_elements(By.CSS_SELECTOR, "input")
                otp_inputs = []
                for inp in all_inputs:
                    try:
                        if inp.is_displayed():
                            inp_type = (inp.get_attribute("type") or "").lower()
                            # OTP boxes are typically text, tel, or number
                            if inp_type in ("text", "tel", "number", ""):
                                otp_inputs.append(inp)
                    except Exception:
                        pass
                if otp_inputs:
                    self._log(f"Found {len(otp_inputs)} OTP input box(es)")
                    break
            except Exception as e:
                self._log(f"OTP input search error (attempt {attempt+1}): {e}", "WARNING")
            time.sleep(2)

        if not otp_inputs:
            self._log("No OTP input boxes found on page!", "ERROR")
            self._debug_dump(driver, "otp_boxes_not_found")
            return False

        # --- Step C: Type OTP ---
        for attempt in range(3):
            try:
                if len(otp_inputs) >= len(otp):
                    # MULTI-BOX MODE: 6 separate boxes, type one char per box
                    self._log(f"Multi-box OTP mode: {len(otp_inputs)} boxes for {len(otp)} chars")
                    for i, char in enumerate(otp):
                        box = otp_inputs[i]
                        try:
                            box.click()
                        except Exception:
                            driver.execute_script("arguments[0].focus();", box)
                        time.sleep(0.1)
                        box.clear()
                        box.send_keys(char)
                        time.sleep(random.uniform(0.1, 0.25))
                else:
                    # SINGLE-BOX MODE: one input field for entire code
                    self._log("Single-box OTP mode")
                    box = otp_inputs[0]
                    try:
                        box.click()
                    except Exception:
                        driver.execute_script("arguments[0].focus();", box)
                    time.sleep(0.2)
                    box.clear()
                    time.sleep(0.1)
                    # Select all + delete for thorough clear
                    ActionChains(driver).key_down(Keys.CONTROL).send_keys("a").key_up(Keys.CONTROL).perform()
                    ActionChains(driver).send_keys(Keys.DELETE).perform()
                    time.sleep(0.2)
                    for char in otp:
                        box.send_keys(char)
                        time.sleep(random.uniform(0.05, 0.15))

                time.sleep(0.5)

                # --- Step D: Verify OTP was actually entered ---
                if len(otp_inputs) >= len(otp):
                    # Read each box value
                    entered = ""
                    for i in range(len(otp)):
                        val = (otp_inputs[i].get_attribute("value") or "").strip()
                        entered += val
                    if entered.upper() == otp.upper():
                        self._log(f"OTP VERIFIED across {len(otp)} boxes: '{entered}' ✓")
                        return True
                    self._log(
                        f"OTP verify attempt {attempt+1}/3: expected '{otp}', got '{entered}'",
                        "WARNING"
                    )
                else:
                    actual = (otp_inputs[0].get_attribute("value") or "").strip()
                    if actual.upper() == otp.upper():
                        self._log(f"OTP VERIFIED in single box: '{actual}' ✓")
                        return True
                    self._log(
                        f"OTP verify attempt {attempt+1}/3: expected '{otp}', got '{actual}'",
                        "WARNING"
                    )

                # Before retry, re-find the elements (they may have gone stale)
                time.sleep(1)
                all_inputs = driver.find_elements(By.CSS_SELECTOR, "input")
                otp_inputs = [
                    inp for inp in all_inputs
                    if inp.is_displayed() and
                    (inp.get_attribute("type") or "").lower() in ("text", "tel", "number", "")
                ]
            except Exception as e:
                self._log(f"OTP typing error (attempt {attempt+1}/3): {e}", "WARNING")
                time.sleep(1)

        # --- Step E: Last resort - type via ActionChains on first box ---
        self._log("Falling back to ActionChains on first input...", "WARNING")
        try:
            if otp_inputs:
                otp_inputs[0].click()
                time.sleep(0.2)
            ActionChains(driver).send_keys(otp).perform()
            time.sleep(0.5)
            self._log(f"OTP sent via ActionChains: {otp}")
            return True
        except Exception as e:
            self._log(f"ActionChains OTP failed: {e}", "ERROR")
        return False

    def _click_verify_button(self, driver) -> bool:
        # Step 12: Klik verify button menggunakan JS path yang sudah diverifikasi
        try:
            verify_btn = driver.execute_script(
                'return document.querySelector("#yDmH0d > c-wiz > div > div > div.keerLb > div > div > div > form > div.rPlx0b > div > div:nth-child(1) > span > div.VfPpkd-dgl2Hf-ppHlrf-sM5MNb > button > span.YUhpIc-RLmnJb");'
            )
            if verify_btn and verify_btn.is_displayed():
                self._human_click(driver, verify_btn)
                self._log("Clicked verify button via verified selector")
                return True
        except Exception as e:
            self._log(f"Verify button click error: {e}", "WARNING")

        # Fallback methods
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
                        self._log(f"Clicked verify via fallback: {sel}")
                        return True
            except Exception:
                pass

        for el in driver.find_elements(By.TAG_NAME, "button"):
            try:
                if any(w in el.text.lower() for w in ["verify", "confirm", "continue"])\
                        and el.is_displayed():
                    self._human_click(driver, el)
                    self._log("Clicked verify (text fallback)")
                    return True
            except Exception:
                pass
        return False

    def _enter_name(self, driver) -> bool:
        # Step 13: Input nama menggunakan JS path yang sudah diverifikasi
        name_el = None
        try:
            name_el = driver.execute_script('return document.querySelector("#mat-input-0");')
            if name_el and name_el.is_displayed():
                self._log("Name input found: #mat-input-0")
        except Exception:
            pass

        # Fallback selectors
        if not name_el:
            for sel in [
                "input[formcontrolname='fullName']",
                "input[placeholder='Full name']",
                "input[type='text'][required]",
            ]:
                el = self._wait_for(driver, sel, timeout=10)
                if el and el.is_displayed():
                    name_el = el
                    self._log(f"Name input found via fallback: {sel}")
                    break

        if name_el:
            name = _random_name()
            if self._verified_type(driver, name_el, name, field_name="Name"):
                return True
            # Fallback to _fast_type if _verified_type fails
            self._fast_type(driver, name_el, name)
            self._log(f"Name entered (fallback): {name}")
            time.sleep(0.3)
            return True
        return False

    def _click_agree_button(self, driver) -> bool:
        # Step 14: Klik 'Agree & get started' menggunakan JS path yang sudah diverifikasi
        try:
            agree_btn = driver.execute_script(
                'return document.querySelector("body > saasfe-root > main > saasfe-onboard-component > div > div > div > form > button > span.mat-mdc-button-touch-target");'
            )
            if agree_btn and agree_btn.is_displayed():
                self._human_click(driver, agree_btn)
                self._log("Clicked 'Agree & get started' via verified selector")
                return True
        except Exception as e:
            self._log(f"Agree button click error: {e}", "WARNING")

        # Fallback methods
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
                        self._log("Clicked 'Agree & get started' (fallback)")
                        return True
            except Exception:
                pass
        return False

    def _initial_setup(self, driver):
        # Step 16: Dismiss popup with retry
        self._log("Step 16: Closing 'I'll do this later' popup...")
        dismissed = False
        for dismiss_try in range(1, 4):
            try:
                btn = driver.execute_script(_JS_DISMISS_POPUP)
                if btn:
                    driver.execute_script("arguments[0].click();", btn)
                    self._log("Popup 'I'll do this later' dismissed")
                    dismissed = True
                    break
            except Exception as e:
                if dismiss_try < 3:
                    self._log(f"Dismiss popup attempt {dismiss_try}/3: {e}", "WARNING")
                    time.sleep(2)
                else:
                    self._log(f"Dismiss popup error: {e}", "WARNING")

        if not dismissed:
            self._log("No 'do this later' popup found, proceeding...", "WARNING")
        self._wait_page_ready(driver, timeout=15, label="Post-Dismiss Popup")

        # Step 17: Click tools button with retry
        self._log("Step 17: Clicking tools button (page_info icon)...")
        tools_clicked = False
        for tools_try in range(1, 4):
            try:
                btn = driver.execute_script(_JS_CLICK_TOOLS)
                if btn:
                    driver.execute_script("arguments[0].click();", btn)
                    self._log("Tools button clicked")
                    tools_clicked = True
                    break
            except Exception as e:
                self._log(f"Tools button attempt {tools_try}/3: {e}", "WARNING")
            if tools_try < 3:
                time.sleep(2)
                try:
                    driver.refresh()
                    self._wait_page_ready(driver, timeout=20, label="Tools Refresh")
                except Exception:
                    pass

        if not tools_clicked:
            self._log("Tools button not found after retries", "WARNING")
            self._debug_dump(driver, "tools_btn_not_found")
            return

        self._wait_page_ready(driver, timeout=15, label="Post-Tools Click")

        # Step 18: Click 'Create videos with Veo' with retry
        self._log("Step 18: Selecting 'Create videos with Veo'...")
        veo_clicked = False
        for veo_try in range(1, 4):
            try:
                menu_item = driver.execute_script(_JS_CLICK_VEO)
                if menu_item:
                    driver.execute_script("arguments[0].click();", menu_item)
                    self._log("Clicked 'Create videos with Veo'")
                    veo_clicked = True
                    break
            except Exception as e:
                self._log(f"Veo menu attempt {veo_try}/3: {e}", "WARNING")

            # Fallback: text search
            if not veo_clicked:
                try:
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
                except Exception:
                    pass

            if veo_clicked:
                break
            if veo_try < 3:
                time.sleep(2)
                # Re-click tools button before retry
                try:
                    btn = driver.execute_script(_JS_CLICK_TOOLS)
                    if btn:
                        driver.execute_script("arguments[0].click();", btn)
                        time.sleep(1.5)
                except Exception:
                    pass

        if not veo_clicked:
            self._log("Veo option not found after retries", "WARNING")
            self._debug_dump(driver, "veo_not_found")

        self._wait_page_ready(driver, timeout=15, label="Post-Veo Selection")
        self._log("Initial setup completed!")

    # ── Process single prompt ───────────────────────────────────────────────
    def _process_prompt(
        self, driver, prompt: str, prompt_num: int, total: int, delay: int
    ) -> str:
        if self._gemini_tab:
            try:
                driver.switch_to.window(self._gemini_tab)
            except Exception as e:
                self._log(f"Failed to switch to Gemini tab: {e}", "ERROR")
                return "error"

        self._wait_page_ready(driver, timeout=15, label="Pre-Prompt Input")
        self._progress(int((prompt_num / total) * 100), f"Prompt {prompt_num}/{total}")

        # Step 19: Input prompt with retry for stale elements
        self._log(f"Step 19: Inputting prompt {prompt_num}/{total}")
        typed_ok = False
        for input_try in range(1, 4):
            prompt_el = None
            # Try shadow DOM path first
            try:
                prompt_el = driver.execute_script(_JS_GET_PROMPT_INPUT)
                if prompt_el and prompt_el.is_displayed():
                    self._log("Prompt input found via shadow DOM path")
            except Exception as e:
                self._log(f"Prompt input error: {e}", "WARNING")

            # Fallback selectors
            if not prompt_el:
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
                        self._log(f"Prompt input found via fallback: {sel}")
                        break

            if not prompt_el:
                self._log(f"Prompt input not found (attempt {input_try}/3)", "WARNING")
                self._debug_dump(driver, f"no_prompt_input_{input_try}")
                if input_try < 3:
                    time.sleep(3)
                    continue
                self._log("Prompt input not found after retries", "ERROR")
                return "error"

            try:
                driver.execute_script("arguments[0].click();", prompt_el)
                time.sleep(0.2)
                ActionChains(driver).key_down(Keys.CONTROL).send_keys("a").key_up(
                    Keys.CONTROL).perform()
                time.sleep(0.1)
                ActionChains(driver).send_keys(Keys.DELETE).perform()
                time.sleep(0.1)

                # Clipboard paste via JS insertText (fastest method)
                driver.execute_script(
                    "arguments[0].focus();"
                    "document.execCommand('insertText', false, arguments[1]);",
                    prompt_el, prompt
                )
                # Verify text was inserted
                inserted = driver.execute_script(
                    "return arguments[0].textContent;", prompt_el
                ) or ""
                if prompt[:20] not in inserted:
                    # Fallback: Ctrl+V via pyperclip
                    self._log("insertText failed, fallback to Ctrl+V", "WARNING")
                    try:
                        import pyperclip
                        pyperclip.copy(prompt)
                        ActionChains(driver).key_down(Keys.CONTROL).send_keys(
                            "v").key_up(Keys.CONTROL).perform()
                    except Exception:
                        # Last fallback: chunk typing
                        ac = ActionChains(driver)
                        i = 0
                        while i < len(prompt):
                            chunk = prompt[i:i + random.randint(5, 15)]
                            ac.send_keys(chunk)
                            ac.pause(0.02)
                            i += len(chunk)
                        ac.perform()
                self._log("Prompt entered (paste)")
                typed_ok = True
                break
            except Exception as e:
                self._log(f"Prompt typing error (attempt {input_try}/3): {e}", "WARNING")
                time.sleep(2)

        if not typed_ok:
            self._log("Failed to type prompt after retries", "ERROR")
            return "error"

        time.sleep(random.uniform(0.3, 0.5))

        self._log("Pressing Enter to generate...")
        try:
            ActionChains(driver).send_keys(Keys.RETURN).perform()
        except Exception as e:
            self._log(f"Enter key error: {e}", "WARNING")
            try:
                driver.execute_script(
                    "arguments[0].dispatchEvent(new KeyboardEvent('keydown',"
                    "{key:'Enter',code:'Enter',keyCode:13,bubbles:true}));",
                    prompt_el)
            except Exception:
                pass
        self._log("Generation started")
        self._wait_page_ready(driver, timeout=15, label="Post-Prompt Submit")

        return self._wait_for_generation(driver, prompt_num)

    def _wait_for_generation(self, driver, prompt_num: int) -> str:
        # Step 20: Monitor thinking message menggunakan shadow DOM path
        thinking_appeared = False
        thinking_start    = None
        for check_i in range(20):  # Wait up to ~10s for thinking to appear
            try:
                thinking_el = driver.execute_script(_JS_GET_THINKING)
                if thinking_el and thinking_el.is_displayed():
                    thinking_appeared = True
                    thinking_start    = time.time()
                    self._log("Thinking...")
                    break
            except Exception:
                pass

            # While waiting for thinking, check page for rate limit or error
            if check_i > 0 and check_i % 5 == 0:
                try:
                    src = driver.page_source.lower()
                    if any(k in src for k in [
                        "rate limit", "quota exceeded", "try again later",
                        "too many requests", "usage limit",
                    ]):
                        self._log("Rate limit detected on page (no thinking appeared)", "WARNING")
                        self._debug_dump(driver, f"rate_limit_no_think_{prompt_num}")
                        return "rate_limit"
                    if any(k in src for k in [
                        "failed to load attachment", "failed to load",
                        "something went wrong", "couldn't generate",
                        "unable to generate", "an error occurred",
                    ]):
                        self._log("Error message detected before thinking started", "WARNING")
                        self._debug_dump(driver, f"gen_error_no_think_{prompt_num}")
                        return "error"
                except Exception:
                    pass
            time.sleep(0.5)

        # If thinking never appeared → likely rate limited or page unresponsive
        if not thinking_appeared:
            self._log("Thinking never appeared after prompt submission — checking page state...", "WARNING")
            self._debug_dump(driver, f"no_thinking_{prompt_num}")
            try:
                src = driver.page_source.lower()
                # Check for explicit rate limit indicators
                if any(k in src for k in [
                    "rate limit", "quota exceeded", "try again later",
                    "too many requests", "usage limit",
                ]):
                    self._log("RATE LIMIT: explicit rate limit text found on page")
                    return "rate_limit"
                # Check for error messages
                if any(k in src for k in [
                    "failed to load attachment", "failed to load",
                    "something went wrong", "couldn't generate",
                    "unable to generate", "an error occurred",
                ]):
                    self._log("Generation error detected (no thinking)")
                    return "error"
                # If no thinking and no visible video content, assume rate limit
                # (the page is blank/unresponsive after the prompt)
                has_response = any(k in src for k in [
                    "video", "render", "generat", "attachment", "download",
                ])
                if not has_response:
                    self._log("RATE LIMIT: page is blank/unresponsive after prompt — switching account")
                    return "rate_limit"
            except Exception as e:
                self._log(f"Page check failed: {e}", "WARNING")
                return "rate_limit"

        if thinking_appeared and thinking_start:
            time.sleep(2)
            try:
                thinking_el = driver.execute_script(_JS_GET_THINKING)
                thinking_gone = not (thinking_el and thinking_el.is_displayed())
                elapsed       = time.time() - thinking_start
                if thinking_gone and elapsed < RATE_LIMIT_THINKING_THRESHOLD:
                    self._log(f"Thinking gone in {elapsed:.1f}s - RATE LIMIT!")
                    return "rate_limit"
            except Exception:
                pass

        self._log("Waiting for thinking to complete...")
        # Wait for thinking to complete using shadow DOM
        start = time.time()
        while time.time() - start < 120:
            try:
                thinking_el = driver.execute_script(_JS_GET_THINKING)
                if not (thinking_el and thinking_el.is_displayed()):
                    break
            except Exception:
                break

            # Also check for rate limit during thinking
            if int(time.time() - start) % 15 == 0 and int(time.time() - start) > 0:
                try:
                    src = driver.page_source.lower()
                    if any(k in src for k in [
                        "rate limit", "quota exceeded", "try again later",
                        "too many requests", "usage limit",
                    ]):
                        self._log("Rate limit detected during thinking phase")
                        return "rate_limit"
                except Exception:
                    pass
            time.sleep(0.5)
        
        self._log("Thinking completed. Waiting for video render...")

        start = time.time()
        while time.time() - start < VIDEO_GEN_TIMEOUT:
            if self._cancelled:
                return "error"
            elapsed = int(time.time() - start)

            try:
                # PRIMARY CHECK: Read attachment status from shadow DOM
                # (error messages are INSIDE shadow DOM, invisible to page_source)
                try:
                    attachment_text = driver.execute_script(_JS_GET_ATTACHMENT_STATUS)
                    if attachment_text:
                        att_lower = attachment_text.strip().lower()
                        if any(k in att_lower for k in [
                            "failed to load", "failed", "error",
                            "couldn't generate", "unable to generate",
                            "something went wrong", "try again",
                        ]):
                            self._log(
                                f"SHADOW DOM ERROR: '{attachment_text.strip()}' — "
                                "will retry prompt", "WARNING"
                            )
                            self._debug_dump(driver, f"shadow_dom_error_{prompt_num}")
                            return "error"
                except Exception:
                    pass

                # SECONDARY CHECK: page source (for non-shadow-DOM errors)
                src = driver.page_source.lower()

                if any(k in src for k in [
                    "rate limit", "quota exceeded", "try again later",
                    "too many requests", "usage limit",
                ]):
                    self._log("Rate limit message on page")
                    return "rate_limit"

                # Check for generation failure messages → retry prompt
                if any(k in src for k in [
                    "failed to load attachment",
                    "failed to load",
                    "something went wrong",
                    "couldn't generate",
                    "unable to generate",
                    "content generation error",
                    "an error occurred",
                ]):
                    self._log("Generation failed — will retry prompt", "WARNING")
                    self._debug_dump(driver, f"gen_failed_{prompt_num}")
                    return "error"

                # Check if download button is available via shadow DOM
                try:
                    dl_btn = driver.execute_script(_JS_CLICK_DOWNLOAD)
                    if dl_btn:
                        break
                except Exception:
                    pass

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
        # Step 21a: Click download button with retry
        self._log("Step 21a: Clicking download button...")
        dl_btn = None
        for dl_try in range(1, 4):
            try:
                dl_btn = driver.execute_script(_JS_CLICK_DOWNLOAD)
                if dl_btn:
                    self._log("Download button found")
                    break
            except Exception as e:
                self._log(f"Download button attempt {dl_try}/3: {e}", "WARNING")
            time.sleep(2)

        if not dl_btn:
            self._log("Download button not found after retries", "ERROR")
            self._debug_dump(driver, "no_download_btn")
            return "error"

        try:
            driver.execute_script(
                "arguments[0].scrollIntoView({block:'center'});", dl_btn)
            time.sleep(0.5)
            self._js_click(driver, dl_btn)
            self._log("Download button clicked")
        except Exception as e:
            self._log(f"Download button click error: {e}", "WARNING")
            # Retry click
            try:
                dl_btn = driver.execute_script(_JS_CLICK_DOWNLOAD)
                if dl_btn:
                    self._js_click(driver, dl_btn)
                    self._log("Download button clicked (retry)")
            except Exception:
                self._log("Download button click failed", "ERROR")
                return "error"
        time.sleep(random.uniform(1.5, 2.5))

        # Step 21b: Click confirmation with retry
        self._log("Step 21b: Waiting for download confirmation popup...")
        confirm_clicked = False
        for conf_try in range(1, 4):
            try:
                confirm_btn = driver.execute_script(_JS_CLICK_CONFIRM)
                if confirm_btn:
                    self._js_click(driver, confirm_btn)
                    self._log("Confirmation button clicked")
                    confirm_clicked = True
                    break
            except Exception as e:
                if conf_try < 3:
                    self._log(f"Confirmation attempt {conf_try}/3: {e}", "WARNING")
                    time.sleep(1.5)
                else:
                    self._log(f"Confirmation button error: {e}", "WARNING")

        if not confirm_clicked:
            self._log("No confirmation popup - download may proceed directly", "WARNING")

        time.sleep(random.uniform(1, 2))

        # Wait for file with progress logging
        self._log("Waiting for video file to appear...")
        last_log_time = time.time()
        for wait_sec in range(120):
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

            # Log download progress (crdownload files indicate active download)
            if time.time() - last_log_time > 15:
                try:
                    downloading = [
                        f for f in os.listdir(self.output_dir)
                        if f.endswith(".crdownload")
                    ]
                    if downloading:
                        self._log(f"Download in progress... ({wait_sec}s)")
                    else:
                        self._log(f"Waiting for download to start... ({wait_sec}s)")
                except Exception:
                    pass
                last_log_time = time.time()

        self._log("File did not appear after 120s", "WARNING")
        self._debug_dump(driver, "no_file_after_download")
        return "error"

