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
             -> Jika muncul error page (couldn't sign in / disallowed / access denied)
                navigate ulang ke GEMINI_HOME_URL dan retry submit email
  Step 8  : Tunggu halaman OTP load - kembali ke tab mailticking
  Step 9  : Reload mailticking - klik a[href*='/mail/view/'] (Gemini email)
  Step 10 : Tunggu span.verification-code muncul - baca OTP
  Step 11 : Kembali tab Gemini - input OTP ke input.J6L5wc
  Step 12 : Klik verify button
  Step 13 : Tunggu form nama - input ke input[formcontrolname="fullName"]
  Step 14 : Klik span.mdc-button__label 'Agree & get started'
  Step 15 : Tunggu h1.title 'Signing you in...' hilang
  Step 16 : Tutup popup 'I'll do this later'
             -> Web Component Shadow DOM: pakai JS rekursif shadowRoot traversal
  Step 17 : Klik tools button (md-icon: page_info)
             -> Priority 0: exact path ucs-standalone-app > ucs-chat-landing >
                ucs-search-bar > #tool-selector-menu-anchor > #button
             -> Fallback: JS rekursif shadowRoot traversal
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
]

# JavaScript: rekursif traversal semua shadow root untuk cari button 'I'll do this later'
# Mencari button yang:
#   - id="button" atau class mengandung "button"
#   - BUKAN icon-button / download button
#   - Teks di dalam shadow slot mengandung 'later' / 'skip' / 'dismiss' / 'not now'
#   - Atau: parent custom element mengandung teks tersebut di outerHTML
_JS_FIND_DISMISS_BTN = """
(function() {
    var KEYWORDS = ['later', 'skip', 'dismiss', 'not now', 'no thanks'];
    var SKIP_ARIA = ['download', 'close', 'menu', 'search'];

    function textOf(el) {
        // Gabungkan innerText + semua slot children innerText
        var t = (el.innerText || el.textContent || '').toLowerCase().trim();
        if (!t && el.shadowRoot) {
            var slots = el.shadowRoot.querySelectorAll('slot');
            slots.forEach(function(slot) {
                var assigned = slot.assignedNodes ? slot.assignedNodes({flatten:true}) : [];
                assigned.forEach(function(node) {
                    t += (node.textContent || '').toLowerCase();
                });
            });
        }
        return t;
    }

    function hasKeyword(txt) {
        return KEYWORDS.some(function(k) { return txt.indexOf(k) !== -1; });
    }

    function isSkip(el) {
        var aria = (el.getAttribute('aria-label') || '').toLowerCase();
        var cls  = (el.getAttribute('class') || '').toLowerCase();
        return SKIP_ARIA.some(function(k) { return aria.indexOf(k) !== -1; })
            || cls.indexOf('icon-button') !== -1;
    }

    function findInRoot(root) {
        // Cari semua button candidate
        var candidates = root.querySelectorAll(
            'button#button, button.button, [id="button"], gds-button, gmp-button'
        );
        for (var i = 0; i < candidates.length; i++) {
            var el = candidates[i];
            if (isSkip(el)) continue;

            // Cek teks el itu sendiri
            var t = textOf(el);
            if (hasKeyword(t)) return el;

            // Cek outerHTML parent custom element (bisa jadi teks ada di light DOM)
            var parent = el.parentElement;
            while (parent && parent !== document.body) {
                var pt = (parent.outerHTML || '').toLowerCase();
                if (hasKeyword(pt) && !isSkip(el)) return el;
                // Hanya naik 3 level
                if (parent.parentElement === parent) break;
                parent = parent.parentElement;
            }
        }

        // Rekursif ke shadow roots
        var all = root.querySelectorAll('*');
        for (var j = 0; j < all.length; j++) {
            if (all[j].shadowRoot) {
                var found = findInRoot(all[j].shadowRoot);
                if (found) return found;
            }
        }
        return null;
    }

    return findInRoot(document);
})();
"""

# JavaScript: cari semua button di shadow DOM, kembalikan array info
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

