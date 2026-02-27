"""
gemini_enterprise.py

Otomasi generate video di business.gemini.google
Menggunakan undetected-chromedriver (UC) + fresh temp profile
agar tidak terdeteksi sebagai bot oleh Google.

Mode operasi:
    1. SESSION MODE  : Load cookies dari session/gemini_session.json (prioritas)
    2. LOGIN MODE    : Login otomatis via email + OTP (fallback)
                       + auto-retry jika muncul 'Let's try something else'
"""

import os
import sys
import json
import time
import random
import shutil
import tempfile
import threading
from typing import Optional, Callable

try:
    import undetected_chromedriver as uc
except ImportError:
    uc = None

try:
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException
except ImportError:
    pass

from App.gmail_otp import GmailOTPReader

GEMINI_HOME_URL   = "https://business.gemini.google/"

OTP_TIMEOUT       = 120
VIDEO_GEN_TIMEOUT = 600
POLLING_INTERVAL  = 8
MAX_OTP_RETRY     = 3
MAX_LOGIN_RETRY   = 4

# Email input selectors (CSS)
EMAIL_SELECTORS = [
    "input[name='loginHint']",
    "input[id='email-input']",
    "input[jsname='YPqjbf']",
    "input[type='email']",
    "input[name='email']",
    "input[autocomplete='email']",
    "input[type='text']",
]

SUBMIT_SELECTORS = [
    "button[type='submit']",
    "button",
]

SIGNIN_RETRY_SELECTORS = [
    "a",
    "button",
]


