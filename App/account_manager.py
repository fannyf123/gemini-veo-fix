"""
account_manager.py

Flow:
  Step 1  : Buka business.gemini.google
  Step 2  : Buka mailticking.com
            - Uncheck div:nth-child(2),(3),(4) — @gmail / @googlemail / lainnya
            - Sisakan div:nth-child(1) — @domain.com
  Step 3  : Klik #modalChange, pastikan non-gmail, klik Activate
  Step 4  : Input email ke #email-input + klik login
  Step 5  : Tunggu URL verification page (tanpa tunggu #c2)
  Step 6  : Baca inbox mailticking, buka email OTP
  Step 7  : Ambil kode OTP dari span
  Step 8  : Input OTP ke Gemini
  Step 9  : Klik Verify
  Step 10 : Isi nama #mat-input-0
  Step 11 : Klik Agree
  Step 12 : Tunggu loading selesai
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

# ── Gemini selectors ──────────────────────────────────────────────────────────
_SEL_EMAIL_INPUT     = "#email-input"
_SEL_LOGIN_BTN       = "#log-in-button > span.UywwFc-RLmnJb"
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

# ── Mailticking selectors ─────────────────────────────────────────────────────
_SEL_MT_MODAL_BODY   = (
    "#emailActivationModal > div > div "
    "> div.modal-body.pt-4 > div > div > div > div.form-group"
)
# 4 ceklist: nth-child(1)=@domain.com (sisakan), (2)(3)(4)=uncheck
_SEL_MT_LABEL_1      = _SEL_MT_MODAL_BODY + " > div:nth-child(1) > label"  # @domain.com — sisakan
_SEL_MT_LABEL_2      = _SEL_MT_MODAL_BODY + " > div:nth-child(2) > label"  # uncheck
_SEL_MT_LABEL_3      = _SEL_MT_MODAL_BODY + " > div:nth-child(3) > label"  # uncheck (@gmail)
_SEL_MT_LABEL_4      = _SEL_MT_MODAL_BODY + " > div:nth-child(4) > label"  # uncheck (@googlemail)

_SEL_MT_CHANGE_BTN   = "#modalChange"
_SEL_MT_SELECTED     = "#selectedEmail"
_SEL_MT_ACTIVATE_BTN = "#emailActivationModal > div > div > div.modal-footer.text-center > a"
_SEL_MT_OPEN_MODAL   = (
    "#changeEmailBtn, .change-email-btn, "
    "[data-target='#emailActivationModal'], "
    "[data-bs-target='#emailActivationModal']"
)

_SEL_VERIF_CODE = (
    "#content-wrapper > table > tbody > tr > td > table > tbody "
    "> tr:nth-child(1) > td > table > tbody > tr > td "
    "> p.verification-code-container > span"
)

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
    low = email.lower()
    return any(low.endswith(d.rstrip('.')) or d in low for d in _GMAIL_DOMAINS)


def _wait_for_css(driver, selector, timeout=15, visible=False):
    try:
        cond = (
            EC.visibility_of_element_located((By.CSS_SELECTOR, selector))
            if visible else
            EC.presence_of_element_located((By.CSS_SELECTOR, selector))
        )
        return WebDriverWait(driver, timeout).until(cond)
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

        # ─────────────────────────────────────────────────────────────────────
        # STEP 1: Buka business.gemini.google
        # ─────────────────────────────────────────────────────────────────────
        self._log("Step 1: Buka business.gemini.google")
        try:
            driver.get(GEMINI_HOME_URL)
            WebDriverWait(driver, 20).until(lambda d: d.current_url != "about:blank")
        except Exception:
            pass
        gemini_tab = driver.current_window_handle

        # ─────────────────────────────────────────────────────────────────────
        # STEP 2: Buka mailticking, uncheck 3 format, sisakan @domain.com
        # ─────────────────────────────────────────────────────────────────────
        self._log("Step 2: Buka mailticking.com")
        driver.execute_script("window.open('about:blank', '_blank');")
        time.sleep(0.5)
        driver.switch_to.window(driver.window_handles[-1])
        mail_tab = driver.current_window_handle
        driver.get(MAILTICKING_URL)
        self._wait_page_ready(driver, timeout=30, label="mailticking.com")
        time.sleep(1)

        # Buka modal
        self._log("Step 2: Buka #emailActivationModal")
        modal_opened = False
        for sel in [
            _SEL_MT_OPEN_MODAL,
            "button[data-target='#emailActivationModal']",
            "a[data-target='#emailActivationModal']",
            "[data-bs-toggle='modal'][data-bs-target='#emailActivationModal']",
            ".change-email",
        ]:
            try:
                for el in driver.find_elements(By.CSS_SELECTOR, sel):
                    if el.is_displayed():
                        driver.execute_script("arguments[0].click();", el)
                        modal_opened = True
                        break
            except Exception:
                pass
            if modal_opened:
                break

        if not modal_opened:
            try:
                driver.execute_script(
                    "var m=document.querySelector('#emailActivationModal');"
                    "if(m){bootstrap.Modal.getOrCreateInstance(m).show();}"
                )
                modal_opened = True
                self._log("Step 2: Modal dibuka via JS Bootstrap")
            except Exception:
                pass

        if not _wait_for_css(driver, "#emailActivationModal", timeout=10, visible=True):
            self._log("Step 2: Modal tidak muncul, force show", "WARNING")
            try:
                driver.execute_script(
                    "var m=document.querySelector('#emailActivationModal');"
                    "if(m){m.style.display='block';m.classList.add('show');}"
                )
            except Exception:
                pass
        time.sleep(0.8)

        # Uncheck semua kecuali nth-child(1) = @domain.com
        self._log("Step 2: Uncheck div:nth-child(2)")
        self._uncheck_label(driver, _SEL_MT_LABEL_2)
        self._log("Step 2: Uncheck div:nth-child(3) @gmail")
        self._uncheck_label(driver, _SEL_MT_LABEL_3)
        self._log("Step 2: Uncheck div:nth-child(4) @googlemail")
        self._uncheck_label(driver, _SEL_MT_LABEL_4)
        self._log("Step 2: Pastikan div:nth-child(1) @domain.com checked")
        self._ensure_checked(driver, _SEL_MT_LABEL_1)

        # ─────────────────────────────────────────────────────────────────────
        # STEP 3: Klik Change → verify non-gmail → Activate
        # ─────────────────────────────────────────────────────────────────────
        self._log("Step 3: Klik #modalChange")
        if not _css_click(driver, _SEL_MT_CHANGE_BTN, timeout=10, js_click=True):
            self._log("Step 3: Fallback cari tombol 'change'", "WARNING")
            try:
                for btn in driver.find_elements(By.TAG_NAME, "button"):
                    if "change" in (btn.text or "").lower() and btn.is_displayed():
                        driver.execute_script("arguments[0].click();", btn)
                        break
            except Exception:
                pass
        time.sleep(1)

        email = ""
        for _ in range(8):
            try:
                el = _wait_for_css(driver, _SEL_MT_SELECTED, timeout=5, visible=True)
                if el:
                    val = re.sub(
                        r'<[^>]+>', '',
                        (el.text or el.get_attribute("value") or el.get_attribute("innerHTML") or "")
                    ).strip()
                    if "@" in val:
                        email = val
                        break
            except Exception:
                pass
            time.sleep(1)

        if not email:
            try:
                el = _wait_for_css(driver, "#active-mail", timeout=5, visible=True)
                if el:
                    email = (el.text or "").strip()
            except Exception:
                pass

        self._log(f"Step 3: Email kandidat: {email}")

        # Auto-loop jika masih gmail
        for i in range(10):
            if not email or not _is_gmail_email(email):
                break
            self._log(f"Step 3: Masih gmail ({email}), change lagi ({i+1}/10)", "WARNING")
            _css_click(driver, _SEL_MT_CHANGE_BTN, timeout=5, js_click=True)
            time.sleep(1.5)
            try:
                el = _wait_for_css(driver, _SEL_MT_SELECTED, timeout=4, visible=True)
                if el:
                    val = re.sub(r'<[^>]+>', '', (el.text or el.get_attribute("value") or "")).strip()
                    if "@" in val:
                        email = val
            except Exception:
                pass

        if not email or _is_gmail_email(email):
            self._log("Step 3: Tidak bisa dapat email non-gmail", "ERROR")
            self._debug_dump(driver, "no_nongmail_email")
            return False

        self._log(f"Step 3: Email non-gmail: {email}")

        self._log("Step 3: Klik Activate")
        if not _css_click(driver, _SEL_MT_ACTIVATE_BTN, timeout=10, js_click=True):
            self._log("Step 3: Fallback cari link 'activate'", "WARNING")
            try:
                for a in driver.find_elements(By.TAG_NAME, "a"):
                    if "activate" in (a.text or "").lower() and a.is_displayed():
                        driver.execute_script("arguments[0].click();", a)
                        break
            except Exception:
                pass
        time.sleep(1)

        # ─────────────────────────────────────────────────────────────────────
        # STEP 4: Switch ke Gemini, input email
        # ─────────────────────────────────────────────────────────────────────
        self._log(f"Step 4: Input email ke Gemini: {email}")
        driver.switch_to.window(gemini_tab)

        if not _wait_for_css(driver, _SEL_EMAIL_INPUT, timeout=30, visible=True):
            self._log("Step 4: #email-input tidak muncul!", "ERROR")
            self._debug_dump(driver, "no_email_input")
            return False

        submitted = False
        for attempt in range(1, MAX_EMAIL_SUBMIT_RETRY + 1):
            self._log(f"Step 4: Attempt {attempt}/{MAX_EMAIL_SUBMIT_RETRY}")

            if self._is_lets_try_error_page(driver):
                self._handle_lets_try_something_else(driver)
                time.sleep(1)
                continue

            if not _css_type(driver, _SEL_EMAIL_INPUT, email, timeout=15):
                self._log("Step 4: Gagal ketik email", "WARNING")
                time.sleep(2)
                driver.refresh()
                _wait_for_css(driver, _SEL_EMAIL_INPUT, timeout=20, visible=True)
                continue

            try:
                el = driver.find_element(By.CSS_SELECTOR, _SEL_EMAIL_INPUT)
                actual = (el.get_attribute("value") or "").strip()
                if actual.lower() != email.lower():
                    self._log(f"Step 4: Mismatch '{actual}' vs '{email}'", "WARNING")
                    driver.execute_script("arguments[0].value='';", el)
                    continue
            except Exception:
                pass

            if not _css_click(driver, _SEL_LOGIN_BTN, timeout=10, js_click=True):
                try:
                    driver.find_element(By.CSS_SELECTOR, _SEL_EMAIL_INPUT).send_keys(Keys.RETURN)
                    self._log("Step 4: Fallback Enter")
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

        # ─────────────────────────────────────────────────────────────────────
        # STEP 5: Tunggu URL verification page (tanpa tunggu #c2)
        # ─────────────────────────────────────────────────────────────────────
        self._log("Step 5: Tunggu URL verification page...")
        self._wait_page_ready(driver, timeout=20, label="OTP Page")

        deadline = time.time() + 60
        while time.time() < deadline:
            try:
                url = driver.current_url.lower()
                if any(k in url for k in ["accountverification", "verify-oob-code", "oauth2", "signin-callback"]):
                    self._log("Step 5: Verification URL terdeteksi")
                    break
                if self._is_lets_try_error_page(driver):
                    self._log("Step 5: Error page pada OTP wait", "WARNING")
                    return False
            except Exception:
                pass
            time.sleep(1)

        # ─────────────────────────────────────────────────────────────────────
        # STEP 6: Switch mailticking, tunggu email OTP
        # ─────────────────────────────────────────────────────────────────────
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
                rb = driver.find_element(By.CSS_SELECTOR, "#refresh-btn, .refresh, [data-action='refresh']")
                driver.execute_script("arguments[0].click();", rb)
            except Exception:
                pass
            time.sleep(3)

        if not otp_link:
            self._log("Step 6: Email OTP timeout", "ERROR")
            return False

        try:
            driver.execute_script("arguments[0].click();", otp_link)
            time.sleep(2)
        except Exception:
            pass

        # ─────────────────────────────────────────────────────────────────────
        # STEP 7: Ambil kode OTP
        # ─────────────────────────────────────────────────────────────────────
        self._log("Step 7: Ambil kode OTP")
        otp = ""
        for _ in range(5):
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

        # ─────────────────────────────────────────────────────────────────────
        # STEP 8: Input OTP ke Gemini
        # ─────────────────────────────────────────────────────────────────────
        self._log("Step 8: Input OTP ke Gemini")
        driver.switch_to.window(gemini_tab)
        self._wait_page_ready(driver, timeout=15, label="Gemini OTP Form")
        time.sleep(1)

        otp_ok = False
        for attempt in range(1, 4):
            el = _wait_for_css(driver, _SEL_OTP_INPUT, timeout=10, visible=True)
            if not el:
                try:
                    for inp in driver.find_elements(By.CSS_SELECTOR, "input"):
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
                self._log(f"Step 8: Error attempt {attempt}: {e}", "WARNING")
                time.sleep(2)

        if not otp_ok:
            self._log("Step 8: Gagal input OTP", "ERROR")
            self._debug_dump(driver, "otp_type_failed")
            return False

        time.sleep(0.5)

        # ─────────────────────────────────────────────────────────────────────
        # STEP 9: Klik Verify
        # ─────────────────────────────────────────────────────────────────────
        self._log("Step 9: Klik Verify")
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
        self._log("Step 9: Verify clicked" if verify_ok else "Step 9: Verify button tidak ditemukan", "INFO" if verify_ok else "WARNING")
        time.sleep(random.uniform(0.3, 0.6))

        # ─────────────────────────────────────────────────────────────────────
        # STEP 10: Isi nama
        # ─────────────────────────────────────────────────────────────────────
        self._log("Step 10: Tunggu form nama")
        _wait_for_css(driver, _SEL_FULL_NAME_LABEL, timeout=30, visible=False)
        name = _random_name()
        name_ok = _css_type(driver, _SEL_NAME_INPUT, name, timeout=15)
        if not name_ok:
            for sel in ["input[formcontrolname='fullName']", "input[placeholder='Full name']"]:
                if _css_type(driver, sel, name, timeout=5):
                    name_ok = True
                    break
        self._log(f"Step 10: Nama={'diisi: ' + name if name_ok else 'gagal diisi'}")

        # ─────────────────────────────────────────────────────────────────────
        # STEP 11: Klik Agree
        # ─────────────────────────────────────────────────────────────────────
        self._log("Step 11: Klik Agree")
        agree_ok = _css_click(driver, _SEL_AGREE_BTN, timeout=15, js_click=True)
        if not agree_ok:
            for sel in [".mdc-button__label", "button.mdc-button", "button[mat-flat-button]"]:
                try:
                    for el in driver.find_elements(By.CSS_SELECTOR, sel):
                        if any(w in (el.text or "").lower() for w in ["agree", "get started"]) and el.is_displayed():
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
        self._log("Step 11: Agree clicked" if agree_ok else "Step 11: Agree tidak ditemukan",
                  "INFO" if agree_ok else "WARNING")

        # ─────────────────────────────────────────────────────────────────────
        # STEP 12: Tunggu loading selesai
        # ─────────────────────────────────────────────────────────────────────
        self._log("Step 12: Tunggu loading selesai (h1 hilang)...")
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

        # ── Shadow DOM setup (popup dismiss, tools, veo)
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
    # Checkbox helpers
    # =========================================================================

    def _uncheck_label(self, driver, label_selector: str):
        """Uncheck checkbox jika saat ini checked."""
        try:
            label = _wait_for_css(driver, label_selector, timeout=5, visible=True)
            if not label:
                self._log(f"Label tidak ditemukan: {label_selector}", "WARNING")
                return
            chk = None
            try:
                chk = label.find_element(By.CSS_SELECTOR, "input[type='checkbox']")
            except Exception:
                pass
            if chk is None:
                try:
                    chk = label.find_element(By.XPATH, "../input[@type='checkbox']")
                except Exception:
                    pass
            if chk is not None:
                if chk.is_selected():
                    driver.execute_script("arguments[0].click();", label)
                    time.sleep(0.3)
                    self._log(f"Unchecked: {label_selector}")
                else:
                    self._log(f"Already unchecked: {label_selector}")
            else:
                cls = (label.get_attribute("class") or "").lower()
                if "checked" in cls or "active" in cls:
                    driver.execute_script("arguments[0].click();", label)
                    self._log(f"Unchecked via class: {label_selector}")
        except Exception as e:
            self._log(f"_uncheck_label error ({label_selector}): {e}", "WARNING")

    def _ensure_checked(self, driver, label_selector: str):
        """Pastikan checkbox checked."""
        try:
            label = _wait_for_css(driver, label_selector, timeout=5, visible=True)
            if not label:
                self._log(f"Label tidak ditemukan: {label_selector}", "WARNING")
                return
            chk = None
            try:
                chk = label.find_element(By.CSS_SELECTOR, "input[type='checkbox']")
            except Exception:
                pass
            if chk is None:
                try:
                    chk = label.find_element(By.XPATH, "../input[@type='checkbox']")
                except Exception:
                    pass
            if chk is not None:
                if not chk.is_selected():
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
    (function(){
        function scan(root,depth){
            if(depth>10)return false;
            if(root.querySelector&&(
                root.querySelector("#tool-selector-menu-anchor")||
                root.querySelector(".omnibox-tools-selector")||
                root.querySelector(".tools-button-container")
            ))return true;
            var all=root.querySelectorAll?root.querySelectorAll('*'):[];
            for(var i=0;i<all.length;i++){
                if(all[i].shadowRoot&&scan(all[i].shadowRoot,depth+1))return true;
            }
            return false;
        }
        return scan(document,0);
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
                if driver.execute_script("return document.querySelector('body > ucs-standalone-app');"):
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

        self._log("Shadow Step 1: Dismiss popup...")
        dismissed = False
        for attempt in range(1, 4):
            try:
                if driver.execute_script(_JS_DISMISS_POPUP):
                    self._log("Shadow Step 1: Popup dismissed")
                    dismissed = True
                    break
            except Exception as e:
                self._log(f"Shadow Step 1 attempt {attempt}/3: {e}", "WARNING")
                time.sleep(2)
        if not dismissed:
            self._log("Shadow Step 1: Popup tidak ditemukan, lanjut...", "WARNING")
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

        self._log("Shadow Step 2: Klik tools button...")
        tools_clicked = False
        for attempt in range(1, 6):
            try:
                if driver.execute_script(_JS_CLICK_TOOLS):
                    self._log(f"Shadow Step 2: Tools clicked (attempt {attempt})")
                    tools_clicked = True
                    break
                self._log(f"Shadow Step 2: Falsy (attempt {attempt}/5)", "WARNING")
                try:
                    self._log(f"[DEBUG] Buttons: {str(driver.execute_script(_JS_LIST_BUTTONS) or '')[:300]}")
                except Exception:
                    pass
            except Exception as e:
                self._log(f"Shadow Step 2 attempt {attempt}/5: {e}", "WARNING")
            if attempt < 5:
                time.sleep(3)

        if not tools_clicked:
            self._log("Shadow Step 2: Tools button tidak ditemukan!", "WARNING")
            self._debug_dump(driver, "tools_not_found")
            return

        time.sleep(1.5)

        self._log("Shadow Step 3: Pilih Veo...")
        veo_clicked = False
        for attempt in range(1, 6):
            try:
                if driver.execute_script(_JS_CLICK_VEO):
                    self._log("Shadow Step 3: Veo diklik")
                    veo_clicked = True
                    break
                self._log(f"Shadow Step 3: Falsy (attempt {attempt}/5)", "WARNING")
            except Exception as e:
                self._log(f"Shadow Step 3 attempt {attempt}/5: {e}", "WARNING")
            if not veo_clicked and attempt < 5:
                time.sleep(2)
                try:
                    driver.execute_script(_JS_CLICK_TOOLS)
                    time.sleep(1.5)
                except Exception:
                    pass

        if not veo_clicked:
            self._log("Shadow Step 3: Veo tidak ditemukan!", "WARNING")
            self._debug_dump(driver, "veo_not_found")

        self._wait_page_ready(driver, timeout=15, label="Post-Veo")
        self._log("Shadow setup selesai!")

    # =========================================================================
    # Misc helpers
    # =========================================================================

    def _is_lets_try_error_page(self, driver) -> bool:
        try:
            return any(k in driver.page_source.lower() for k in _ERROR_PAGE_INDICATORS)
        except Exception:
            return False

    def _handle_lets_try_something_else(self, driver) -> bool:
        self._log("[!] Error page, navigasi ulang...", "WARNING")
        self._debug_dump(driver, "error_page")
        try:
            driver.get(GEMINI_HOME_URL)
            _wait_for_css(driver, _SEL_EMAIL_INPUT, timeout=20, visible=True)
        except Exception:
            pass
        return True

    def _is_error_page(self, driver) -> bool:
        try:
            return any(k in driver.page_source.lower() for k in
                       ["something went wrong", "couldn't sign", "error occurred"])
        except Exception:
            return False
