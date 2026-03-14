"""
account_manager.py

Logika registrasi akun menggunakan exact CSS selector dari DevTools:
- Step 2/5  : #email-input
- Step 4    : #active-mail (mailticking)
- Step 6    : #log-in-button > span.UywwFc-RLmnJb
- Step 7    : #c2 (code sent indicator)
- Step 8    : #message-list > tr:nth-child(1) > td.col-6 > a
- Step 9    : #content-wrapper > table > ... > span (verification code)
- Step 10   : input di form OTP (CSS selector dari DevTools)
- Step 11   : tombol Verify (CSS selector dari DevTools)
- Step 12   : #full-name-label (tunggu muncul)
- Step 13   : #mat-input-0
- Step 14   : span.mdc-button__label di dalam form agree
- Step 15   : tunggu body > saasfe-root ... h1 hilang (loading selesai)
"""

import time
import random
import re

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import TimeoutException, NoSuchElementException

from App.js_constants import (
    _JS_DISMISS_POPUP,
    _JS_CLICK_TOOLS,
    _JS_CLICK_VEO,
    _JS_LIST_BUTTONS,
)

GEMINI_HOME_URL        = "https://business.gemini.google/"
OTP_TIMEOUT            = 90
MAX_ACCOUNT_RETRY      = 3
MAX_EMAIL_SUBMIT_RETRY = 5

# CSS Selectors dari DevTools (exact)
_SEL_EMAIL_INPUT     = "#email-input"
_SEL_ACTIVE_MAIL     = "#active-mail"              # mailticking email display
_SEL_LOGIN_BTN       = "#log-in-button > span.UywwFc-RLmnJb"
_SEL_CODE_SENT       = "#c2"                       # indikator 'code sent'
_SEL_MSG_LIST_FIRST  = "#message-list > tr:nth-child(1) > td.col-6 > a"
_SEL_VERIF_CODE      = (
    "#content-wrapper > table > tbody > tr > td > table > tbody "
    "> tr:nth-child(1) > td > table > tbody > tr > td "
    "> p.verification-code-container > span"
)
_SEL_OTP_INPUT       = (
    "#yDmH0d > c-wiz > div > div > div.keerLb > div > div > div > form "
    "> div:nth-child(1) > div > div.AFffCd > div > input"
)
_SEL_VERIFY_BTN      = (
    "#yDmH0d > c-wiz > div > div > div.keerLb > div > div > div > form "
    "> div.rPlx0b > div > div:nth-child(1) > span "
    "> div.VfPpkd-dgl2Hf-ppHlrf-sM5MNb > button > span.YUhpIc-RLmnJb"
)
_SEL_FULL_NAME_LABEL = "#full-name-label"
_SEL_NAME_INPUT      = "#mat-input-0"
_SEL_AGREE_BTN       = (
    "body > saasfe-root > main > saasfe-onboard-component "
    "> div > div > div > form > button > span.mdc-button__label"
)
_SEL_LOADING_H1      = (
    "body > saasfe-root > main > saasfe-onboard-component "
    "> div > div.loading-message > h1"
)