class GeminiEnterpriseProcessor(threading.Thread):

    def __init__(
        self,
        base_dir:          str,
        prompt:            str,
        mask_email:        str,
        output_dir:        str,
        config:            dict,
        log_callback:      Optional[Callable] = None,
        progress_callback: Optional[Callable] = None,
        finished_callback: Optional[Callable] = None,
    ):
        super().__init__(daemon=True)
        self.base_dir     = base_dir
        self.prompt       = prompt
        self.mask_email   = mask_email
        self.output_dir   = output_dir or os.path.join(base_dir, "OUTPUT_GEMINI")
        self.config       = config
        self.log_cb       = log_callback
        self.progress_cb  = progress_callback
        self.finished_cb  = finished_callback
        self._cancelled   = False
        self._otp_reader  = GmailOTPReader(base_dir)
        self.debug_dir    = os.path.join(base_dir, "DEBUG")
        self.session_file = os.path.join(base_dir, "session", "gemini_session.json")
        self._driver      = None
        self._temp_profile = None

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

    # ── Debug ──────────────────────────────────────────────────────────────
    def _debug_dump(self, driver, label: str):
        try:
            os.makedirs(self.debug_dir, exist_ok=True)
            ts = int(time.time())
            driver.save_screenshot(os.path.join(self.debug_dir, f"{label}_{ts}.png"))
            with open(os.path.join(self.debug_dir, f"{label}_{ts}.html"), "w", encoding="utf-8") as f:
                f.write(driver.page_source)
            self._log(f"🔍 DEBUG: DEBUG/{label}_{ts}.*", "WARNING")
        except Exception as e:
            self._log(f"⚠️  Debug dump gagal: {e}", "WARNING")

    # ── UC Driver ──────────────────────────────────────────────────────────
    def _create_driver(self) -> Optional[object]:
        """Buat undetected-chromedriver dengan fresh temp profile."""
        if uc is None:
            self._log("❌ undetected-chromedriver tidak terinstall!", "ERROR")
            self._log("   → pip install undetected-chromedriver selenium", "ERROR")
            return None

        # Fresh temp profile — Google tidak kenal profil ini, tidak ada history bot
        self._temp_profile = tempfile.mkdtemp(prefix="gemini_uc_profile_")
        self._log(f"   📂 Fresh profile: {self._temp_profile}")

        headless = self.config.get("headless", False)

        options = uc.ChromeOptions()
        options.add_argument(f"--user-data-dir={self._temp_profile}")
        options.add_argument("--no-first-run")
        options.add_argument("--no-default-browser-check")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--disable-infobars")
        options.add_argument("--disable-extensions")
        options.add_argument("--lang=en-US")
        options.add_argument("--window-size=1280,900")
        options.add_argument("--disable-popup-blocking")

        # Preferences: bahasa, unduhan
        prefs = {
            "intl.accept_languages": "en,en_US",
            "download.default_directory": self.output_dir,
            "download.prompt_for_download": False,
            "download.directory_upgrade": True,
            "safebrowsing.enabled": True,
        }
        options.add_experimental_option("prefs", prefs)

        if headless:
            options.add_argument("--headless=new")

        try:
            driver = uc.Chrome(
                options=options,
                use_subprocess=True,   # spawn subprocess agar PID terpisah
                version_main=None,     # auto-detect versi Chrome
            )
            # Hapus tanda webdriver di JS
            driver.execute_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
            )
            self._log("✅ undetected-chromedriver berhasil dibuat", "SUCCESS")
            return driver
        except Exception as e:
            self._log(f"❌ Gagal buat UC driver: {e}", "ERROR")
            return None

    def _quit_driver(self, driver):
        """Quit driver dan bersihkan temp profile."""
        try:
            if driver:
                driver.quit()
        except Exception:
            pass
        # Hapus temp profile
        if self._temp_profile and os.path.exists(self._temp_profile):
            try:
                shutil.rmtree(self._temp_profile, ignore_errors=True)
                self._log(f"   🗑️  Temp profile dihapus: {self._temp_profile}")
            except Exception:
                pass

    # ── Session cookies ────────────────────────────────────────────────────
    def _has_valid_session(self) -> bool:
        if not os.path.exists(self.session_file):
            return False
        try:
            with open(self.session_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            # Format Selenium: list of cookie dicts
            if isinstance(data, list):
                cookies = data
            else:
                # Format Playwright storage_state
                cookies = data.get("cookies", [])
            google_cookies = [c for c in cookies if ".google.com" in c.get("domain", "")]
            return len(google_cookies) > 0
        except Exception:
            return False

    def _load_session(self, driver):
        """Inject cookies ke driver dari session file."""
        try:
            with open(self.session_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            if isinstance(data, list):
                cookies = data
            else:
                # Playwright format → konversi ke Selenium format
                cookies = []
                for c in data.get("cookies", []):
                    cookie = {
                        "name":   c.get("name", ""),
                        "value":  c.get("value", ""),
                        "domain": c.get("domain", ""),
                        "path":   c.get("path", "/"),
                    }
                    if c.get("expires") and c["expires"] > 0:
                        cookie["expiry"] = int(c["expires"])
                    if "httpOnly" in c:
                        cookie["httpOnly"] = c["httpOnly"]
                    if "secure" in c:
                        cookie["secure"] = c["secure"]
                    cookies.append(cookie)

            # Buka domain dulu sebelum set cookie
            driver.get("https://business.gemini.google/")
            time.sleep(2)

            loaded = 0
            for cookie in cookies:
                try:
                    # Selenium butuh domain tanpa leading dot untuk beberapa browser
                    ck = dict(cookie)
                    driver.add_cookie(ck)
                    loaded += 1
                except Exception:
                    pass

            self._log(f"   ✅ {loaded}/{len(cookies)} cookies dimuat", "SUCCESS")
            return loaded > 0
        except Exception as e:
            self._log(f"   ⚠️  Load session gagal: {e}", "WARNING")
            return False

    def _save_session(self, driver):
        """Simpan cookies dari driver ke session file (format Selenium)."""
        try:
            os.makedirs(os.path.dirname(self.session_file), exist_ok=True)
            cookies = driver.get_cookies()
            with open(self.session_file, "w", encoding="utf-8") as f:
                json.dump(cookies, f, indent=2)
            self._log(f"💾 Session tersimpan ({len(cookies)} cookies): {self.session_file}", "SUCCESS")
        except Exception as e:
            self._log(f"⚠️  Gagal simpan session: {e}", "WARNING")

    # ── Helpers ────────────────────────────────────────────────────────────
    def _wait_for(self, driver, css_selector, timeout=15):
        """Tunggu elemen muncul, return element atau None."""
        try:
            el = WebDriverWait(driver, timeout).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, css_selector))
            )
            return el
        except TimeoutException:
            return None

    def _find_element(self, driver, selectors):
        """Cari elemen dari list selector CSS, return element pertama yang ditemukan."""
        for sel in selectors:
            try:
                els = driver.find_elements(By.CSS_SELECTOR, sel)
                for el in els:
                    if el.is_displayed() and el.is_enabled():
                        return el
            except Exception:
                continue
        return None

    def _human_type(self, driver, element, text: str):
        """Mengetik seperti manusia dengan jeda random."""
        element.click()
        time.sleep(random.uniform(0.3, 0.6))
        element.clear()
        time.sleep(random.uniform(0.1, 0.25))
        from selenium.webdriver.common.action_chains import ActionChains
        ac = ActionChains(driver)
        for char in text:
            ac.send_keys(char)
            ac.pause(random.uniform(0.07, 0.16))
        ac.perform()
        time.sleep(random.uniform(0.4, 0.7))

    def _human_click(self, driver, element):
        """Klik dengan gerakan mouse human-like."""
        try:
            from selenium.webdriver.common.action_chains import ActionChains
            ActionChains(driver).move_to_element(element).pause(
                random.uniform(0.1, 0.3)
            ).click().perform()
        except Exception:
            element.click()

    def _is_error_page(self, driver) -> bool:
        """Cek apakah halaman 'Let's try something else' tampil."""
        try:
            src = driver.page_source.lower()
            return "try something else" in src or "let\u2019s try" in src
        except Exception:
            return False

    def _click_signin_retry(self, driver) -> bool:
        """Klik tombol 'Sign up or sign in' di halaman error."""
        try:
            wait = WebDriverWait(driver, 5)
            # Cari semua link/button, cari yang mengandung teks sign in
            for tag in ["a", "button"]:
                els = driver.find_elements(By.TAG_NAME, tag)
                for el in els:
                    txt = el.text.lower()
                    if "sign" in txt and ("up" in txt or "in" in txt):
                        self._log(f"   🔄 Klik retry: '{el.text.strip()}'")
                        self._human_click(driver, el)
                        time.sleep(random.uniform(2.5, 4.0))
                        return True
        except Exception as e:
            self._log(f"   ⚠️  Click retry error: {e}", "WARNING")
        return False

    # ── Main run ───────────────────────────────────────────────────────────
    def run(self):
        os.makedirs(self.output_dir, exist_ok=True)

        use_session = self._has_valid_session()
        if use_session:
            self._log("🔑 Session ditemukan → akan skip login", "SUCCESS")
        else:
            self._log("⚠️  Session tidak ada → Login otomatis", "WARNING")

        driver = self._create_driver()
        if driver is None:
            self._done(False, "Gagal membuat browser driver.")
            return

        try:
            result = self._run_automation(driver, use_session)
            if result:
                self._done(True, f"✅ Video tersimpan: {result}", result)
            else:
                self._done(False, "Generate video gagal atau dibatalkan.")
        except Exception as e:
            self._log(f"❌ Fatal error: {e}", "ERROR")
            import traceback
            self._log(traceback.format_exc(), "ERROR")
            self._done(False, str(e))
        finally:
            self._quit_driver(driver)

    # ── Automation flow ────────────────────────────────────────────────────
    def _run_automation(self, driver, use_session: bool) -> Optional[str]:
        self._progress(5, "Membuka Gemini Enterprise...")
        self._log("🌐 Membuka https://business.gemini.google/ ...")

        if use_session:
            # Inject cookies lalu reload
            ok = self._load_session(driver)
            if ok:
                driver.refresh()
                time.sleep(random.uniform(3, 5))
                current = driver.current_url
                self._log(f"   URL: {current}")

                if not any(x in current for x in ["signin", "login", "accounts.google"]):
                    self._log("✅ Session valid! Langsung ke dashboard.", "SUCCESS")
                    self._progress(50, "Session OK, buka menu Veo...")
                    return self._run_veo(driver)
                else:
                    self._log("⚠️  Session expired, fallback ke login...", "WARNING")
            else:
                self._log("⚠️  Gagal load session, fallback ke login...", "WARNING")

        # ── LOGIN OTOMATIS ──────────────────────────────────────────────────
        for attempt in range(1, MAX_LOGIN_RETRY + 1):
            if self._cancelled:
                return None

            self._log(f"🔄 Login attempt {attempt}/{MAX_LOGIN_RETRY}...")
            self._progress(8, f"Login attempt {attempt}/{MAX_LOGIN_RETRY}...")

            # Warm-up: buka google.com dulu di attempt pertama
            if attempt == 1:
                self._log("   → Warm-up google.com...")
                driver.get("https://www.google.com")
                time.sleep(random.uniform(2, 3.5))
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight / 3)")
                time.sleep(random.uniform(0.5, 1.2))

            # Navigasi ke Gemini
            driver.get(GEMINI_HOME_URL)
            time.sleep(random.uniform(3, 5))

            current = driver.current_url
            self._log(f"   URL: {current}")
            self._debug_dump(driver, f"attempt{attempt}_redirect")

            # Cek error page sebelum input
            if self._is_error_page(driver):
                self._log(f"⚠️  Error page sebelum input (attempt {attempt})", "WARNING")
                if attempt < MAX_LOGIN_RETRY and self._click_signin_retry(driver):
                    self._log("   → Klik 'Sign up or sign in', mencoba lagi...", "WARNING")
                    time.sleep(random.uniform(2, 3))
                    continue
                else:
                    break

            # Tunggu form email
            self._progress(10, "Menunggu form login...")
            self._log("   → Tunggu form email...")
            email_el = None
            for sel in EMAIL_SELECTORS:
                el = self._wait_for(driver, sel, timeout=12)
                if el and el.is_displayed():
                    self._log(f"   ✅ Form email: [{sel}]")
                    email_el = el
                    break

            if not email_el:
                self._log("   ❌ Form email tidak ditemukan!", "ERROR")
                self._debug_dump(driver, f"attempt{attempt}_no_email")
                continue

            # Input email
            self._log(f"📧 Input email: {self.mask_email}")
            try:
                self._human_type(driver, email_el, self.mask_email)

                # Cek value
                val = email_el.get_attribute("value")
                self._log(f"   ✅ Value: '{val}'")
                if val != self.mask_email:
                    email_el.clear()
                    email_el.send_keys(self.mask_email)
                    time.sleep(0.5)

                time.sleep(random.uniform(0.9, 1.8))

                # Klik submit
                submit_el = None
                for sel in SUBMIT_SELECTORS:
                    els = driver.find_elements(By.CSS_SELECTOR, sel)
                    for el in els:
                        if el.is_displayed() and el.is_enabled():
                            txt = el.text.lower()
                            if any(w in txt for w in ["continue", "next", "send", "sign in", "submit", ""]):
                                submit_el = el
                                break
                    if submit_el:
                        break

                if submit_el:
                    self._log(f"   → Klik submit: '{submit_el.text.strip()}'")
                    self._human_click(driver, submit_el)
                else:
                    from selenium.webdriver.common.keys import Keys
                    email_el.send_keys(Keys.RETURN)

                self._log("✅ Email tersubmit, menunggu respons...")
                time.sleep(random.uniform(3, 5))

            except Exception as e:
                self._log(f"   ❌ Error input email: {e}", "ERROR")
                self._debug_dump(driver, f"attempt{attempt}_email_error")
                continue

            # Cek error page setelah submit
            if self._is_error_page(driver):
                self._log(f"⚠️  'Let's try something else' muncul (attempt {attempt})", "WARNING")
                self._debug_dump(driver, f"attempt{attempt}_error_after_submit")

                if attempt < MAX_LOGIN_RETRY:
                    if self._click_signin_retry(driver):
                        self._log("   → Klik 'Sign up or sign in', tunggu form...", "WARNING")
                        # Tunggu form email muncul kembali
                        for sel in EMAIL_SELECTORS:
                            el = self._wait_for(driver, sel, timeout=12)
                            if el and el.is_displayed():
                                self._log("   ✅ Form muncul, ulangi input...", "WARNING")
                                break
                        time.sleep(random.uniform(1.5, 3))
                        continue
                break

            if self._cancelled:
                return None

            # ── OTP ──────────────────────────────────────────────────────
            self._progress(20, "Menunggu OTP dari Gmail...")
            self._log(f"   URL setelah submit: {driver.current_url}")
            self._debug_dump(driver, "otp_page")

            otp_code = None
            reg_ts   = int(time.time())

            for otp_try in range(1, MAX_OTP_RETRY + 1):
                self._log(f"📬 Polling OTP ({otp_try}/{MAX_OTP_RETRY})...")
                try:
                    otp_code = self._otp_reader.wait_for_otp(
                        sender="noreply-googlecloud@google.com",
                        timeout=OTP_TIMEOUT,
                        interval=5,
                        log_callback=self.log_cb,
                        mask_email=self.mask_email,
                        after_timestamp=reg_ts,
                    )
                    self._log(f"✅ OTP: {otp_code}", "SUCCESS")
                    break
                except TimeoutError:
                    self._log(f"⚠️  OTP timeout ({otp_try})", "WARNING")
                    if otp_try < MAX_OTP_RETRY:
                        try:
                            resend_els = driver.find_elements(By.XPATH,
                                "//*[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'resend') or "
                                "contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'send again')]"
                            )
                            if resend_els:
                                self._human_click(driver, resend_els[0])
                                time.sleep(2)
                                reg_ts = int(time.time())
                        except Exception:
                            pass

            if not otp_code:
                self._log("❌ Gagal dapat OTP!", "ERROR")
                self._debug_dump(driver, "otp_failed")
                return None

            if self._cancelled:
                return None

            # ── Input OTP ─────────────────────────────────────────────────
            self._progress(35, "Memasukkan OTP...")
            self._log("✏️  Input OTP...")
            try:
                otp_inputs = driver.find_elements(By.CSS_SELECTOR,
                    "input[type='text'][maxlength='1'], "
                    "input[autocomplete='one-time-code'], "
                    "input[name*='otp'], input[name*='code']"
                )
                if len(otp_inputs) > 1:
                    for i, digit in enumerate(otp_code[:len(otp_inputs)]):
                        otp_inputs[i].clear()
                        otp_inputs[i].send_keys(digit)
                        time.sleep(random.uniform(0.1, 0.22))
                elif len(otp_inputs) == 1:
                    self._human_type(driver, otp_inputs[0], otp_code)
                else:
                    from selenium.webdriver.common.action_chains import ActionChains
                    ActionChains(driver).send_keys(otp_code).perform()

                time.sleep(random.uniform(0.7, 1.2))

                # Klik verify
                verify_candidates = driver.find_elements(By.CSS_SELECTOR,
                    "button[type='submit'], button"
                )
                for el in verify_candidates:
                    txt = el.text.lower()
                    if any(w in txt for w in ["verify", "continue", "sign in", "next"]):
                        self._human_click(driver, el)
                        break
                else:
                    from selenium.webdriver.common.keys import Keys
                    driver.find_element(By.TAG_NAME, "body").send_keys(Keys.RETURN)

                self._log("✅ OTP tersubmit, menunggu redirect...")

                # Tunggu redirect ke Gemini
                for _ in range(25):
                    time.sleep(1)
                    if "business.gemini.google" in driver.current_url:
                        break

                if "business.gemini.google" not in driver.current_url:
                    self._log("❌ Redirect timeout setelah OTP!", "ERROR")
                    self._debug_dump(driver, "otp_redirect_failed")
                    return None

                self._log("✅ Login berhasil!", "SUCCESS")
                self._save_session(driver)
                return self._run_veo(driver)

            except Exception as e:
                self._log(f"❌ Error OTP: {e}", "ERROR")
                self._debug_dump(driver, "otp_error")
                return None

        self._log("❌ Semua login attempt gagal.", "ERROR")
        self._log("   → Jalankan Save_Session.bat untuk login manual.", "WARNING")
        return None

    # ── Veo ────────────────────────────────────────────────────────────────
    def _run_veo(self, driver) -> Optional[str]:
        self._progress(50, "Membuka menu Veo...")
        self._log("🎬 Mencari tombol tools...")
        time.sleep(random.uniform(2.5, 4))
        self._debug_dump(driver, "dashboard")

        try:
            tools_selectors = [
                "button[aria-label*='tool' i]",
                "button[aria-label*='attach' i]",
                "button[aria-label*='more' i]",
                "[role='button'][aria-label*='tool' i]",
            ]
            tools_btn = None
            for sel in tools_selectors:
                el = self._wait_for(driver, sel, timeout=8)
                if el and el.is_displayed():
                    tools_btn = el
                    self._log(f"   ✅ Tools btn: [{sel}]")
                    break

            if not tools_btn:
                # Fallback: cari semua button di form
                btns = driver.find_elements(By.CSS_SELECTOR, "form button")
                if btns:
                    tools_btn = btns[0]
                    self._log("   ✅ Tools btn fallback: form button[0]")

            if not tools_btn:
                self._log("❌ Tombol tools tidak ditemukan!", "ERROR")
                self._debug_dump(driver, "no_tools")
                return None

            self._human_click(driver, tools_btn)
            time.sleep(random.uniform(0.9, 1.6))

            # Cari menu Veo
            veo_el = None
            for sel in [
                "[role='menuitem']",
                "[role='option']",
                "li",
            ]:
                els = driver.find_elements(By.CSS_SELECTOR, sel)
                for el in els:
                    if "veo" in el.text.lower() or "video" in el.text.lower():
                        veo_el = el
                        break
                if veo_el:
                    break

            if not veo_el:
                self._log("❌ Menu Veo tidak ditemukan!", "ERROR")
                self._debug_dump(driver, "no_veo")
                return None

            self._log(f"   ✅ Veo: '{veo_el.text.strip()}'")
            self._human_click(driver, veo_el)
            time.sleep(random.uniform(1.5, 2.5))

        except Exception as e:
            self._log(f"❌ Error menu: {e}", "ERROR")
            self._debug_dump(driver, "menu_error")
            return None

        if self._cancelled:
            return None

        # ── Input prompt ──────────────────────────────────────────────────
        self._progress(60, "Input prompt...")
        self._debug_dump(driver, "veo_open")
        try:
            prompt_el = None
            for sel in ["textarea", "[contenteditable='true']", "[role='textbox']"]:
                el = self._wait_for(driver, sel, timeout=10)
                if el and el.is_displayed():
                    prompt_el = el
                    break

            if not prompt_el:
                self._log("❌ Input prompt tidak ditemukan!", "ERROR")
                self._debug_dump(driver, "no_prompt")
                return None

            self._human_type(driver, prompt_el, self.prompt)
            time.sleep(random.uniform(0.7, 1.2))

            # Klik send/generate
            send_candidates = driver.find_elements(By.CSS_SELECTOR,
                "button[aria-label*='send' i], "
                "button[aria-label*='generate' i], "
                "button[aria-label*='Submit' i], "
                "button[type='submit']"
            )
            if send_candidates:
                self._human_click(driver, send_candidates[0])
            else:
                from selenium.webdriver.common.keys import Keys
                prompt_el.send_keys(Keys.RETURN)

            self._log("✅ Prompt tersubmit!", "SUCCESS")
        except Exception as e:
            self._log(f"❌ Error prompt: {e}", "ERROR")
            self._debug_dump(driver, "prompt_error")
            return None

        if self._cancelled:
            return None

        # ── Polling video ─────────────────────────────────────────────────
        self._progress(70, "Menunggu Veo generate...")
        self._log(f"⏳ Polling max {VIDEO_GEN_TIMEOUT}s...")
        start = time.time()
        video_ready = False

        while time.time() - start < VIDEO_GEN_TIMEOUT:
            if self._cancelled:
                return None
            elapsed = int(time.time() - start)
            self._progress(
                min(70 + int((elapsed / VIDEO_GEN_TIMEOUT) * 18), 88),
                f"Generate... {elapsed}s/{VIDEO_GEN_TIMEOUT}s"
            )
            try:
                dl = driver.find_elements(By.CSS_SELECTOR,
                    "button[aria-label*='download' i], a[download]"
                )
                if dl:
                    video_ready = True
                    break
                # Cari teks 'Download' di button
                btns = driver.find_elements(By.TAG_NAME, "button")
                for btn in btns:
                    if "download" in btn.text.lower():
                        video_ready = True
                        break
                if video_ready:
                    break
            except Exception:
                pass
            time.sleep(POLLING_INTERVAL)

        if not video_ready:
            self._debug_dump(driver, "polling_timeout")
            return None

        if self._cancelled:
            return None

        # ── Download ──────────────────────────────────────────────────────
        self._progress(90, "Mendownload video...")
        try:
            out_path = os.path.join(self.output_dir, f"gemini_veo_{int(time.time())}.mp4")

            # Cari tombol download
            dl_btn = None
            for sel in ["button[aria-label*='download' i]", "a[download]"]:
                els = driver.find_elements(By.CSS_SELECTOR, sel)
                if els:
                    dl_btn = els[0]
                    break
            if not dl_btn:
                btns = driver.find_elements(By.TAG_NAME, "button")
                for btn in btns:
                    if "download" in btn.text.lower():
                        dl_btn = btn
                        break

            if not dl_btn:
                raise Exception("Tombol download tidak ditemukan")

            self._human_click(driver, dl_btn)
            self._log("✅ Klik download, menunggu file...")

            # Tunggu file di output_dir
            for _ in range(120):
                time.sleep(1)
                files = [
                    f for f in os.listdir(self.output_dir)
                    if f.endswith(".mp4") or f.endswith(".webm")
                ]
                if files:
                    # Ambil file terbaru
                    newest = max(
                        [os.path.join(self.output_dir, f) for f in files],
                        key=os.path.getmtime
                    )
                    self._log(f"✅ File terdownload: {newest}", "SUCCESS")
                    self._progress(100, "Selesai!")
                    return newest

            raise Exception("File tidak muncul setelah 120 detik")

        except Exception as e:
            self._log(f"❌ Download gagal: {e}", "ERROR")
            self._debug_dump(driver, "download_failed")
            return None
