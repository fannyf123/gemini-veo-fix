"""
mailticking.py

Otomasi mailticking.com sesuai tampilan nyata:

  Modal popup muncul otomatis saat halaman load:
  +------------------------------------------+
  | Your Temp Email is Ready                 |
  | [doalbon567@gongjua.com] [change v]      |
  |  [x] abc@domain.com      <- HANYA ini   |
  |  [ ] a.b.c@gmail.com     <- uncheck     |
  |  [ ] abc@gmail.com       <- uncheck     |
  |  [ ] abc+d@gmail.com     <- uncheck     |
  |  [ ] abc@googlemail.com  <- uncheck     |
  |          [Activate]                     |
  +------------------------------------------+

  Setelah Activate:
  +------------------------------------------+
  | [doalbon567@gongjua.com] [change v]      |
  | SENDER          | SUBJECT         | TIME |
  | noreply-google  | Gemini Enterp.. | 12:51|
  | [ Check emails button ]                  |
  +------------------------------------------+

EXACT JS PATH dari inspect element:
  Step 3  - Checkbox type4:
    document.querySelector("#type4")

  Step 4a - Tombol Change:
    document.querySelector("#modalChange")

  Step 4b - Tombol Activate:
    document.querySelector("#emailActivationModal > div > div > div.modal-footer.text-center > a")

  Email link di inbox:
    <a href="/mail/view/{hash}/" rel="nofollow">Gemini Enterprise verification code</a>

  OTP span:
    <span class="verification-code" style="font-size:28px;...color:#1c3a70;...background-color:#eaf2ff;">
"""
import re
import time
import random
from typing import Optional, Callable

try:
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.common.exceptions import (
        TimeoutException, NoSuchElementException,
        ElementClickInterceptedException, ElementNotInteractableException,
        StaleElementReferenceException,
    )
    from bs4 import BeautifulSoup
except ImportError:
    pass

MAILTICKING_URL = "https://mailticking.com"

# Domain yang TIDAK boleh dipakai (Google akan reject)
BANNED_DOMAINS = {"@gmail.com", "@googlemail.com"}

OTP_BG_COLORS = {"#eaf2ff", "#e8f0fe", "#f1f8ff", "#e3f2fd", "#f0f4ff", "#dce8fc"}
OTP_TEXT_COLORS = {
    "#1c3a70", "#1a73e8", "#4285f4", "#1558d6", "#1967d2",
    "#185abc", "#174ea6", "#0d47a1",
}

# Polling: cek inbox setiap N detik (tidak perlu full refresh)
_INBOX_POLL_INTERVAL   = 0.8   # detik antar cek DOM
_INBOX_REFRESH_EVERY   = 6     # detik sebelum full page refresh
_OTP_WAIT_AFTER_CLICK  = 0.8   # detik tunggu setelah klik email link

# ── Exact CSS selectors dari JS path inspect element ─────────────────────────
_SEL_TYPE4_CHECKBOX = "#type4"
_SEL_CHANGE_BTN     = "#modalChange"
_SEL_ACTIVATE_BTN   = (
    "#emailActivationModal > div > div "
    "> div.modal-footer.text-center > a"
)
# ─────────────────────────────────────────────────────────────────────────────


def _is_banned_email(email: str) -> bool:
    low = email.lower().strip()
    return any(low.endswith(d) for d in BANNED_DOMAINS)