_ERROR_PAGE_INDICATORS = [
    "let's try something else",
    "lets try something else",
    "trouble retrieving the email",
    "go back to sign up or sign in",
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


def _wait_for_css(driver, selector, timeout=15, visible=False):
    """Tunggu elemen CSS selector muncul. visible=True untuk tunggu visible."""
    try:
        condition = (
            EC.visibility_of_element_located((By.CSS_SELECTOR, selector))
            if visible else
            EC.presence_of_element_located((By.CSS_SELECTOR, selector))
        )
        return WebDriverWait(driver, timeout).until(condition)
    except TimeoutException:
        return None


def _css_click(driver, selector, timeout=15, js_click=False):
    """Tunggu lalu klik elemen CSS selector."""
    el = _wait_for_css(driver, selector, timeout, visible=True)
    if not el:
        return False
    try:
        if js_click:
            driver.execute_script("arguments[0].click();", el)
        else:
            el.click()
        return True
    except Exception:
        try:
            driver.execute_script("arguments[0].click();", el)
            return True
        except Exception:
            return False


def _css_type(driver, selector, text, timeout=15, clear=True):
    """Tunggu lalu ketik teks ke elemen CSS selector."""
    el = _wait_for_css(driver, selector, timeout, visible=True)
    if not el:
        return False
    try:
        el.click()
        if clear:
            el.clear()
            driver.execute_script("arguments[0].value = '';", el)
        el.send_keys(text)
        return True
    except Exception:
        return False


class AccountManagerMixin:

    def _register_account(self, driver, worker_id=0) -> bool:
        for retry in range(1, MAX_ACCOUNT_RETRY + 1):
            self._log(f"[W-{worker_id}] --- ACCOUNT REGISTRATION (Attempt {retry}/{MAX_ACCOUNT_RETRY}) ---")
            if retry > 1:
                self._close_extra_tabs(driver)
            ok = self._register_once(driver, worker_id)
            if ok:
                return True
            self._log(f"[W-{worker_id}] Attempt {retry} failed, retrying...", "WARNING")
            time.sleep(3)
        return False

    def _register_once(self, driver, worker_id=0) -> bool:
        # ── Step 1-2: Buka Gemini, tunggu email input ──────────────────────
        self._log(f"[W-{worker_id}] Step 1: Buka business.gemini.google")
        try:
            driver.get(GEMINI_HOME_URL)
            WebDriverWait(driver, 20).until(lambda d: d.current_url != "about:blank")
        except Exception:
            pass

        # Step 2: Tunggu #email-input
        self._log("Step 2: Tunggu #email-input...")
        if not _wait_for_css(driver, _SEL_EMAIL_INPUT, timeout=30, visible=True):
            self._log("Step 2: #email-input tidak muncul!", "ERROR")
            self._debug_dump(driver, "no_email_input")
            return False
        self._log("Step 2: #email-input ready")
        gemini_tab = driver.current_window_handle

        # ── Step 3: Buka mailticking di tab baru ───────────────────────────
        self._log("Step 3: Buka mailticking.com di tab baru")
        driver.execute_script("window.open('about:blank', '_blank');")
        time.sleep(0.5)
        driver.switch_to.window(driver.window_handles[-1])
        mail_tab = driver.current_window_handle

        from App.mailticking import MAILTICKING_URL
        driver.get(MAILTICKING_URL)
        self._wait_page_ready(driver, timeout=30, label="mailticking.com")

        # Step 4: Baca email dari #active-mail
        self._log("Step 4: Baca email dari #active-mail")
        email = ""
        for attempt in range(10):
            try:
                el = _wait_for_css(driver, _SEL_ACTIVE_MAIL, timeout=5, visible=True)
                if el:
                    email = (el.text or el.get_attribute("value") or "").strip()
                    if "@" in email:
                        break
            except Exception:
                pass
            time.sleep(2)

        if not email or "@" not in email:
            # Fallback ke method lama
            email = self._mail_client.get_fresh_email(driver)

        if not email or "@" not in email:
            self._log("Step 4: Gagal mendapatkan email temp", "ERROR")
            return False
        self._log(f"Step 4: Email: {email}")

        # ── Step 5-6: Input email ke Gemini ────────────────────────────────
        self._log("Step 5: Switch ke Gemini, input email")
        driver.switch_to.window(gemini_tab)

        submitted = False
        for attempt in range(1, MAX_EMAIL_SUBMIT_RETRY + 1):
            self._log(f"Step 5: Submit email attempt {attempt}/{MAX_EMAIL_SUBMIT_RETRY}")

            if self._is_lets_try_error_page(driver):
                self._handle_lets_try_something_else(driver)
                time.sleep(1)
                continue

            # Ketik email ke #email-input
            if not _css_type(driver, _SEL_EMAIL_INPUT, email, timeout=15):
                self._log("Step 5: Tidak bisa ketik ke #email-input", "WARNING")
                self._debug_dump(driver, f"type_email_fail_{attempt}")
                time.sleep(2)
                driver.refresh()
                _wait_for_css(driver, _SEL_EMAIL_INPUT, timeout=20, visible=True)
                continue

            # Verifikasi isi input
            try:
                el = driver.find_element(By.CSS_SELECTOR, _SEL_EMAIL_INPUT)
                actual = (el.get_attribute("value") or "").strip()
                if actual.lower() != email.lower():
                    self._log(f"Step 5: Mismatch email: '{actual}' != '{email}'", "WARNING")
                    driver.execute_script("arguments[0].value = '';", el)
                    continue
            except Exception:
                pass

            # Step 6: Klik tombol login
            self._log("Step 6: Klik #log-in-button")
            if not _css_click(driver, _SEL_LOGIN_BTN, timeout=10, js_click=True):
                # Fallback: tekan Enter
                try:
                    el = driver.find_element(By.CSS_SELECTOR, _SEL_EMAIL_INPUT)
                    el.send_keys(Keys.RETURN)
                    self._log("Step 6: Fallback Enter key")
                except Exception:
                    pass

            time.sleep(2)
            if self._is_lets_try_error_page(driver):
                self._handle_lets_try_something_else(driver)
                continue

            submitted = True
            self._log(f"Step 6: Email submitted: {email}")
            break

        if not submitted:
            self._log("Step 6: Gagal submit email", "ERROR")
            return False

        # ── Step 7: Tunggu OTP page (#c2 muncul) ───────────────────────────
        self._log("Step 7: Tunggu OTP page (#c2)...")
        self._wait_page_ready(driver, timeout=20, label="OTP Page")

        # Tunggu URL berubah ke verification page
        deadline = time.time() + 60
        while time.time() < deadline:
            try:
                url = driver.current_url.lower()
                if any(k in url for k in ["accountverification", "verify-oob-code", "oauth2", "signin-callback"]):
                    break
                if self._is_lets_try_error_page(driver):
                    self._log("Step 7: Error page pada OTP wait", "WARNING")
                    return False
            except Exception:
                pass
            time.sleep(1)

        # Tunggu #c2 (code sent indicator)
        code_sent_el = _wait_for_css(driver, _SEL_CODE_SENT, timeout=30, visible=False)
        if code_sent_el:
            self._log("Step 7: #c2 ditemukan - OTP page ready")
        else:
            self._log("Step 7: #c2 tidak ditemukan, lanjut...", "WARNING")

        # ── Step 8: Baca email OTP dari mailticking ─────────────────────────
        self._log("Step 8: Switch ke mailticking, tunggu email OTP")
        driver.switch_to.window(mail_tab)

        # Tunggu email masuk: klik #message-list tr pertama
        otp_link = None
        deadline = time.time() + OTP_TIMEOUT
        while time.time() < deadline:
            try:
                el = _wait_for_css(driver, _SEL_MSG_LIST_FIRST, timeout=3, visible=True)
                if el:
                    otp_link = el
                    self._log("Step 8: Email OTP ditemukan di message list")
                    break
            except Exception:
                pass
            # Refresh inbox
            try:
                refresh_btn = driver.find_element(By.CSS_SELECTOR, "#refresh-btn, .refresh, [data-action='refresh']")
                driver.execute_script("arguments[0].click();", refresh_btn)
            except Exception:
                pass
            time.sleep(3)

        if not otp_link:
            self._log("Step 8: Email OTP tidak datang (timeout)", "ERROR")
            return False

        # Klik email untuk membuka
        try:
            driver.execute_script("arguments[0].click();", otp_link)
            time.sleep(2)
        except Exception:
            pass

        # Step 9: Ambil kode OTP dari span
        self._log("Step 9: Ambil kode verifikasi")
        otp = ""
        for attempt in range(5):
            try:
                el = _wait_for_css(driver, _SEL_VERIF_CODE, timeout=5, visible=False)
                if el:
                    otp = (el.text or "").strip()
                    if otp and otp.isdigit() and len(otp) >= 4:
                        self._log(f"Step 9: OTP: {otp}")
                        break
            except Exception:
                pass
            time.sleep(2)

        if not otp:
            # Fallback ke extract method lama
            otp = self._mail_client.extract_verification_code(driver, mail_tab_handle=mail_tab)

        if not otp:
            self._log("Step 9: OTP tidak ditemukan", "ERROR")
            return False

        # ── Step 10: Input OTP ─────────────────────────────────────────────
        self._log(f"Step 10: Input OTP ke Gemini")
        driver.switch_to.window(gemini_tab)
        self._wait_page_ready(driver, timeout=15, label="Gemini OTP Form")
        time.sleep(1)

        otp_ok = False
        for attempt in range(1, 4):
            el = _wait_for_css(driver, _SEL_OTP_INPUT, timeout=10, visible=True)
            if not el:
                # Fallback: cari input apapun yang visible
                try:
                    inputs = driver.find_elements(By.CSS_SELECTOR, "input")
                    for inp in inputs:
                        if inp.is_displayed() and (inp.get_attribute("type") or "").lower() in ("text", "tel", "number", ""):
                            el = inp
                            break
                except Exception:
                    pass

            if not el:
                self._log(f"Step 10: OTP input tidak ditemukan (attempt {attempt}/3)", "WARNING")
                time.sleep(2)
                continue

            try:
                el.click()
                time.sleep(0.3)
                for char in otp:
                    ActionChains(driver).send_keys(char).perform()
                    time.sleep(random.uniform(0.12, 0.25))
                self._log(f"Step 10: OTP diketik: {otp}")
                otp_ok = True
                break
            except Exception as e:
                self._log(f"Step 10: Error ketik OTP attempt {attempt}: {e}", "WARNING")
                time.sleep(2)

        if not otp_ok:
            self._log("Step 10: Gagal input OTP", "ERROR")
            self._debug_dump(driver, "otp_type_failed")
            return False

        time.sleep(0.5)

        # ── Step 11: Klik Verify ────────────────────────────────────────────
        self._log("Step 11: Klik tombol Verify")
        verify_ok = _css_click(driver, _SEL_VERIFY_BTN, timeout=10, js_click=True)
        if not verify_ok:
            # Fallback selectors
            for sel in ["button[jsname='LgbsSe']", "button[type='submit']", ".YUhpIc-RLmnJb"]:
                if _css_click(driver, sel, timeout=5, js_click=True):
                    verify_ok = True
                    break
            if not verify_ok:
                for el in driver.find_elements(By.TAG_NAME, "button"):
                    try:
                        if any(w in el.text.lower() for w in ["verify", "confirm", "continue"]) and el.is_displayed():
                            driver.execute_script("arguments[0].click();", el)
                            verify_ok = True
                            break
                    except Exception:
                        pass
        if not verify_ok:
            self._log("Step 11: Verify button tidak ditemukan", "WARNING")
        else:
            self._log("Step 11: Verify clicked")

        time.sleep(random.uniform(0.3, 0.6))

        # Cek apakah sudah past verification
        try:
            src = driver.page_source.lower()
            if any(k in src for k in ["full name", "fullname", "agree", "get started"]):
                self._log("Step 11: Already past verification")
        except Exception:
            pass

        # ── Step 12: Tunggu #full-name-label ───────────────────────────────
        self._log("Step 12: Tunggu form nama (#full-name-label)...")
        name_page = _wait_for_css(driver, _SEL_FULL_NAME_LABEL, timeout=30, visible=False)
        if name_page:
            self._log("Step 12: Form nama muncul")
        else:
            self._log("Step 12: Form nama tidak muncul, lanjut...", "WARNING")

        # ── Step 13: Ketik nama ─────────────────────────────────────────────
        self._log("Step 13: Input nama (#mat-input-0)")
        name = _random_name()
        name_ok = _css_type(driver, _SEL_NAME_INPUT, name, timeout=15)
        if not name_ok:
            self._log("Step 13: Name input fallback", "WARNING")
            for sel in ["input[formcontrolname='fullName']", "input[placeholder='Full name']"]:
                if _css_type(driver, sel, name, timeout=5):
                    name_ok = True
                    break
        if name_ok:
            self._log(f"Step 13: Nama diisi: {name}")
        else:
            self._log("Step 13: Nama tidak bisa diisi", "WARNING")

        # ── Step 14: Klik Agree & get started ──────────────────────────────
        self._log("Step 14: Klik Agree & get started")
        agree_ok = _css_click(driver, _SEL_AGREE_BTN, timeout=15, js_click=True)
        if not agree_ok:
            for sel in [".mdc-button__label", "button.mdc-button", "button[mat-flat-button]"]:
                try:
                    els = driver.find_elements(By.CSS_SELECTOR, sel)
                    for el in els:
                        txt = (el.text or "").strip().lower()
                        if "agree" in txt or "get started" in txt:
                            try:
                                parent = el.find_element(By.XPATH, "./ancestor::button")
                                driver.execute_script("arguments[0].click();", parent)
                            except Exception:
                                driver.execute_script("arguments[0].click();", el)
                            agree_ok = True
                            break
                except Exception:
                    pass
                if agree_ok:
                    break
        if agree_ok:
            self._log("Step 14: Agree clicked")
        else:
            self._log("Step 14: Agree button tidak ditemukan", "WARNING")

        # ── Step 15: Tunggu loading selesai (h1 hilang) ─────────────────────
        self._log("Step 15: Tunggu sign-in selesai (loading h1 hilang)...")
        deadline = time.time() + 60
        while time.time() < deadline:
            try:
                h1 = driver.find_element(By.CSS_SELECTOR, _SEL_LOADING_H1)
                if not h1.is_displayed():
                    break
            except NoSuchElementException:
                # h1 sudah hilang dari DOM = selesai
                break
            except Exception:
                break
            time.sleep(0.5)
        self._log("Step 15: Sign-in selesai")
        self._wait_page_ready(driver, timeout=20, label="Post-SignIn")

        # ── Step 16-18: Initial setup (shadow DOM) ──────────────────────────
        self._log("Ensuring Gemini tab & shadow DOM ready...")
        self._ensure_gemini_tab(driver, gemini_tab)

        setup_ok = False
        for setup_try in range(1, 4):
            try:
                self._initial_setup(driver)
                setup_ok = True
                break
            except Exception as e:
                self._log(f"Initial setup error (attempt {setup_try}/3): {e}", "WARNING")
                time.sleep(3)
                try:
                    driver.refresh()
                    time.sleep(random.uniform(3, 5))
                except Exception:
                    pass
        if not setup_ok:
            return False

        self._log("Registrasi dan setup selesai!")
        return True

    # =========================================================================
    # Helper: ensure Gemini tab + wait shadow DOM ready
    # =========================================================================

    # JS probe: cek tools button sudah ada di shadow DOM
    _JS_WAIT_SHADOW_READY = """
    (function() {
        function scan(root, depth) {
            if (depth > 10) return false;
            if (root.querySelector && (
                root.querySelector("#tool-selector-menu-anchor") ||
                root.querySelector(".omnibox-tools-selector") ||
                root.querySelector(".tools-button-container")
            )) return true;
            var all = root.querySelectorAll ? root.querySelectorAll('*') : [];
            for (var i = 0; i < all.length; i++) {
                if (all[i].shadowRoot && scan(all[i].shadowRoot, depth + 1)) return true;
            }
            return false;
        }
        return scan(document, 0);
    })();
    """

    def _ensure_gemini_tab(self, driver, gemini_tab: str):
        try:
            driver.switch_to.window(gemini_tab)
        except Exception as e:
            self._log(f"[TAB] Switch failed: {e}", "WARNING")
            for handle in driver.window_handles:
                try:
                    driver.switch_to.window(handle)
                    if "business.gemini.google" in driver.current_url:
                        break
                except Exception:
                    pass

        try:
            current_url = driver.current_url
            self._log(f"[TAB] URL: {current_url}")
        except Exception:
            current_url = ""

        if "accounts.google" in current_url or "business.gemini.google" not in current_url:
            self._log("[TAB] Menunggu redirect ke Gemini...", "WARNING")
            deadline = time.time() + 30
            while time.time() < deadline:
                try:
                    url = driver.current_url
                    if "business.gemini.google" in url and "accounts.google" not in url:
                        break
                except Exception:
                    pass
                time.sleep(1)
            else:
                try:
                    driver.get(GEMINI_HOME_URL)
                except Exception:
                    pass

        self._wait_page_ready(driver, timeout=20, label="Gemini Main (pre-setup)")

        # Tunggu ucs-standalone-app
        deadline = time.time() + 20
        while time.time() < deadline:
            try:
                el = driver.execute_script("return document.querySelector('body > ucs-standalone-app');")
                if el:
                    self._log("[TAB] ucs-standalone-app ditemukan")
                    break
            except Exception:
                pass
            time.sleep(0.5)
        else:
            self._log("[TAB] ucs-standalone-app tidak muncul!", "WARNING")
            self._debug_dump(driver, "no_ucs_app")

        # Tunggu tools button ready di shadow DOM
        self._log("[TAB] Tunggu tools button di shadow DOM...")
        deadline = time.time() + 30
        while time.time() < deadline:
            try:
                if driver.execute_script(self._JS_WAIT_SHADOW_READY):
                    self._log("[TAB] Shadow DOM ready")
                    break
            except Exception:
                pass
            time.sleep(0.5)
        else:
            self._log("[TAB] Shadow DOM timeout, lanjut...", "WARNING")
            self._debug_dump(driver, "shadow_not_ready")
        time.sleep(1)

    # =========================================================================
    # Initial setup: step 16 (popup) -> 17 (tools) -> 18 (veo)
    # =========================================================================

    def _initial_setup(self, driver):
        try:
            self._log(f"[SETUP] URL: {driver.current_url}")
        except Exception:
            pass

        # Step 16: Dismiss popup
        self._log("Step 16: Tutup popup 'I'll do this later'...")
        dismissed = False
        for attempt in range(1, 4):
            try:
                if driver.execute_script(_JS_DISMISS_POPUP):
                    self._log("Step 16: Popup dismissed")
                    dismissed = True
                    break
            except Exception as e:
                self._log(f"Step 16 attempt {attempt}/3: {e}", "WARNING")
                time.sleep(2)
        if not dismissed:
            self._log("Step 16: Popup tidak ditemukan, lanjut...", "WARNING")
        self._wait_page_ready(driver, timeout=15, label="Post-Dismiss")

        # Tunggu tools button sekali lagi setelah dismiss
        deadline = time.time() + 20
        while time.time() < deadline:
            try:
                if driver.execute_script(self._JS_WAIT_SHADOW_READY):
                    break
            except Exception:
                pass
            time.sleep(0.5)
        time.sleep(0.5)

        # Step 17: Klik tools button
        self._log("Step 17: Klik tools button...")
        tools_clicked = False
        for attempt in range(1, 6):
            try:
                result = driver.execute_script(_JS_CLICK_TOOLS)
                if result:
                    self._log(f"Step 17: Tools clicked (attempt {attempt})")
                    tools_clicked = True
                    break
                else:
                    self._log(f"Step 17: Falsy (attempt {attempt}/5)", "WARNING")
                    try:
                        btns = driver.execute_script(_JS_LIST_BUTTONS)
                        self._log(f"[DEBUG] Buttons: {(btns or 'none')[:300]}")
                    except Exception:
                        pass
            except Exception as e:
                self._log(f"Step 17 attempt {attempt}/5: {e}", "WARNING")
            if attempt < 5:
                time.sleep(3)

        if not tools_clicked:
            self._log("Step 17: Tools button tidak ditemukan!", "WARNING")
            self._debug_dump(driver, "tools_not_found")
            return

        time.sleep(1.5)

        # Step 18: Klik Veo
        self._log("Step 18: Pilih 'Create videos with Veo'...")
        veo_clicked = False
        for attempt in range(1, 6):
            try:
                result = driver.execute_script(_JS_CLICK_VEO)
                if result:
                    self._log("Step 18: Veo diklik")
                    veo_clicked = True
                    break
                self._log(f"Step 18: Falsy (attempt {attempt}/5)", "WARNING")
            except Exception as e:
                self._log(f"Step 18 attempt {attempt}/5: {e}", "WARNING")
            if not veo_clicked and attempt < 5:
                time.sleep(2)
                # Re-open tools menu
                try:
                    driver.execute_script(_JS_CLICK_TOOLS)
                    time.sleep(1.5)
                except Exception:
                    pass

        if not veo_clicked:
            self._log("Step 18: Veo tidak ditemukan!", "WARNING")
            self._debug_dump(driver, "veo_not_found")

        self._wait_page_ready(driver, timeout=15, label="Post-Veo")
        self._log("Step 18: Initial setup selesai!")

    # =========================================================================
    # Helper methods
    # =========================================================================

    def _is_lets_try_error_page(self, driver) -> bool:
        try:
            src = driver.page_source.lower()
            return any(k in src for k in _ERROR_PAGE_INDICATORS)
        except Exception:
            return False

    def _handle_lets_try_something_else(self, driver) -> bool:
        self._log("[!] Error page terdeteksi, navigasi ulang...", "WARNING")
        self._debug_dump(driver, "error_page")
        try:
            driver.get(GEMINI_HOME_URL)
            _wait_for_css(driver, _SEL_EMAIL_INPUT, timeout=20, visible=True)
        except Exception:
            pass
        return True

    def _read_email_from_gemini_otp_page(self, driver) -> str:
        try:
            src = driver.page_source
            m = re.search(
                r'(?:code sent to|sent to|verify)\s+([a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})',
                src, re.IGNORECASE
            )
            if m:
                return m.group(1).strip()
        except Exception:
            pass
        return ""

    def _resync_mailticking_email(self, driver, target_email: str) -> bool:
        try:
            driver.refresh()
            self._wait_page_ready(driver, timeout=15, label="Mailticking Resync")
            el = _wait_for_css(driver, _SEL_ACTIVE_MAIL, timeout=5, visible=True)
            if el:
                current = (el.text or "").strip()
                if current.lower() == target_email.lower():
                    return True
        except Exception:
            pass
        return False

    def _is_error_page(self, driver) -> bool:
        try:
            src = driver.page_source.lower()
            return any(k in src for k in ["something went wrong", "couldn't sign", "error occurred"])
        except Exception:
            return False

    def _enter_name(self, driver) -> bool:
        name = _random_name()
        return _css_type(driver, _SEL_NAME_INPUT, name, timeout=10)

    def _click_agree_button(self, driver) -> bool:
        return _css_click(driver, _SEL_AGREE_BTN, timeout=10, js_click=True)

    def _submit_otp(self, driver, otp: str) -> bool:
        el = _wait_for_css(driver, _SEL_OTP_INPUT, timeout=10, visible=True)
        if not el:
            inputs = driver.find_elements(By.CSS_SELECTOR, "input")
            for inp in inputs:
                if inp.is_displayed() and (inp.get_attribute("type") or "").lower() in ("text", "tel", "number", ""):
                    el = inp
                    break
        if not el:
            return False
        try:
            el.click()
            time.sleep(0.3)
            for char in otp:
                ActionChains(driver).send_keys(char).perform()
                time.sleep(random.uniform(0.12, 0.25))
            return True
        except Exception:
            return False

    def _click_verify_button(self, driver) -> bool:
        return _css_click(driver, _SEL_VERIFY_BTN, timeout=10, js_click=True)
