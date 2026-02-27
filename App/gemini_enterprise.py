"""
gemini_enterprise.py

Otomasi generate video di business.gemini.google
Menggunakan undetected-chromedriver (UC) + fresh temp profile.

Fix:
    - Tiap login pakai email mask BARU dari Firefox Relay
    - Mask lama dihapus otomatis setelah selesai/gagal
    - OTP diambil dari pesan TERBARU (sort internalDate desc)
    - Setelah OTP submit, deteksi OTP salah/invalid lalu retry
    - Jika relay_config.json tidak ada, fallback ke mask_email dari config
"""

import os
import sys
import re
import json
import time
import random
import shutil
import tempfile
import threading
import subprocess
from typing import Optional, Callable

try:
    import undetected_chromedriver as uc
except ImportError:
    uc = None

try:
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.common.exceptions import TimeoutException, WebDriverException
except ImportError:
    pass

from App.gmail_otp import GmailOTPReader
from App.firefox_relay import FirefoxRelay

GEMINI_HOME_URL   = "https://business.gemini.google/"

OTP_TIMEOUT       = 120
VIDEO_GEN_TIMEOUT = 600
POLLING_INTERVAL  = 8
MAX_OTP_RETRY     = 3
MAX_LOGIN_RETRY   = 4

CHROME_PATHS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    os.path.expanduser(r"~\AppData\Local\Google\Chrome\Application\chrome.exe"),
]

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

# Keywords yang menandakan OTP salah/expired di halaman Google
OTP_ERROR_KEYWORDS = [
    "wrong code",
    "incorrect code",
    "invalid code",
    "code expired",
    "code has expired",
    "didn't match",
    "try again",
    "kode salah",
    "kode tidak valid",
    "kode sudah kadaluarsa",
    "that code didn't work",
    "code doesn't match",
    "please check",
]