def _extract_otp_from_html(html: str) -> Optional[str]:
    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception:
        return None

    # 1. Exact class match
    for tag in soup.find_all("span", class_="verification-code"):
        text = re.sub(r'\s+', '', tag.get_text(strip=True))
        if re.fullmatch(r'[A-Z0-9]{4,8}', text, re.IGNORECASE):
            return text.upper()

    # 2. Style-based heuristic
    def _n(s):
        return s.lower().replace(" ", "").strip()

    def _is_otp_tag(tag) -> bool:
        style = _n(tag.get("style", "") or "")
        if not style:
            return False
        m = re.search(r'font-size:([\d.]+)(px|pt)', style)
        if m:
            val = float(m.group(1))
            px = val if m.group(2) == "px" else val * 1.333
            if px >= 20:
                return True
        for c in OTP_TEXT_COLORS:
            if _n(c) in style:
                return True
        for c in OTP_BG_COLORS:
            if _n(c) in style:
                return True
        if "letter-spacing" in style and "font-weight:bold" in style:
            return True
        return False

    for tag in soup.find_all(True):
        if _is_otp_tag(tag):
            text = re.sub(r'\s+', '', tag.get_text(strip=True))
            if re.fullmatch(r'[A-Z0-9]{4,8}', text, re.IGNORECASE):
                return text.upper()

    # 3. Standalone block
    STANDALONE = ["td", "div", "span", "p", "b", "strong", "h1", "h2", "h3"]
    SKIP_WORDS = {
        "THIS", "THAT", "FROM", "WITH", "YOUR", "EMAIL", "ALIAS",
        "SENT", "STOP", "LINK", "CLICK", "HERE", "MORE", "INFO",
        "GOOGLE", "GMAIL", "VERIFY", "GEMINI", "CLOUD", "SIGN",
    }
    for tag in soup.find_all(STANDALONE):
        text = re.sub(r'\s+', '', tag.get_text(strip=True))
        if re.fullmatch(r'[A-Z0-9]{4,8}', text, re.IGNORECASE):
            code = text.upper()
            if code not in SKIP_WORDS:
                return code

    # 4. Regex on plain text
    plain = soup.get_text(separator=" ")
    patterns = [
        r'(?:verification|one-time)\s+code[^A-Z0-9]{0,20}([A-Z0-9]{4,8})\b',
        r'Your\s+code\s+is[:\s]+([A-Z0-9]{4,8})\b',
        r'\b([0-9]{6})\b',
        r'\b([A-Z0-9]{6})\b',
    ]
    FALSE_YEARS = {str(y) for y in range(2018, 2032)}
    FOOTER_CTX  = ["copyright", "\u00a9", "google llc", "mountain view", "privacy", "terms"]
    for pat in patterns:
        for m in re.finditer(pat, plain, re.IGNORECASE):
            code = m.group(1).upper()
            if code in FALSE_YEARS:
                continue
            ctx = plain[max(0, m.start()-40):m.end()+20].lower()
            if any(k in ctx for k in FOOTER_CTX):
                continue
            if code not in SKIP_WORDS:
                return code

    return None


