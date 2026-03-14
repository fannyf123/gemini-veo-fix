"""
account_manager.py

Flow step terbaru:
  Step 1  : Buka business.gemini.google
  Step 2  : Buka mailticking.com di tab baru
            - Uncheck @gmail     : #emailActivationModal ... div:nth-child(3) > label
            - Uncheck @googlemail: #emailActivationModal ... div:nth-child(2) > label  (jika ada)
            - Sisakan @domain.com: #emailActivationModal ... div:nth-child(1) > label
  Step 3  : Klik [#modalChange], pastikan email bukan @gmail/@googlemail,
            klik Activate [#emailActivationModal ... a]
  Step 4  : Copy email dari [#selectedEmail], switch ke Gemini,
            input ke [#email-input]
  Step 5  : Submit email via [#log-in-button > span.UywwFc-RLmnJb]
  Step 6  : Tunggu OTP page [#c2]
  Step 7  : Baca inbox mailticking [#message-list > tr:nth-child(1) > td.col-6 > a]
  Step 8  : Ambil kode OTP dari email
  Step 9  : Input OTP + klik Verify
  Step 10 : Isi nama [#mat-input-0]
  Step 11 : Klik Agree [span.mdc-button__label]
  Step 12 : Tunggu loading selesai (h1 hilang)
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
MAILTICKING_URL        = "https://www.mailticking.com/"
OTP_TIMEOUT            = 90
MAX_ACCOUNT_RETRY      = 3
MAX_EMAIL_SUBMIT_RETRY = 5

# ── Gemini selectors ────────────────────────────────────────────────────────
_SEL_EMAIL_INPUT    = "#email-input"
_SEL_LOGIN_BTN      = "#log-in-button > span.UywwFc-RLmnJb"
_SEL_CODE_SENT      = "#c2"
_SEL_OTP_INPUT      = (
    "#yDmH0d > c-wiz > div > div > div.keerLb > div > div > div > form "
    "> div:nth-child(1) > div > div.AFffCd > div > input"
)
_SEL_VERIFY_BTN     = (
    "#yDmH0d > c-wiz > div > div > div.keerLb > div > div > div > form "
    "> div.rPlx0b > div > div:nth-child(1) > span "
    "> div.VfPpkd-dgl2Hf-ppHlrf-sM5MNb > button > span.YUhpIc-RLmnJb"
)
_SEL_FULL_NAME_LABEL = "#full-name-label"
_SEL_NAME_INPUT     = "#mat-input-0"
_SEL_AGREE_BTN      = (
    "body > saasfe-root > main > saasfe-onboard-component "
    "> div > div > div > form > button > span.mdc-button__label"
)
_SEL_LOADING_H1     = (
    "body > saasfe-root > main > saasfe-onboard-component "
    "> div > div.loading-message > h1"
)

# ── Mailticking selectors ────────────────────────────────────────────────────
# Modal body checkbox labels (dari DevTools)
_SEL_MT_MODAL_BODY      = "#emailActivationModal > div > div > div.modal-body.pt-4 > div > div > div > div.form-group"
_SEL_MT_LABEL_DOMAIN    = _SEL_MT_MODAL_BODY + " > div:nth-child(1) > label"   # @domain.com (sisakan)
_SEL_MT_LABEL_GMAIL     = _SEL_MT_MODAL_BODY + " > div:nth-child(3) > label"   # @gmail.com  (uncheck)
_SEL_MT_LABEL_GOOGLEMAIL= _SEL_MT_MODAL_BODY + " > div:nth-child(2) > label"   # @googlemail (uncheck jika ada)
# Checkbox input di dalam tiap label (untuk cek status)
_SEL_MT_CHK_DOMAIN      = _SEL_MT_MODAL_BODY + " > div:nth-child(1) > label > input"
_SEL_MT_CHK_GMAIL       = _SEL_MT_MODAL_BODY + " > div:nth-child(3) > input, " + _SEL_MT_MODAL_BODY + " > div:nth-child(3) > label > input"
# Tombol Change & Activate
_SEL_MT_CHANGE_BTN      = "#modalChange"
_SEL_MT_SELECTED_EMAIL  = "#selectedEmail"
_SEL_MT_ACTIVATE_BTN    = "#emailActivationModal > div > div > div.modal-footer.text-center > a"
# Tombol buka modal (biasanya tombol di header mailticking)
_SEL_MT_OPEN_MODAL      = "#changeEmailBtn, .change-email-btn, [data-target='#emailActivationModal'], [data-bs-target='#emailActivationModal']"

_GMAIL_DOMAINS = ["@gmail.com", "@googlemail.com", "@gmail.", "@googlemail."]

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


def _is_gmail_email(email: str) -> bool:
    email_lower = email.lower()
    return any(email_lower.endswith(d.rstrip('.')) or d in email_lower for d in _GMAIL_DOMAINS)


def _wait_for_css(driver, selector, timeout=15, visible=False):
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


def _is_checked(driver, selector) -> bool:
    """Return True jika checkbox CSS selector dalam keadaan checked."""
    try:
        el = driver.find_element(By.CSS_SELECTOR, selector)
        return el.is_selected()
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

        # ──────────────────────────────────────────────────────────────────
        # STEP 1: Buka business.gemini.google
        # ──────────────────────────────────────────────────────────────────
        self._log("Step 1: Buka business.gemini.google")
        try:
            driver.get(GEMINI_HOME_URL)
            WebDriverWait(driver, 20).until(lambda d: d.current_url != "about:blank")
        except Exception:
            pass
        gemini_tab = driver.current_window_handle

        # ──────────────────────────────────────────────────────────────────
        # STEP 2: Buka mailticking.com di tab baru
        # ──────────────────────────────────────────────────────────────────
        self._log("Step 2: Buka mailticking.com")
        driver.execute_script("window.open('about:blank', '_blank');")
        time.sleep(0.5)
        driver.switch_to.window(driver.window_handles[-1])
        mail_tab = driver.current_window_handle
        driver.get(MAILTICKING_URL)
        self._wait_page_ready(driver, timeout=30, label="mailticking.com")
        time.sleep(1)

        # Buka modal email activation
        self._log("Step 2: Buka modal email activation")
        modal_opened = False

        # Coba klik tombol buka modal
        for sel in [
            _SEL_MT_OPEN_MODAL,
            "button[data-target='#emailActivationModal']",
            "a[data-target='#emailActivationModal']",
            "[data-bs-toggle='modal'][data-bs-target='#emailActivationModal']",
            ".change-email",
        ]:
            try:
                els = driver.find_elements(By.CSS_SELECTOR, sel)
                for el in els:
                    if el.is_displayed():
                        driver.execute_script("arguments[0].click();", el)
                        modal_opened = True
                        break
            except Exception:
                pass
            if modal_opened:
                break

        # Fallback: JS Bootstrap modal show
        if not modal_opened:
            try:
                driver.execute_script(
                    "var m = document.querySelector('#emailActivationModal');"
                    "if(m){ var bsModal = bootstrap.Modal.getOrCreateInstance(m); bsModal.show(); }"
                )
                modal_opened = True
                self._log("Step 2: Modal dibuka via JS Bootstrap")
            except Exception:
                pass

        # Tunggu modal muncul
        modal_el = _wait_for_css(driver, "#emailActivationModal", timeout=10, visible=True)
        if not modal_el:
            self._log("Step 2: Modal tidak muncul, coba JS show", "WARNING")
            try:
                driver.execute_script(
                    "var m = document.querySelector('#emailActivationModal');"
                    "if(m){ m.style.display='block'; m.classList.add('show'); }"
                )
                time.sleep(0.5)
            except Exception:
                pass

        time.sleep(0.8)

        # Uncheck @gmail (div:nth-child(3) > label)
        self._log("Step 2: Uncheck @gmail")
        self._uncheck_label(driver, _SEL_MT_LABEL_GMAIL)

        # Uncheck @googlemail (div:nth-child(2) > label) jika ada
        self._log("Step 2: Uncheck @googlemail (jika ada)")
        self._uncheck_label(driver, _SEL_MT_LABEL_GOOGLEMAIL)

        # Pastikan @domain.com (div:nth-child(1) > label) tetap checked
        self._log("Step 2: Pastikan @domain.com checked")
        self._ensure_checked(driver, _SEL_MT_LABEL_DOMAIN)

        # ──────────────────────────────────────────────────────────────────
        # STEP 3: Klik Change, pastikan email bukan gmail, klik Activate
        # ──────────────────────────────────────────────────────────────────
        self._log("Step 3: Klik #modalChange")
        change_ok = _css_click(driver, _SEL_MT_CHANGE_BTN, timeout=10, js_click=True)
        if not change_ok:
            self._log("Step 3: #modalChange tidak ditemukan, coba fallback", "WARNING")
            try:
                # Cari tombol berteks 'change'
                for btn in driver.find_elements(By.TAG_NAME, "button"):
                    if "change" in (btn.text or "").lower() and btn.is_displayed():
                        driver.execute_script("arguments[0].click();", btn)
                        break
            except Exception:
                pass
        time.sleep(1)

        # Cek email hasil change di #selectedEmail
        email = ""
        for attempt in range(8):
            try:
                el = _wait_for_css(driver, _SEL_MT_SELECTED_EMAIL, timeout=5, visible=True)
                if el:
                    val = (el.text or el.get_attribute("value") or el.get_attribute("innerHTML") or "").strip()
                    # Bersihkan tag HTML jika ada
                    val = re.sub(r'<[^>]+>', '', val).strip()
                    if "@" in val:
                        email = val
                        break
            except Exception:
                pass
            time.sleep(1)

        if not email:
            self._log("Step 3: Email tidak ditemukan di #selectedEmail", "WARNING")
            # Fallback: ambil dari #active-mail
            try:
                el = _wait_for_css(driver, "#active-mail", timeout=5, visible=True)
                if el:
                    email = (el.text or "").strip()
            except Exception:
                pass

        self._log(f"Step 3: Email kandidat: {email}")

        # Jika masih gmail, tekan Change lagi sampai dapat non-gmail
        max_change = 10
        change_count = 0
        while email and _is_gmail_email(email) and change_count < max_change:
            self._log(f"Step 3: Email masih gmail ({email}), change lagi...", "WARNING")
            _css_click(driver, _SEL_MT_CHANGE_BTN, timeout=5, js_click=True)
            time.sleep(1.5)
            change_count += 1
            try:
                el = _wait_for_css(driver, _SEL_MT_SELECTED_EMAIL, timeout=4, visible=True)
                if el:
                    val = (el.text or el.get_attribute("value") or "").strip()
                    val = re.sub(r'<[^>]+>', '', val).strip()
                    if "@" in val:
                        email = val
            except Exception:
                pass

        if not email or _is_gmail_email(email):
            self._log(f"Step 3: Tidak bisa dapat email non-gmail setelah {max_change}x", "ERROR")
            self._debug_dump(driver, "no_nongmail_email")
            return False

        self._log(f"Step 3: Email non-gmail confirmed: {email}")

        # Klik Activate
        self._log("Step 3: Klik Activate")
        activate_ok = _css_click(driver, _SEL_MT_ACTIVATE_BTN, timeout=10, js_click=True)
        if not activate_ok:
            self._log("Step 3: Activate button tidak ditemukan, coba fallback", "WARNING")
            try:
                for a in driver.find_elements(By.TAG_NAME, "a"):
                    if "activate" in (a.text or "").lower() and a.is_displayed():
                        driver.execute_script("arguments[0].click();", a)
                        activate_ok = True
                        break
            except Exception:
                pass
        if activate_ok:
            self._log("Step 3: Activate diklik")
        else:
            self._log("Step 3: Activate tidak bisa diklik, lanjut...", "WARNING")
        time.sleep(1)

        # ──────────────────────────────────────────────────────────────────
        # STEP 4: Switch ke Gemini, input email ke #email-input
        # ──────────────────────────────────────────────────────────────────
        self._log(f"Step 4: Switch ke Gemini, input email: {email}")
        driver.switch_to.window(gemini_tab)

        # Tunggu #email-input
        if not _wait_for_css(driver, _SEL_EMAIL_INPUT, timeout=30, visible=True):
            self._log("Step 4: #email-input tidak muncul!", "ERROR")
            self._debug_dump(driver, "no_email_input")
            return False

        submitted = False
        for attempt in range(1, MAX_EMAIL_SUBMIT_RETRY + 1):
            self._log(f"Step 4: Submit email attempt {attempt}/{MAX_EMAIL_SUBMIT_RETRY}")

            if self._is_lets_try_error_page(driver):
                self._handle_lets_try_something_else(driver)
                time.sleep(1)
                continue

            if not _css_type(driver, _SEL_EMAIL_INPUT, email, timeout=15):
                self._log("Step 4: Tidak bisa ketik ke #email-input", "WARNING")
                self._debug_dump(driver, f"type_email_fail_{attempt}")
                time.sleep(2)
                driver.refresh()
                _wait_for_css(driver, _SEL_EMAIL_INPUT, timeout=20, visible=True)
                continue

            # Verifikasi isi
            try:
                el = driver.find_element(By.CSS_SELECTOR, _SEL_EMAIL_INPUT)
                actual = (el.get_attribute("value") or "").strip()
                if actual.lower() != email.lower():
                    self._log(f"Step 4: Mismatch: '{actual}' vs '{email}'", "WARNING")
                    driver.execute_script("arguments[0].value = '';", el)
                    continue
            except Exception:
                pass

            # Klik tombol login
            self._log("Step 4: Klik #log-in-button")
            if not _css_click(driver, _SEL_LOGIN_BTN, timeout=10, js_click=True):
                try:
                    el = driver.find_element(By.CSS_SELECTOR, _SEL_EMAIL_INPUT)
                    el.send_keys(Keys.RETURN)
                    self._log("Step 4: Fallback Enter key")
                except Exception:
                    pass

            time.sleep(2)
            if self._is_lets_try_error_page(driver):
                self._handle_lets_try_something_else(driver)
                continue

            submitted = True
            self._log(f"Step 4: Email submitted: {email}")
            break

        if not submitted:
            self._log("Step 4: Gagal submit email", "ERROR")
            return False

        # ──────────────────────────────────────────────────────────────────
        # STEP 5: Tunggu OTP page (#c2)
        # ──────────────────────────────────────────────────────────────────
        self._log("Step 5: Tunggu OTP page (#c2)...")
        self._wait_page_ready(driver, timeout=20, label="OTP Page")

        deadline = time.time() + 60
        while time.time() < deadline:
            try:
                url = driver.current_url.lower()
                if any(k in url for k in ["accountverification", "verify-oob-code", "oauth2", "signin-callback"]):
                    break
                if self._is_lets_try_error_page(driver):
                    self._log("Step 5: Error page pada OTP wait", "WARNING")
                    return False
            except Exception:
                pass
            time.sleep(1)

        code_sent_el = _wait_for_css(driver, _SEL_CODE_SENT, timeout=30, visible=False)
        if code_sent_el:
            self._log("Step 5: #c2 ditemukan - OTP page ready")
        else:
            self._log("Step 5: #c2 tidak ditemukan, lanjut...", "WARNING")

        # ──────────────────────────────────────────────────────────────────
        # STEP 6: Switch mailticking, tunggu email OTP masuk
        # ──────────────────────────────────────────────────────────────────
        self._log("Step 6: Switch mailticking, tunggu email OTP")
        driver.switch_to.window(mail_tab)

        otp_link = None
        deadline = time.time() + OTP_TIMEOUT
        while time.time() < deadline:
            try:
                el = _wait_for_css(
                    driver,
                    "#message-list > tr:nth-child(1) > td.col-6 > a",
                    timeout=3, visible=True
                )
                if el:
                    otp_link = el
                    self._log("Step 6: Email OTP ditemukan")
                    break
            except Exception:
                pass
            try:
                refresh_btn = driver.find_element(
                    By.CSS_SELECTOR,
                    "#refresh-btn, .refresh, [data-action='refresh']"
                )
                driver.execute_script("arguments[0].click();", refresh_btn)
            except Exception:
                pass
            time.sleep(3)

        if not otp_link:
            self._log("Step 6: Email OTP tidak datang (timeout)", "ERROR")
            return False

        try:
            driver.execute_script("arguments[0].click();", otp_link)
            time.sleep(2)
        except Exception:
            pass

        # ──────────────────────────────────────────────────────────────────
        # STEP 7: Ambil kode OTP
        # ──────────────────────────────────────────────────────────────────
        self._log("Step 7: Ambil kode verifikasi")
        _SEL_VERIF_CODE = (
            "#content-wrapper > table > tbody > tr > td > table > tbody "
            "> tr:nth-child(1) > td > table > tbody > tr > td "
            "> p.verification-code-container > span"
        )
        otp = ""
        for attempt in range(5):
            try:
                el = _wait_for_css(driver, _SEL_VERIF_CODE, timeout=5, visible=False)
                if el:
                    otp = (el.text or "").strip()
                    if otp and otp.isdigit() and len(otp) >= 4:
                        self._log(f"Step 7: OTP: {otp}")
                        break
            except Exception:
                pass
            time.sleep(2)

        if not otp:
            otp = self._mail_client.extract_verification_code(driver, mail_tab_handle=mail_tab)

        if not otp:
            self._log("Step 7: OTP tidak ditemukan", "ERROR")
            return False

        # ──────────────────────────────────────────────────────────────────
        # STEP 8: Input OTP ke Gemini
        # ──────────────────────────────────────────────────────────────────
        self._log(f"Step 8: Input OTP ke Gemini")
        driver.switch_to.window(gemini_tab)
        self._wait_page_ready(driver, timeout=15, label="Gemini OTP Form")
        time.sleep(1)

        otp_ok = False
        for attempt in range(1, 4):
            el = _wait_for_css(driver, _SEL_OTP_INPUT, timeout=10, visible=True)
            if not el:
                try:
                    inputs = driver.find_elements(By.CSS_SELECTOR, "input")
                    for inp in inputs:
                        if inp.is_displayed() and (inp.get_attribute("type") or "").lower() in ("text", "tel", "number", ""):
                            el = inp
                            break
                except Exception:
                    pass

            if not el:
                self._log(f"Step 8: OTP input tidak ditemukan (attempt {attempt}/3)", "WARNING")
                time.sleep(2)
                continue

            try:
                el.click()
                time.sleep(0.3)
                for char in otp:
                    ActionChains(driver).send_keys(char).perform()
                    time.sleep(random.uniform(0.12, 0.25))
                self._log(f"Step 8: OTP diketik: {otp}")
                otp_ok = True
                break
            except Exception as e:
                self._log(f"Step 8: Error ketik OTP attempt {attempt}: {e}", "WARNING")
                time.sleep(2)

        if not otp_ok:
            self._log("Step 8: Gagal input OTP", "ERROR")
            self._debug_dump(driver, "otp_type_failed")
            return False

        time.sleep(0.5)

        # ──────────────────────────────────────────────────────────────────
        # STEP 9: Klik Verify
        # ──────────────────────────────────────────────────────────────────
        self._log("Step 9: Klik tombol Verify")
        verify_ok = _css_click(driver, _SEL_VERIFY_BTN, timeout=10, js_click=True)
        if not verify_ok:
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
        if verify_ok:
            self._log("Step 9: Verify clicked")
        else:
            self._log("Step 9: Verify button tidak ditemukan", "WARNING")

        time.sleep(random.uniform(0.3, 0.6))

        # ──────────────────────────────────────────────────────────────────
        # STEP 10: Tunggu form nama & isi nama
        # ──────────────────────────────────────────────────────────────────
        self._log("Step 10: Tunggu form nama (#full-name-label)...")
        _wait_for_css(driver, _SEL_FULL_NAME_LABEL, timeout=30, visible=False)

        name = _random_name()
        name_ok = _css_type(driver, _SEL_NAME_INPUT, name, timeout=15)
        if not name_ok:
            for sel in ["input[formcontrolname='fullName']", "input[placeholder='Full name']"]:
                if _css_type(driver, sel, name, timeout=5):
                    name_ok = True
                    break
        if name_ok:
            self._log(f"Step 10: Nama diisi: {name}")
        else:
            self._log("Step 10: Nama tidak bisa diisi", "WARNING")

        # ──────────────────────────────────────────────────────────────────
        # STEP 11: Klik Agree & get started
        # ──────────────────────────────────────────────────────────────────
        self._log("Step 11: Klik Agree & get started")
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
            self._log("Step 11: Agree clicked")
        else:
            self._log("Step 11: Agree button tidak ditemukan", "WARNING")

        # ──────────────────────────────────────────────────────────────────
        # STEP 12: Tunggu loading selesai (h1 hilang)
        # ──────────────────────────────────────────────────────────────────
        self._log("Step 12: Tunggu sign-in selesai...")
        deadline = time.time() + 60
        while time.time() < deadline:
            try:
                h1 = driver.find_element(By.CSS_SELECTOR, _SEL_LOADING_H1)
                if not h1.is_displayed():
                    break
            except NoSuchElementException:
                break
            except Exception:
                break
            time.sleep(0.5)
        self._log("Step 12: Sign-in selesai")
        self._wait_page_ready(driver, timeout=20, label="Post-SignIn")

        # ── Step 13-15: Initial setup shadow DOM (dismiss popup, tools, veo)
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
    # Mailticking checkbox helpers
    # =========================================================================

    def _uncheck_label(self, driver, label_selector: str):
        """Uncheck checkbox dengan mengklik label, hanya jika saat ini checked."""
        try:
            label = _wait_for_css(driver, label_selector, timeout=5, visible=True)
            if not label:
                return
            # Cari checkbox di dalam atau sebelum label
            chk = None
            try:
                chk = label.find_element(By.CSS_SELECTOR, "input[type='checkbox']")
            except Exception:
                pass
            if chk is None:
                # Coba cari input sibling
                try:
                    parent = label.find_element(By.XPATH, "..")
                    chk = parent.find_element(By.CSS_SELECTOR, "input[type='checkbox']")
                except Exception:
                    pass
            if chk and chk.is_selected():
                driver.execute_script("arguments[0].click();", label)
                time.sleep(0.3)
                self._log(f"Unchecked: {label_selector}")
            elif chk and not chk.is_selected():
                self._log(f"Already unchecked: {label_selector}")
            else:
                # Tidak bisa deteksi status, klik label saja dan lihat
                # Cek via aria-checked atau class
                try:
                    cls = (label.get_attribute("class") or "").lower()
                    checked_via_class = "checked" in cls or "active" in cls
                    if checked_via_class:
                        driver.execute_script("arguments[0].click();", label)
                        self._log(f"Unchecked via class: {label_selector}")
                except Exception:
                    pass
        except Exception as e:
            self._log(f"_uncheck_label error ({label_selector}): {e}", "WARNING")

    def _ensure_checked(self, driver, label_selector: str):
        """Pastikan checkbox dalam keadaan checked."""
        try:
            label = _wait_for_css(driver, label_selector, timeout=5, visible=True)
            if not label:
                return
            chk = None
            try:
                chk = label.find_element(By.CSS_SELECTOR, "input[type='checkbox']")
            except Exception:
                pass
            if chk is None:
                try:
                    parent = label.find_element(By.XPATH, "..")
                    chk = parent.find_element(By.CSS_SELECTOR, "input[type='checkbox']")
                except Exception:
                    pass
            if chk and not chk.is_selected():
                driver.execute_script("arguments[0].click();", label)
                time.sleep(0.3)
                self._log(f"Checked: {label_selector}")
            else:
                self._log(f"Already checked: {label_selector}")
        except Exception as e:
            self._log(f"_ensure_checked error ({label_selector}): {e}", "WARNING")

    # =========================================================================
    # Shadow DOM helpers
    # =========================================================================

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
        time.sleep(1)

    def _initial_setup(self, driver):
        try:
            self._log(f"[SETUP] URL: {driver.current_url}")
        except Exception:
            pass

        self._log("Step 13 (shadow): Dismiss popup 'I'll do this later'...")
        dismissed = False
        for attempt in range(1, 4):
            try:
                if driver.execute_script(_JS_DISMISS_POPUP):
                    self._log("Step 13: Popup dismissed")
                    dismissed = True
                    break
            except Exception as e:
                self._log(f"Step 13 attempt {attempt}/3: {e}", "WARNING")
                time.sleep(2)
        if not dismissed:
            self._log("Step 13: Popup tidak ditemukan, lanjut...", "WARNING")
        self._wait_page_ready(driver, timeout=15, label="Post-Dismiss")

        deadline = time.time() + 20
        while time.time() < deadline:
            try:
                if driver.execute_script(self._JS_WAIT_SHADOW_READY):
                    break
            except Exception:
                pass
            time.sleep(0.5)
        time.sleep(0.5)

        self._log("Step 14 (shadow): Klik tools button...")
        tools_clicked = False
        for attempt in range(1, 6):
            try:
                result = driver.execute_script(_JS_CLICK_TOOLS)
                if result:
                    self._log(f"Step 14: Tools clicked (attempt {attempt})")
                    tools_clicked = True
                    break
                else:
                    self._log(f"Step 14: Falsy (attempt {attempt}/5)", "WARNING")
                    try:
                        btns = driver.execute_script(_JS_LIST_BUTTONS)
                        self._log(f"[DEBUG] Buttons: {(btns or 'none')[:300]}")
                    except Exception:
                        pass
            except Exception as e:
                self._log(f"Step 14 attempt {attempt}/5: {e}", "WARNING")
            if attempt < 5:
                time.sleep(3)

        if not tools_clicked:
            self._log("Step 14: Tools button tidak ditemukan!", "WARNING")
            self._debug_dump(driver, "tools_not_found")
            return

        time.sleep(1.5)

        self._log("Step 15 (shadow): Pilih 'Create videos with Veo'...")
        veo_clicked = False
        for attempt in range(1, 6):
            try:
                result = driver.execute_script(_JS_CLICK_VEO)
                if result:
                    self._log("Step 15: Veo diklik")
                    veo_clicked = True
                    break
                self._log(f"Step 15: Falsy (attempt {attempt}/5)", "WARNING")
            except Exception as e:
                self._log(f"Step 15 attempt {attempt}/5: {e}", "WARNING")
            if not veo_clicked and attempt < 5:
                time.sleep(2)
                try:
                    driver.execute_script(_JS_CLICK_TOOLS)
                    time.sleep(1.5)
                except Exception:
                    pass

        if not veo_clicked:
            self._log("Step 15: Veo tidak ditemukan!", "WARNING")
            self._debug_dump(driver, "veo_not_found")

        self._wait_page_ready(driver, timeout=15, label="Post-Veo")
        self._log("Step 15: Initial setup selesai!")

    # =========================================================================
    # Misc helpers
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

    def _is_error_page(self, driver) -> bool:
        try:
            src = driver.page_source.lower()
            return any(k in src for k in ["something went wrong", "couldn't sign", "error occurred"])
        except Exception:
            return False