# JavaScript: cari tools button (page_info icon) di shadow DOM
#
# Prioritas 0: Exact path yang diketahui dari inspect element
#   body > ucs-standalone-app
#     .shadowRoot > ucs-chat-landing
#     .shadowRoot > ucs-search-bar
#     .shadowRoot > #tool-selector-menu-anchor
#     .shadowRoot > #button
#
# Fallback: Recursive shadow DOM traversal mencari:
#   - md-icon dengan text 'page_info' -> ancestor md-icon-button/button
#   - md-icon-button / button dengan aria-label/title mengandung
#     'tool', 'gem', 'extension', 'plugin', 'app'
_JS_FIND_TOOLS_BTN = """
(function() {
    // ── Priority 0: Exact shadow DOM path ──────────────────────────────────
    try {
        var btn = document
            .querySelector("body > ucs-standalone-app").shadowRoot
            .querySelector("div > div.ucs-standalone-outer-row-container > div > ucs-chat-landing").shadowRoot
            .querySelector("div > div > div > div.fixed-content > ucs-search-bar").shadowRoot
            .querySelector("#tool-selector-menu-anchor").shadowRoot
            .querySelector("#button");
        if (btn) return btn;
    } catch(e) {}

    // ── Fallback: Recursive shadow DOM traversal ───────────────────────────
    var ARIA_KEYWORDS = ['tool', 'gem', 'extension', 'plugin', 'app'];

    function hasToolAria(el) {
        var aria  = (el.getAttribute('aria-label') || '').toLowerCase();
        var title = (el.getAttribute('title') || '').toLowerCase();
        return ARIA_KEYWORDS.some(function(k) {
            return aria.indexOf(k) !== -1 || title.indexOf(k) !== -1;
        });
    }

    function findInRoot(root, depth) {
        if (depth > 10) return null;

        // Prioritas 1: md-icon dengan text 'page_info' -> ambil ancestor button-nya
        var icons = root.querySelectorAll('md-icon');
        for (var k = 0; k < icons.length; k++) {
            if ((icons[k].textContent || '').trim() === 'page_info') {
                var parent = icons[k].parentElement;
                for (var up = 0; up < 5; up++) {
                    if (!parent) break;
                    var tag = parent.tagName.toLowerCase();
                    if (tag === 'md-icon-button' || tag === 'button') return parent;
                    parent = parent.parentElement;
                }
                return icons[k];
            }
        }

        // Prioritas 2: md-icon-button atau button dengan aria-label/title tool-related
        var candidates = root.querySelectorAll('md-icon-button, button');
        for (var i = 0; i < candidates.length; i++) {
            if (hasToolAria(candidates[i])) return candidates[i];
        }

        // Rekursif ke shadow roots
        var all = root.querySelectorAll('*');
        for (var j = 0; j < all.length; j++) {
            if (all[j].shadowRoot) {
                var found = findInRoot(all[j].shadowRoot, depth + 1);
                if (found) return found;
            }
        }
        return null;
    }

    return findInRoot(document, 0);
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

    # ── Driver setup ───────────────────────────────────────────────────────
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
        time.sleep(random.uniform(2, 3))
        self._log("Gemini Business page loaded.")

    # ── Main run ─────────────────────────────────────────────────────
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

    # ── Account registration ──────────────────────────────────────────────
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

        self._log("Step 3: Entering email and submitting (with error page retry)")
        submitted = self._submit_email_with_retry(driver, email)
        if not submitted:
            self._log("Failed to submit email after all retries", "ERROR")
            return False

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

    # ── Submit email with error page retry ───────────────────────────────────────
    def _submit_email_with_retry(self, driver, email: str) -> bool:
        EMAIL_SELECTORS = [
            "input#email-input",
            "input[jsname='YPqjbf']",
            "input[name='loginHint']",
            "input[type='email']",
            "input[type='text']",
        ]
        SUBMIT_SELECTORS = [
            "button#log-in-button",
            "button[aria-label='Continue with email']",
            "button[jsname='jXw9Fb']",
            "button[type='submit']",
        ]

        for attempt in range(1, MAX_EMAIL_SUBMIT_RETRY + 1):
            self._log(f"Step 3-4: Submit email attempt {attempt}/{MAX_EMAIL_SUBMIT_RETRY}")
            self._navigate_to_gemini_home(driver)

            email_el = None
            for sel in EMAIL_SELECTORS:
                el = self._wait_for(driver, sel, timeout=15)
                if el and el.is_displayed():
                    email_el = el
                    self._log(f"Email input found: {sel}")
                    break

            if not email_el:
                self._log("Email input not found", "WARNING")
                self._debug_dump(driver, f"no_email_input_attempt{attempt}")
                time.sleep(2)
                continue

            self._human_type(driver, email_el, email)
            self._log(f"Email entered: {email}")
            time.sleep(random.uniform(0.8, 1.5))

            submit_el = None
            for sel in SUBMIT_SELECTORS:
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

            time.sleep(random.uniform(3, 5))

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
                    "OTP page should be loading..."
                )
                return True

        return False

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
        self._log("Step 16: Closing 'I'll do this later' popup...")
        dismissed = self._dismiss_later_popup(driver)
        if dismissed:
            self._log("Popup 'I'll do this later' dismissed.")
        else:
            self._log("No 'do this later' popup found, proceeding...", "WARNING")
        time.sleep(random.uniform(1, 2))

        self._log("Step 17: Clicking tools button (page_info icon)...")
        tools_clicked = False

        # Strategy 1: JS shadow DOM traversal (Priority 0 = exact path, then recursive)
        try:
            btn = driver.execute_script(_JS_FIND_TOOLS_BTN)
            if btn:
                driver.execute_script("arguments[0].click();", btn)
                self._log("Tools button clicked via shadow DOM JS traversal")
                tools_clicked = True
        except Exception as e:
            self._log(f"Tools button JS traversal error: {e}", "WARNING")

        # Strategy 2: CSS selectors with getBoundingClientRect visibility check
        # (is_displayed() returns False for custom elements even when visible)
        if not tools_clicked:
            for sel in [
                "md-icon-button[aria-label*='tool' i]",
                "md-icon-button[aria-label*='gem' i]",
                "md-icon-button[aria-label*='extension' i]",
                "md-icon-button[aria-label*='app' i]",
                "button[aria-label*='tool' i]",
                "[slot='icon-button']",
            ]:
                try:
                    els = driver.find_elements(By.CSS_SELECTOR, sel)
                    for el in els:
                        try:
                            visible = el.is_displayed() or driver.execute_script(
                                "return arguments[0].getBoundingClientRect().width > 0;", el)
                            if visible:
                                driver.execute_script("arguments[0].click();", el)
                                self._log(f"Tools button clicked: {sel}")
                                tools_clicked = True
                                break
                        except Exception:
                            pass
                    if tools_clicked:
                        break
                except Exception:
                    pass

        # Strategy 3: light-DOM md-icon page_info fallback
        if not tools_clicked:
            try:
                icons = driver.find_elements(By.TAG_NAME, "md-icon")
                for icon in icons:
                    if "page_info" in (icon.text or "").strip():
                        try:
                            btn = icon.find_element(
                                By.XPATH, "./ancestor::button | ./ancestor::md-icon-button")
                            driver.execute_script("arguments[0].click();", btn)
                            self._log("Clicked tools button via md-icon page_info")
                            tools_clicked = True
                        except Exception:
                            driver.execute_script("arguments[0].click();", icon)
                            tools_clicked = True
                        break
            except Exception:
                pass

        if not tools_clicked:
            self._log("Tools button not found - running debug scan...", "WARNING")
            # Debug: log semua md-icon-button visible di shadow DOM untuk analisis
            try:
                raw = driver.execute_script("""
                (function() {
                    var result = [];
                    function scan(root, depth) {
                        if (depth > 8) return;
                        var btns = root.querySelectorAll('md-icon-button, button[aria-label]');
                        btns.forEach(function(b) {
                            var rect = b.getBoundingClientRect();
                            if (rect.width > 0) {
                                result.push({
                                    tag: b.tagName,
                                    aria: b.getAttribute('aria-label') || '',
                                    title: b.getAttribute('title') || '',
                                    text: (b.textContent || '').trim().substring(0, 50)
                                });
                            }
                        });
                        root.querySelectorAll('*').forEach(function(el) {
                            if (el.shadowRoot) scan(el.shadowRoot, depth + 1);
                        });
                    }
                    scan(document, 0);
                    return JSON.stringify(result);
                })();
                """)
                btns_info = json.loads(raw) if raw else []
                for info in btns_info:
                    self._log(
                        f"  [ICON-BTN] tag={info['tag']} aria='{info['aria'][:50]}' "
                        f"title='{info['title'][:30]}' text='{info['text'][:40]}'",
                        "WARNING"
                    )
            except Exception:
                pass
            self._debug_dump(driver, "tools_btn_not_found")
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

    # ── Dismiss 'I'll do this later' popup ───────────────────────────────────────
    def _dismiss_later_popup(self, driver) -> bool:
        """
        Popup 'I'll do this later' di Gemini Business menggunakan Web Component
        dengan Shadow DOM bertingkat. Selenium find_elements() tidak bisa menembus
        shadow root, sehingga teks tombol tidak terbaca.

        Strategi (prioritas):
          1. JS shadow DOM traversal (_JS_FIND_DISMISS_BTN)
             -> Rekursif semua shadowRoot, cari button dengan teks 'later'/'skip'/'dismiss'
             -> Klik langsung via JS
          2. Polling 10 detik: JS traversal berulang (popup mungkin muncul terlambat)
          3. Fallback: debug dump semua button di shadow DOM via _JS_LIST_BUTTONS
             -> log untuk analisis, lalu coba klik button#button pertama yang visible
        """
        # Tunggu halaman settle
        time.sleep(random.uniform(2, 3))

        # Strategy 1: Langsung coba JS shadow DOM traversal
        try:
            btn = driver.execute_script(_JS_FIND_DISMISS_BTN)
            if btn:
                driver.execute_script("arguments[0].click();", btn)
                self._log("[Shadow DOM] Clicked 'I'll do this later' via JS traversal")
                return True
        except Exception as e:
            self._log(f"JS shadow DOM traversal error: {e}", "WARNING")

        # Strategy 2: Polling 10 detik
        self._log("Popup not found immediately, polling 10s...")
        deadline = time.time() + 10
        while time.time() < deadline:
            try:
                btn = driver.execute_script(_JS_FIND_DISMISS_BTN)
                if btn:
                    driver.execute_script("arguments[0].click();", btn)
                    self._log("[Shadow DOM] Clicked 'I'll do this later' (polling)")
                    return True
            except Exception:
                pass
            time.sleep(0.5)

        # Strategy 3: Debug dump semua button di shadow DOM
        self._log("Still not found. Listing all shadow DOM buttons for debug...", "WARNING")
        try:
            raw = driver.execute_script(_JS_LIST_BUTTONS)
            buttons_info = json.loads(raw) if raw else []
            for info in buttons_info:
                if info.get("visible"):
                    self._log(
                        f"  [BTN] tag={info['tag']} id='{info['id']}' "
                        f"cls='{info['cls'][:40]}' aria='{info['aria'][:40]}' "
                        f"text='{info['text'][:60]}'",
                        "WARNING"
                    )
        except Exception as e:
            self._log(f"Button listing failed: {e}", "WARNING")

        # Strategy 3b: Blind click - klik button#button visible pertama yang bukan download/icon
        # (jika popup ada tapi teks tidak terdeteksi karena encoding/language berbeda)
        try:
            clicked = driver.execute_script("""
                (function() {
                    var SKIP_ARIA = ['download', 'close', 'menu', 'search', 'send'];
                    function isSkip(el) {
                        var aria = (el.getAttribute('aria-label') || '').toLowerCase();
                        var cls  = (el.getAttribute('class') || '').toLowerCase();
                        return SKIP_ARIA.some(function(k) { return aria.indexOf(k) !== -1; })
                            || cls.indexOf('icon-button') !== -1
                            || cls.indexOf('send') !== -1;
                    }
                    function scan(root, depth) {
                        if (depth > 10) return null;
                        var btns = root.querySelectorAll('button#button, button.button');
                        for (var i = 0; i < btns.length; i++) {
                            var b = btns[i];
                            if (!isSkip(b) && b.offsetParent !== null) {
                                b.click();
                                return b.outerHTML.substring(0, 100);
                            }
                        }
                        var all = root.querySelectorAll('*');
                        for (var j = 0; j < all.length; j++) {
                            if (all[j].shadowRoot) {
                                var r = scan(all[j].shadowRoot, depth + 1);
                                if (r) return r;
                            }
                        }
                        return null;
                    }
                    return scan(document, 0);
                })();
            """)
            if clicked:
                self._log(
                    f"[Shadow DOM] Blind-clicked first visible button#button: {clicked}",
                    "WARNING"
                )
                return True
        except Exception as e:
            self._log(f"Blind click failed: {e}", "WARNING")

        # Screenshot untuk debug
        self._debug_dump(driver, "dismiss_popup_failed")
        return False

    # ── Process single prompt ───────────────────────────────────────────────
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
            for sel in ["button#button.button", "button#button", "button.button"]:
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
            for sel in ["button#button.button", "button#button", "button.button"]:
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