class MailtickingClient:

    def __init__(self, log_callback: Optional[Callable] = None):
        self._log_cb = log_callback

    def _log(self, msg: str, level: str = "INFO"):
        if self._log_cb:
            self._log_cb(msg, level)

    def _js_click(self, driver, element):
        driver.execute_script("arguments[0].click();", element)

    def _wait_page_ready(self, driver, timeout=30, label=""):
        tag = f" [{label}]" if label else ""
        try:
            WebDriverWait(driver, timeout).until(
                lambda d: d.execute_script("return document.readyState") == "complete"
            )
        except TimeoutException:
            self._log(f"Page readyState timeout{tag} ({timeout}s)", "WARNING")
        time.sleep(0.3)
        self._log(f"Page ready{tag}")

    def _safe_click(self, driver, element):
        for attempt in range(3):
            try:
                if attempt == 1:
                    driver.execute_script(
                        "arguments[0].scrollIntoView({block:'center'});", element)
                    time.sleep(0.2)
                if attempt == 2:
                    self._js_click(driver, element)
                    return
                element.click()
                return
            except (ElementClickInterceptedException,
                    ElementNotInteractableException,
                    StaleElementReferenceException):
                time.sleep(0.2)

    def _wait_for_modal(self, driver, timeout: int = 12) -> bool:
        try:
            WebDriverWait(driver, timeout).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, _SEL_ACTIVATE_BTN))
            )
            return True
        except TimeoutException:
            pass
        try:
            WebDriverWait(driver, 3).until(
                EC.visibility_of_element_located(
                    (By.CSS_SELECTOR, ".modal.show, .modal.in, .modal[style*='display: block']"))
            )
            return True
        except TimeoutException:
            pass
        return False

    # -------------------------------------------------------------------------
    def open_mailticking_tab(self, driver) -> str:
        self._log("Opening mailticking.com...")
        driver.execute_script("window.open('about:blank', '_blank');")
        time.sleep(0.3)
        driver.switch_to.window(driver.window_handles[-1])
        driver.get(MAILTICKING_URL)
        self._wait_page_ready(driver, timeout=30, label="mailticking.com")
        self._log("mailticking.com loaded.")
        return driver.current_window_handle

    # -------------------------------------------------------------------------
    def get_fresh_email(self, driver) -> str:
        modal_found = self._wait_for_modal(driver, timeout=12)
        if modal_found:
            self._log("Modal 'Your Temp Email is Ready' detected.")
        else:
            self._log("Modal not detected, proceeding anyway...", "WARNING")

        self._configure_checkboxes(driver)
        time.sleep(0.3)

        email = self._click_change_once(driver)
        self._log(f"Email ready after change: {email}")

        self._click_activate(driver)

        self._log("Waiting for page to reload after Activate...")
        self._wait_page_ready(driver, timeout=30, label="Post-Activate")

        final_email = self._read_email_from_navbar(driver) or email
        self._log(f"Temp email obtained: {final_email}")
        return final_email

    # -------------------------------------------------------------------------
    def _read_email_from_modal(self, driver) -> str:
        for sel in [
            ".modal input[type='text']",
            ".modal input[type='email']",
            ".modal input[readonly]",
            ".modal input",
            "input[type='text']",
            "input[type='email']",
            "input[readonly]",
            "#email",
        ]:
            try:
                el  = driver.find_element(By.CSS_SELECTOR, sel)
                val = (el.get_attribute("value") or el.text or "").strip()
                if "@" in val:
                    return val
            except Exception:
                pass
        try:
            m = re.search(
                r'value="([a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})"',
                driver.page_source
            )
            if m:
                return m.group(1)
        except Exception:
            pass
        return ""

    def _click_change_once(self, driver) -> str:
        CHANGE_SELECTORS = [
            _SEL_CHANGE_BTN,
            "button#modalChange",
            "button.btn-info#modalChange",
        ]

        def _find_change_btn():
            for sel in CHANGE_SELECTORS:
                try:
                    el = driver.find_element(By.CSS_SELECTOR, sel)
                    if el.is_displayed():
                        return el
                except Exception:
                    pass
            try:
                for btn in driver.find_elements(By.CSS_SELECTOR, "button.btn-info"):
                    if "change" in (btn.text or "").lower() and btn.is_displayed():
                        return btn
            except Exception:
                pass
            return None

        current_email = self._read_email_from_modal(driver)
        self._log(f"Current email before change: {current_email}")

        btn = _find_change_btn()
        if not btn:
            self._log("Change button tidak ditemukan", "WARNING")
            return current_email

        self._js_click(driver, btn)
        self._log("Clicked Change button once.")

        deadline = time.time() + 3
        while time.time() < deadline:
            time.sleep(0.3)
            new_email = self._read_email_from_modal(driver)
            if new_email and new_email != current_email:
                return new_email

        return self._read_email_from_modal(driver)

    # -------------------------------------------------------------------------
    def _configure_checkboxes(self, driver):
        try:
            cb = driver.find_element(By.CSS_SELECTOR, _SEL_TYPE4_CHECKBOX)
            if not cb.is_selected():
                self._js_click(driver, cb)
                time.sleep(0.15)
                self._log("Checked: abc@domain.com (#type4) via exact selector")
            else:
                self._log("Already checked: abc@domain.com (#type4)")
        except Exception as e:
            self._log(f"#type4 not found via exact selector: {e}", "WARNING")

        try:
            checkboxes = driver.find_elements(
                By.CSS_SELECTOR, "input[type='checkbox'][name='type']")
            if not checkboxes:
                checkboxes = driver.find_elements(
                    By.CSS_SELECTOR, "input[type='checkbox']")

            for cb in checkboxes:
                try:
                    cb_id = cb.get_attribute("id") or ""
                    if cb_id == "type4":
                        continue
                    if cb.is_selected():
                        self._js_click(driver, cb)
                        time.sleep(0.15)
                except (StaleElementReferenceException, Exception):
                    continue

            self._log("Checkboxes configured: only #type4 selected")
        except Exception as e:
            self._log(f"Checkbox uncheck error: {e}", "WARNING")

    def _read_current_email(self, driver) -> str:
        return self._read_email_from_modal(driver)

    def _read_email_from_navbar(self, driver) -> str:
        for sel in [
            "input[type='text']", "input[type='email']",
            "input[readonly]", ".navbar input",
            "nav input", "header input",
            "#email", ".email-display",
        ]:
            try:
                el  = driver.find_element(By.CSS_SELECTOR, sel)
                val = el.get_attribute("value") or el.text or ""
                if "@" in val:
                    return val.strip()
            except Exception:
                pass
        try:
            src = driver.page_source
            m = re.search(
                r'value="([a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})"', src)
            if m:
                return m.group(1)
        except Exception:
            pass
        return ""

    def _click_activate(self, driver):
        try:
            el = driver.find_element(By.CSS_SELECTOR, _SEL_ACTIVATE_BTN)
            self._js_click(driver, el)
            self._log("Clicked Activate button (exact path: #emailActivationModal > ... > a)")
            return
        except Exception as e:
            self._log(f"Activate exact path not found: {e}", "WARNING")

        for sel in [
            "a.activeBtn",
            "a.btn-warning.activeBtn",
            ".activeBtn",
            "a.btn.btn-warning.btn-lg",
        ]:
            try:
                el = driver.find_element(By.CSS_SELECTOR, sel)
                if el.is_displayed():
                    self._js_click(driver, el)
                    self._log(f"Clicked Activate button (fallback: {sel})")
                    return
            except Exception:
                pass

        for tag in ["a", "button"]:
            for el in driver.find_elements(By.TAG_NAME, tag):
                try:
                    if "activat" in el.text.lower() and el.is_displayed():
                        self._js_click(driver, el)
                        self._log(f"Clicked Activate button (text fallback: {tag})")
                        return
                except Exception:
                    pass

        self._log("Activate button not found", "WARNING")

    def _click_check_emails(self, driver) -> bool:
        for tag in ["button", "a"]:
            for el in driver.find_elements(By.TAG_NAME, tag):
                try:
                    txt = (el.text or "").lower()
                    if "check email" in txt and el.is_displayed():
                        self._js_click(driver, el)
                        return True
                except Exception:
                    pass
        return False

    def _find_gemini_row(self, driver):
        """
        EXACT: <a href="/mail/view/{hash}/" rel="nofollow">Gemini Enterprise verification code</a>
        """
        try:
            links = driver.find_elements(By.CSS_SELECTOR, "a[href*='/mail/view/']")
            for link in links:
                txt = (link.text or "").lower()
                if any(k in txt for k in ["gemini", "verification", "enterprise"]):
                    return link
            if links:
                return links[0]
        except Exception:
            pass
        KEYWORDS = ["gemini", "verification code", "enterprise", "noreply-googlecloud"]
        try:
            rows = driver.find_elements(By.CSS_SELECTOR, "table tbody tr")
            for row in rows:
                if any(k in (row.text or "").lower() for k in KEYWORDS):
                    return row
        except Exception:
            pass
        try:
            for sel in [".mail-item", ".inbox-item", "tr[onclick]", ".list-group-item"]:
                for el in driver.find_elements(By.CSS_SELECTOR, sel):
                    if any(k in (el.text or "").lower() for k in KEYWORDS):
                        return el
        except Exception:
            pass
        return None

    # -------------------------------------------------------------------------
    def wait_for_verification_email(
        self,
        driver,
        mail_tab_handle:   str,
        gemini_tab_handle: str,
        timeout:           int = 90,
    ) -> bool:
        """
        Fast polling: cek DOM setiap 0.8 detik.
        Full page refresh hanya dilakukan setiap _INBOX_REFRESH_EVERY detik.
        Tidak perlu wait_page_ready pada setiap loop.
        """
        self._log("Checking inbox for verification email...")
        driver.switch_to.window(mail_tab_handle)
        self._log("Switched to mailticking.com tab")

        start            = time.time()
        last_refresh_at  = start
        log_counter      = 0

        while time.time() - start < timeout:
            elapsed = time.time() - start

            # ── Full refresh setiap _INBOX_REFRESH_EVERY detik ──────────────
            if elapsed > 0 and (time.time() - last_refresh_at) >= _INBOX_REFRESH_EVERY:
                try:
                    driver.refresh()
                    # Cukup tunggu document.readyState saja, tanpa extra sleep
                    WebDriverWait(driver, 10).until(
                        lambda d: d.execute_script("return document.readyState") == "complete"
                    )
                    last_refresh_at = time.time()

                    # Re-dismiss activate modal jika muncul lagi
                    try:
                        act_btns = driver.find_elements(
                            By.CSS_SELECTOR,
                            f"{_SEL_ACTIVATE_BTN}, a.activeBtn, .activeBtn"
                        )
                        for b in act_btns:
                            if b.is_displayed():
                                self._js_click(driver, b)
                                time.sleep(0.3)
                                break
                    except Exception:
                        pass
                except Exception:
                    pass

            # ── Cek DOM langsung tanpa refresh ──────────────────────────────
            try:
                row = self._find_gemini_row(driver)
                if row:
                    self._log(f"Verification email found! ({elapsed:.1f}s)")
                    return True
            except Exception:
                pass

            # Log setiap 6 detik
            log_counter += 1
            if log_counter % int(_INBOX_REFRESH_EVERY / _INBOX_POLL_INTERVAL) == 0:
                self._log(f"Waiting for email... ({int(elapsed)}s elapsed)")

            time.sleep(_INBOX_POLL_INTERVAL)

        self._log(f"Email not received after {timeout}s", "WARNING")
        return False

    # -------------------------------------------------------------------------
    def extract_verification_code(
        self,
        driver,
        mail_tab_handle: str,
    ) -> Optional[str]:
        """
        Fast extraction:
        1. Cek span.verification-code di DOM dulu (tanpa klik, instan)
        2. Klik link email -> langsung cek span lagi
        3. Fallback ke HTML parse
        """
        self._log("Extracting verification code from email...")
        driver.switch_to.window(mail_tab_handle)

        # ── Cek span di halaman inbox dulu (instan) ──────────────────────────
        otp = self._fast_extract_span(driver)
        if otp:
            self._log(f"OTP extracted instantly from inbox DOM: {otp}")
            return otp

        # ── Klik link email ──────────────────────────────────────────────────
        row = self._find_gemini_row(driver)
        if row:
            self._js_click(driver, row)
            self._log("Clicked 'Gemini Enterprise verification code' link")

            # Poll span setiap 0.3 detik, max 8 detik
            deadline = time.time() + 8
            while time.time() < deadline:
                otp = self._fast_extract_span(driver)
                if otp:
                    self._log(f"OTP obtained (span poll): {otp}")
                    return otp
                time.sleep(0.3)
        else:
            self._log("Could not find Gemini email link", "WARNING")
            time.sleep(0.5)

        # ── Fallback: switch iframe lalu parse HTML ───────────────────────────
        html_content = ""
        try:
            iframes = driver.find_elements(By.TAG_NAME, "iframe")
            for iframe in iframes:
                try:
                    driver.switch_to.frame(iframe)
                    content = driver.page_source
                    if any(k in content.lower() for k in
                           ["verification", "code", "gemini", "your code"]):
                        html_content = content
                        self._log("Switched to email iframe.")
                        break
                    driver.switch_to.default_content()
                except Exception:
                    driver.switch_to.default_content()
        except Exception:
            pass

        if not html_content:
            driver.switch_to.default_content()
            html_content = driver.page_source
        driver.switch_to.default_content()

        otp = _extract_otp_from_html(html_content)
        if otp:
            self._log(f"Verification code extracted (HTML parse): {otp}")
            return otp

        self._log("Could not extract verification code from email", "WARNING")
        return None

    # -------------------------------------------------------------------------
    def _fast_extract_span(self, driver) -> Optional[str]:
        """Cek span.verification-code langsung di DOM saat ini. Return OTP atau None."""
        try:
            # Cek di main document
            els = driver.find_elements(By.CSS_SELECTOR, "span.verification-code, .verification-code")
            for el in els:
                try:
                    text = el.text.strip()
                    if re.fullmatch(r'[A-Z0-9]{4,8}', text, re.IGNORECASE):
                        return text.upper()
                except Exception:
                    pass
        except Exception:
            pass

        # Cek di dalam iframe (jika email ditampilkan dalam iframe)
        try:
            iframes = driver.find_elements(By.TAG_NAME, "iframe")
            for iframe in iframes:
                try:
                    driver.switch_to.frame(iframe)
                    els = driver.find_elements(By.CSS_SELECTOR, "span.verification-code, .verification-code")
                    for el in els:
                        text = el.text.strip()
                        if re.fullmatch(r'[A-Z0-9]{4,8}', text, re.IGNORECASE):
                            driver.switch_to.default_content()
                            return text.upper()
                    driver.switch_to.default_content()
                except Exception:
                    driver.switch_to.default_content()
        except Exception:
            pass

        return None