# ── Chrome version detection ─────────────────────────────────────────────
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
        self.base_dir          = base_dir
        self.prompt            = prompt
        self.fallback_email    = mask_email
        self.output_dir        = output_dir or os.path.join(base_dir, "OUTPUT_GEMINI")
        self.config            = config
        self.log_cb            = log_callback
        self.progress_cb       = progress_callback
        self.finished_cb       = finished_callback
        self._cancelled        = False
        self._otp_reader       = GmailOTPReader(base_dir)
        self.debug_dir         = os.path.join(base_dir, "DEBUG")
        self.session_file      = os.path.join(base_dir, "session", "gemini_session.json")
        self._driver           = None
        self._temp_profile     = None
        self._current_mask_id  = None
        self._current_mask_email = None
        relay_key = FirefoxRelay.load_key(base_dir)
        self._relay = FirefoxRelay(relay_key) if relay_key else None

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

    # ── Email mask management ───────────────────────────────────────────────────
    def _create_new_mask(self) -> str:
        if self._relay:
            try:
                ts_label = f"gemini-veo-{int(time.time())}"
                result = self._relay.create_mask(label=ts_label)
                addr   = result.get("full_address", "")
                mask_id = result.get("id")
                if addr:
                    self._current_mask_id    = mask_id
                    self._current_mask_email = addr
                    self._log(f"   📨 Mask baru: {addr} (id={mask_id})", "SUCCESS")
                    return addr
            except Exception as e:
                self._log(f"   ⚠️  Gagal buat mask baru: {e} — pakai fallback", "WARNING")

        self._current_mask_email = self.fallback_email
        self._current_mask_id    = None
        self._log(f"   📧 Fallback email: {self.fallback_email}", "WARNING")
        return self.fallback_email

    def _delete_current_mask(self):
        if self._relay and self._current_mask_id:
            try:
                ok = self._relay.delete_mask(self._current_mask_id)
                if ok:
                    self._log(
                        f"   🗑️  Mask {self._current_mask_email} dihapus (id={self._current_mask_id})",
                        "WARNING"
                    )
                else:
                    self._log(
                        f"   ⚠️  Gagal hapus mask {self._current_mask_id}",
                        "WARNING"
                    )
            except Exception as e:
                self._log(f"   ⚠️  Delete mask error: {e}", "WARNING")
            self._current_mask_id    = None
            self._current_mask_email = None

    # ── Debug ────────────────────────────────────────────────────────────
    def _debug_dump(self, driver, label: str):
        try:
            os.makedirs(self.debug_dir, exist_ok=True)
            ts = int(time.time())
            driver.save_screenshot(os.path.join(self.debug_dir, f"{label}_{ts}.png"))
            with open(os.path.join(self.debug_dir, f"{label}_{ts}.html"), "w", encoding="utf-8") as f:
                f.write(driver.page_source)
        except Exception:
            pass

    # ── UC Driver ──────────────────────────────────────────────────────────
    def _create_driver(self) -> Optional[object]:
        if uc is None:
            self._log("❌ undetected-chromedriver tidak terinstall!", "ERROR")
            return None

        chrome_ver = _get_chrome_version()
        if chrome_ver:
            self._log(f"   💻 Chrome versi: {chrome_ver}", "SUCCESS")
        else:
            self._log("⚠️  Versi Chrome tidak terdeteksi", "WARNING")

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
        options.add_experimental_option("prefs", {
            "intl.accept_languages":     "en,en_US",
            "download.default_directory": self.output_dir,
            "download.prompt_for_download": False,
            "download.directory_upgrade": True,
            "safebrowsing.enabled":       True,
        })
        if headless:
            options.add_argument("--headless=new")

        for ver in ([chrome_ver, None] if chrome_ver else [None]):
            try:
                ver_label = str(ver) if ver else "auto"
                self._log(f"   → UC version_main={ver_label}...")
                driver = uc.Chrome(options=options, use_subprocess=True, version_main=ver)
                driver.execute_script(
                    "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
                )
                self._log(f"✅ UC driver OK (version_main={ver_label})", "SUCCESS")
                return driver
            except Exception as e:
                err = str(e)
                self._log(f"   ⚠️  version_main={ver_label} gagal: {err[:100]}", "WARNING")
                m = re.search(r"Current browser version is (\d+)", err)
                if m:
                    detected = int(m.group(1))
                    self._log(f"   🔍 Retry version_main={detected} dari error msg...", "WARNING")
                    try:
                        driver2 = uc.Chrome(options=options, use_subprocess=True,
                                            version_main=detected)
                        driver2.execute_script(
                            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
                        )
                        self._log(f"✅ UC driver OK (version_main={detected})", "SUCCESS")
                        return driver2
                    except Exception as e2:
                        self._log(f"   ❌ Retry {detected} gagal: {str(e2)[:80]}", "ERROR")

        self._log("❌ Semua percobaan UC driver gagal.", "ERROR")
        return None

    def _quit_driver(self, driver):
        try:
            if driver:
                driver.quit()
        except Exception:
            pass
        if self._temp_profile and os.path.exists(self._temp_profile):
            shutil.rmtree(self._temp_profile, ignore_errors=True)

    # ── Session ──────────────────────────────────────────────────────────
    def _has_valid_session(self) -> bool:
        if not os.path.exists(self.session_file):
            return False
        try:
            with open(self.session_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            cookies = data if isinstance(data, list) else data.get("cookies", [])
            return any(".google.com" in c.get("domain", "") for c in cookies)
        except Exception:
            return False

    def _load_session(self, driver) -> bool:
        try:
            with open(self.session_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            cookies = data if isinstance(data, list) else [
                {"name": c.get("name",""), "value": c.get("value",""),
                 "domain": c.get("domain",""), "path": c.get("path","/"),
                 "expiry": int(c["expires"]) if c.get("expires",0) > 0 else None,
                 "httpOnly": c.get("httpOnly", False),
                 "secure": c.get("secure", False)}
                for c in data.get("cookies", [])
            ]
            driver.get("https://business.gemini.google/")
            time.sleep(2)
            loaded = 0
            for ck in cookies:
                try:
                    driver.add_cookie({k: v for k, v in ck.items() if v is not None})
                    loaded += 1
                except Exception:
                    pass
            self._log(f"   ✅ {loaded}/{len(cookies)} cookies dimuat", "SUCCESS")
            return loaded > 0
        except Exception as e:
            self._log(f"   ⚠️  Load session gagal: {e}", "WARNING")
            return False

    def _save_session(self, driver):
        try:
            os.makedirs(os.path.dirname(self.session_file), exist_ok=True)
            cookies = driver.get_cookies()
            with open(self.session_file, "w", encoding="utf-8") as f:
                json.dump(cookies, f, indent=2)
            self._log(f"💾 Session tersimpan ({len(cookies)} cookies)", "SUCCESS")
        except Exception as e:
            self._log(f"   ⚠️  Gagal simpan session: {e}", "WARNING")

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
        time.sleep(random.uniform(0.1, 0.25))
        from selenium.webdriver.common.action_chains import ActionChains
        ac = ActionChains(driver)
        for char in text:
            ac.send_keys(char)
            ac.pause(random.uniform(0.07, 0.16))
        ac.perform()
        time.sleep(random.uniform(0.4, 0.7))

    def _human_click(self, driver, element):
        try:
            from selenium.webdriver.common.action_chains import ActionChains
            ActionChains(driver).move_to_element(element).pause(
                random.uniform(0.1, 0.3)
            ).click().perform()
        except Exception:
            element.click()

    def _is_error_page(self, driver) -> bool:
        try:
            src = driver.page_source.lower()
            return "try something else" in src or "let\u2019s try" in src
        except Exception:
            return False

    def _is_otp_error_page(self, driver) -> bool:
        """
        Cek apakah halaman menampilkan error OTP salah/expired.
        Return True jika ada keyword error OTP di page source.
        """
        try:
            src = driver.page_source.lower()
            return any(kw in src for kw in OTP_ERROR_KEYWORDS)
        except Exception:
            return False

    def _click_signin_retry(self, driver) -> bool:
        try:
            for tag in ["a", "button"]:
                for el in driver.find_elements(By.TAG_NAME, tag):
                    txt = el.text.lower()
                    if "sign" in txt and ("up" in txt or "in" in txt):
                        self._log(f"   🔄 Klik retry: '{el.text.strip()}'")
                        self._human_click(driver, el)
                        time.sleep(random.uniform(2.5, 4.0))
                        return True
        except Exception as e:
            self._log(f"   ⚠️  Click retry: {e}", "WARNING")
        return False

    # ── Main run ─────────────────────────────────────────────────────────
    def run(self):
        os.makedirs(self.output_dir, exist_ok=True)

        use_session = self._has_valid_session()
        if use_session:
            self._log("🔑 Session ditemukan → skip login & mask", "SUCCESS")
        else:
            self._log("⚠️  Session tidak ada → Login otomatis + mask baru", "WARNING")

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
            self._delete_current_mask()

    # ── Automation ─────────────────────────────────────────────────────────
    def _run_automation(self, driver, use_session: bool) -> Optional[str]:
        self._progress(5, "Membuka Gemini Enterprise...")
        self._log("🌐 Membuka https://business.gemini.google/ ...")

        # ── Mode session (skip mask + login) ───────────────────────────────────
        if use_session:
            ok = self._load_session(driver)
            if ok:
                driver.refresh()
                time.sleep(random.uniform(3, 5))
                current = driver.current_url
                if not any(x in current for x in ["signin", "login", "accounts.google"]):
                    self._log("✅ Session valid! Langsung ke dashboard.", "SUCCESS")
                    self._progress(50, "Session OK...")
                    return self._run_veo(driver)
                else:
                    self._log("⚠️  Session expired, fallback ke login...", "WARNING")
            else:
                self._log("⚠️  Gagal load session, fallback ke login...", "WARNING")

        # ── Login otomatis dengan mask BARU tiap attempt ──────────────────────────
        for attempt in range(1, MAX_LOGIN_RETRY + 1):
            if self._cancelled:
                return None

            active_email = self._create_new_mask()
            self._log(f"🔄 Login attempt {attempt}/{MAX_LOGIN_RETRY} — email: {active_email}")
            self._progress(8, f"Login attempt {attempt}/{MAX_LOGIN_RETRY}...")

            if attempt == 1:
                driver.get("https://www.google.com")
                time.sleep(random.uniform(2, 3.5))
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight / 3)")
                time.sleep(random.uniform(0.5, 1.2))

            driver.get(GEMINI_HOME_URL)
            time.sleep(random.uniform(3, 5))
            self._debug_dump(driver, f"attempt{attempt}_redirect")

            if self._is_error_page(driver):
                self._log(f"⚠️  Error page sebelum input (attempt {attempt})", "WARNING")
                if attempt < MAX_LOGIN_RETRY and self._click_signin_retry(driver):
                    self._delete_current_mask()
                    time.sleep(random.uniform(2, 3))
                    continue
                break

            self._progress(10, "Menunggu form login...")
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
                self._delete_current_mask()
                continue

            self._log(f"📧 Input email: {active_email}")
            try:
                self._human_type(driver, email_el, active_email)
                val = email_el.get_attribute("value")
                if val != active_email:
                    email_el.clear()
                    email_el.send_keys(active_email)
                    time.sleep(0.5)
                self._log(f"   ✅ Value: '{val}'")
                time.sleep(random.uniform(0.9, 1.8))

                submit_el = None
                for sel in SUBMIT_SELECTORS:
                    for el in driver.find_elements(By.CSS_SELECTOR, sel):
                        if el.is_displayed() and el.is_enabled():
                            submit_el = el
                            break
                    if submit_el:
                        break

                if submit_el:
                    self._human_click(driver, submit_el)
                else:
                    from selenium.webdriver.common.keys import Keys
                    email_el.send_keys(Keys.RETURN)

                self._log("✅ Email tersubmit...")
                time.sleep(random.uniform(3, 5))

            except Exception as e:
                self._log(f"   ❌ Error input email: {e}", "ERROR")
                self._debug_dump(driver, f"attempt{attempt}_email_error")
                self._delete_current_mask()
                continue

            if self._is_error_page(driver):
                self._log(f"⚠️  'Let's try something else' (attempt {attempt})", "WARNING")
                self._debug_dump(driver, f"attempt{attempt}_error_after_submit")
                self._delete_current_mask()
                if attempt < MAX_LOGIN_RETRY and self._click_signin_retry(driver):
                    for sel in EMAIL_SELECTORS:
                        el = self._wait_for(driver, sel, timeout=12)
                        if el and el.is_displayed():
                            break
                    time.sleep(random.uniform(1.5, 3))
                    continue
                break

            if self._cancelled:
                return None

            # ── OTP polling ───────────────────────────────────────────────
            self._progress(20, "Menunggu OTP...")
            self._log(f"   URL: {driver.current_url}")
            self._debug_dump(driver, "otp_page")

            otp_code = None
            reg_ts   = int(time.time())
            self._log(f"   ⏱️  OTP cutoff timestamp: {reg_ts}")

            for otp_try in range(1, MAX_OTP_RETRY + 1):
                self._log(f"📬 Polling OTP ({otp_try}/{MAX_OTP_RETRY}) — mask: {active_email}...")
                try:
                    otp_code = self._otp_reader.wait_for_otp(
                        sender          = "noreply-googlecloud@google.com",
                        timeout         = OTP_TIMEOUT,
                        interval        = 5,
                        log_callback    = self.log_cb,
                        mask_email      = active_email,
                        after_timestamp = reg_ts,
                    )
                    self._log(f"✅ OTP: {otp_code}", "SUCCESS")
                    break
                except TimeoutError:
                    self._log(f"⚠️  OTP timeout ({otp_try})", "WARNING")
                    if otp_try < MAX_OTP_RETRY:
                        try:
                            resend = driver.find_elements(By.XPATH,
                                "//*[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ',"
                                "'abcdefghijklmnopqrstuvwxyz'),'resend') or "
                                "contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ',"
                                "'abcdefghijklmnopqrstuvwxyz'),'send again')]"
                            )
                            if resend:
                                self._human_click(driver, resend[0])
                                time.sleep(2)
                                reg_ts = int(time.time())
                        except Exception:
                            pass

            if not otp_code:
                self._log("❌ Gagal dapat OTP!", "ERROR")
                self._debug_dump(driver, "otp_failed")
                self._delete_current_mask()
                return None

            if self._cancelled:
                return None

            # ── Input OTP + verifikasi ─────────────────────────────────────────
            otp_success = self._submit_and_verify_otp(driver, otp_code, active_email)
            if otp_success:
                return self._run_veo(driver)
            else:
                self._log("❌ OTP gagal! Hapus mask + coba ulang dari awal.", "ERROR")
                self._debug_dump(driver, f"otp_failed_attempt{attempt}")
                self._delete_current_mask()
                # Lanjut ke attempt berikutnya (buat mask baru)
                continue

        self._log("❌ Semua login attempt gagal.", "ERROR")
        return None

    # ── Submit OTP + verifikasi hasilnya ──────────────────────────────────
    def _submit_and_verify_otp(self, driver, otp_code: str, active_email: str) -> bool:
        """
        Submit kode OTP ke form Google, lalu verifikasi hasilnya:
          - True  : redirect ke business.gemini.google (login sukses)
          - False : OTP error page / redirect timeout / exception
        """
        self._progress(35, "Memasukkan OTP...")
        try:
            otp_inputs = driver.find_elements(By.CSS_SELECTOR,
                "input[type='text'][maxlength='1'],"
                "input[autocomplete='one-time-code'],"
                "input[name*='otp'],input[name*='code']"
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

            # Klik tombol submit OTP
            submit_found = False
            for el in driver.find_elements(By.CSS_SELECTOR, "button[type='submit'],button"):
                if any(w in el.text.lower() for w in ["verify", "continue", "sign in", "next"]):
                    self._human_click(driver, el)
                    submit_found = True
                    break
            if not submit_found:
                from selenium.webdriver.common.keys import Keys
                driver.find_element(By.TAG_NAME, "body").send_keys(Keys.RETURN)

            self._log("✅ OTP tersubmit...")

            # ── Tunggu redirect atau deteksi error OTP ──────────────────────
            for wait_tick in range(30):
                time.sleep(1)
                current_url = driver.current_url

                # Berhasil login
                if "business.gemini.google" in current_url:
                    self._log("✅ Login berhasil! Redirect ke dashboard.", "SUCCESS")
                    self._save_session(driver)
                    return True

                # Deteksi halaman error OTP (kode salah / expired)
                if self._is_otp_error_page(driver):
                    self._log(
                        f"   ❌ OTP '{otp_code}' SALAH atau EXPIRED — "
                        f"halaman Google menolak kode ini.",
                        "ERROR"
                    )
                    self._debug_dump(driver, "otp_rejected")
                    return False

                # Masih di halaman OTP / loading, lanjut polling
                if wait_tick % 5 == 0 and wait_tick > 0:
                    self._log(f"   ⏳ Menunggu redirect... ({wait_tick}s)")

            # Timeout 30 detik tanpa redirect
            self._log(
                f"   ❌ Redirect timeout setelah OTP submit! URL: {driver.current_url}",
                "ERROR"
            )
            return False

        except Exception as e:
            self._log(f"❌ Error input OTP: {e}", "ERROR")
            return False

    # ── Veo ────────────────────────────────────────────────────────────
    def _run_veo(self, driver) -> Optional[str]:
        self._progress(50, "Membuka menu Veo...")
        self._log("🎬 Mencari tombol tools...")
        time.sleep(random.uniform(2.5, 4))
        self._debug_dump(driver, "dashboard")

        try:
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

            if not tools_btn:
                self._log("❌ Tombol tools tidak ditemukan!", "ERROR")
                self._debug_dump(driver, "no_tools")
                return None

            self._human_click(driver, tools_btn)
            time.sleep(random.uniform(0.9, 1.6))

            veo_el = None
            for sel in ["[role='menuitem']", "[role='option']", "li"]:
                for el in driver.find_elements(By.CSS_SELECTOR, sel):
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

        self._progress(60, "Input prompt...")
        try:
            prompt_el = None
            for sel in ["textarea", "[contenteditable='true']", "[role='textbox']"]:
                el = self._wait_for(driver, sel, timeout=10)
                if el and el.is_displayed():
                    prompt_el = el
                    break
            if not prompt_el:
                self._log("❌ Input prompt tidak ditemukan!", "ERROR")
                return None

            self._human_type(driver, prompt_el, self.prompt)
            time.sleep(random.uniform(0.7, 1.2))

            send = driver.find_elements(By.CSS_SELECTOR,
                "button[aria-label*='send' i],button[aria-label*='generate' i],"
                "button[aria-label*='Submit' i],button[type='submit']"
            )
            if send:
                self._human_click(driver, send[0])
            else:
                from selenium.webdriver.common.keys import Keys
                prompt_el.send_keys(Keys.RETURN)

            self._log("✅ Prompt tersubmit!", "SUCCESS")
        except Exception as e:
            self._log(f"❌ Error prompt: {e}", "ERROR")
            return None

        if self._cancelled:
            return None

        self._progress(70, "Menunggu Veo generate...")
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
                if driver.find_elements(By.CSS_SELECTOR, "button[aria-label*='download' i],a[download]"):
                    video_ready = True; break
                for btn in driver.find_elements(By.TAG_NAME, "button"):
                    if "download" in btn.text.lower():
                        video_ready = True; break
                if video_ready:
                    break
            except Exception:
                pass
            time.sleep(POLLING_INTERVAL)

        if not video_ready:
            self._debug_dump(driver, "polling_timeout")
            return None

        self._progress(90, "Mendownload video...")
        try:
            dl_btn = None
            for sel in ["button[aria-label*='download' i]", "a[download]"]:
                els = driver.find_elements(By.CSS_SELECTOR, sel)
                if els:
                    dl_btn = els[0]; break
            if not dl_btn:
                for btn in driver.find_elements(By.TAG_NAME, "button"):
                    if "download" in btn.text.lower():
                        dl_btn = btn; break
            if not dl_btn:
                raise Exception("Tombol download tidak ditemukan")

            self._human_click(driver, dl_btn)
            self._log("✅ Klik download, menunggu file...")

            for _ in range(120):
                time.sleep(1)
                files = [f for f in os.listdir(self.output_dir)
                         if f.endswith(".mp4") or f.endswith(".webm")]
                if files:
                    newest = max(
                        [os.path.join(self.output_dir, f) for f in files],
                        key=os.path.getmtime
                    )
                    self._log(f"✅ File: {newest}", "SUCCESS")
                    self._progress(100, "Selesai!")
                    return newest

            raise Exception("File tidak muncul setelah 120s")
        except Exception as e:
            self._log(f"❌ Download gagal: {e}", "ERROR")
            return None
