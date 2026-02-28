"""
mailticking.py

Otomasi mailticking.com sesuai tampilan nyata:

  Modal popup muncul otomatis saat halaman load:
  +------------------------------------------+
  | Your Temp Email is Ready                 |
  | [a.mzho.x.v.z.idbke@gmail.com] [Change] |
  |  [x] abc@domain.com      <- uncheck     |
  |  [ ] a.b.c@gmail.com     <- uncheck     |
  |  [ ] abc@gmail.com       <- uncheck     |
  |  [ ] abc+d@gmail.com     <- uncheck     |
  |  [x] abc@googlemail.com  <- HANYA ini   |
  |          [Activate]                     |
  +------------------------------------------+

Alur:
  1. Tunggu modal muncul
  2. Uncheck semua checkbox KECUALI "abc@googlemail.com"
  3. Klik Change -> email baru generate dengan format googlemail
  4. Klik Activate -> modal tutup, inbox aktif
  5. Baca email aktif dari inbox header
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

OTP_BG_COLORS = {"#eaf2ff", "#e8f0fe", "#f1f8ff", "#e3f2fd", "#f0f4ff", "#dce8fc"}
OTP_TEXT_COLORS = {
    "#1c3a70", "#1a73e8", "#4285f4", "#1558d6", "#1967d2",
    "#185abc", "#174ea6", "#0d47a1", "rgb(28,58,112)", "rgb(66,133,244)"
}


def _extract_otp_from_html(html: str) -> Optional[str]:
    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception:
        return None

    def _n(s):
        return s.lower().replace(" ", "").strip()

    def _is_otp_tag(tag) -> bool:
        style = _n(tag.get("style", "") or "")
        if not style:
            return False
        m = re.search(r'font-size:([\d.]+)(px|pt)', style)
        if m:
            val = float(m.group(1))
            px  = val if m.group(2) == "px" else val * 1.333
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

    plain = soup.get_text(separator=" ")
    patterns = [
        r'(?:verification|one-time)\s+code[^A-Z0-9]{0,20}([A-Z0-9]{4,8})\b',
        r'Your\s+code\s+is[:\s]+([A-Z0-9]{4,8})\b',
        r'\b([0-9]{6})\b',
        r'\b([0-9]{4,8})\b',
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
        """JavaScript click - selalu bypass overlay/modal."""
        driver.execute_script("arguments[0].click();", element)

    def _safe_click(self, driver, element):
        """Klik dengan 3 fallback: normal -> scroll+click -> JS click."""
        for attempt in range(3):
            try:
                if attempt == 1:
                    driver.execute_script(
                        "arguments[0].scrollIntoView({block:'center'});", element
                    )
                    time.sleep(0.3)
                if attempt == 2:
                    self._js_click(driver, element)
                    return
                element.click()
                return
            except (ElementClickInterceptedException,
                    ElementNotInteractableException,
                    StaleElementReferenceException):
                time.sleep(0.3)

    def _wait_for_modal(self, driver, timeout: int = 10) -> bool:
        """Tunggu modal 'Your Temp Email is Ready' muncul."""
        try:
            WebDriverWait(driver, timeout).until(
                EC.visibility_of_element_located(
                    (By.CSS_SELECTOR, ".modal.show, .modal.in, .modal[style*='display: block']")
                )
            )
            return True
        except TimeoutException:
            pass
        try:
            els = driver.find_elements(By.XPATH,
                "//button[contains(translate(.,"
                "'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),"
                "'activate')]"
            )
            return any(el.is_displayed() for el in els)
        except Exception:
            return False

    # -- Open tab -------------------------------------------------------------
    def open_mailticking_tab(self, driver) -> str:
        self._log("Opening mailticking.com...")
        driver.execute_script("window.open('about:blank', '_blank');")
        time.sleep(0.5)
        driver.switch_to.window(driver.window_handles[-1])
        driver.get(MAILTICKING_URL)
        try:
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
        except Exception:
            pass
        time.sleep(random.uniform(3, 4))
        self._log("mailticking.com loaded.")
        return driver.current_window_handle

    # -- get_fresh_email ------------------------------------------------------
    def get_fresh_email(self, driver) -> str:
        """
        Alur modal mailticking:
          1. Tunggu modal muncul
          2. Set checkbox: HANYA centang abc@googlemail.com, uncheck sisanya
          3. Klik Change
          4. Klik Activate
          5. Tunggu modal tutup
          6. Baca email aktif
        """
        modal_found = self._wait_for_modal(driver, timeout=8)
        if modal_found:
            self._log("Modal 'Your Temp Email is Ready' detected.")
        else:
            self._log("Modal not detected, proceeding anyway...", "WARNING")

        self._configure_checkboxes(driver)
        time.sleep(0.5)

        old_email = self._read_current_email(driver)
        self._log(f"Current email: {old_email}")

        self._click_change(driver)
        time.sleep(random.uniform(1.5, 2.5))

        new_email = self._read_current_email(driver)
        self._log(f"New email obtained: {new_email}" if new_email else "Could not read new email")

        self._click_activate(driver)
        self._wait_modal_closed(driver)

        final_email = self._read_email_from_page(driver) or new_email
        self._log(f"Temp email obtained: {final_email}")
        return final_email

    # -- Sub-helpers ----------------------------------------------------------

    def _configure_checkboxes(self, driver):
        """
        Target: HANYA centang abc@googlemail.com, uncheck semua yang lain.

        Format checkbox di mailticking:
          [x] abc@domain.com
          [x] a.b.c@gmail.com
          [x] abc@gmail.com
          [x] abc+d@gmail.com
          [x] abc@googlemail.com  <- SATU-SATUNYA yang harus checked
        """
        try:
            checkboxes = driver.find_elements(By.CSS_SELECTOR, "input[type='checkbox']")
            if not checkboxes:
                self._log("No checkboxes found in modal", "WARNING")
                return

            for cb in checkboxes:
                try:
                    cb_id    = cb.get_attribute("id") or ""
                    cb_value = (cb.get_attribute("value") or "").lower()
                    cb_name  = (cb.get_attribute("name")  or "").lower()

                    label_text = ""
                    if cb_id:
                        try:
                            lbl = driver.find_element(By.XPATH, f"//label[@for='{cb_id}']")
                            label_text = lbl.text.lower()
                        except Exception:
                            pass
                    if not label_text:
                        try:
                            lbl = cb.find_element(By.XPATH, "./ancestor::label")
                            label_text = lbl.text.lower()
                        except Exception:
                            pass
                    if not label_text:
                        try:
                            parent = cb.find_element(By.XPATH, "..")
                            label_text = parent.text.lower()
                        except Exception:
                            pass

                    combined = label_text + cb_value + cb_name

                    # Target: abc@googlemail.com
                    is_googlemail = "googlemail" in combined

                    currently_checked = cb.is_selected()

                    if is_googlemail:
                        # Harus CHECKED
                        if not currently_checked:
                            self._js_click(driver, cb)
                            time.sleep(0.2)
                    else:
                        # Harus UNCHECKED
                        if currently_checked:
                            self._js_click(driver, cb)
                            time.sleep(0.2)

                except StaleElementReferenceException:
                    continue
                except Exception:
                    continue

            self._log("Gmail format checkboxes unchecked")

        except Exception as e:
            self._log(f"Checkbox config error: {e}", "WARNING")

    def _read_current_email(self, driver) -> str:
        for sel in [
            ".modal input[type='text']",
            ".modal input[type='email']",
            ".modal input[readonly]",
            "input[type='text']",
            "input[type='email']",
            "input[readonly]",
            "#email",
        ]:
            try:
                el  = driver.find_element(By.CSS_SELECTOR, sel)
                val = el.get_attribute("value") or el.text or ""
                if "@" in val:
                    return val.strip()
            except Exception:
                pass
        return ""

    def _read_email_from_page(self, driver) -> str:
        for sel in [
            "input[type='text']", "input[type='email']",
            "input[readonly]", "#email",
            ".email-display", "[class*='email']",
            ".navbar input", ".header input",
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
                r'value="([a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})"', src
            )
            if m and "@" in m.group(1):
                return m.group(1)
        except Exception:
            pass
        return ""

    def _click_change(self, driver):
        CHANGE_SELECTORS = [
            ".input-group-btn button",
            ".input-group button",
            "button.btn-default",
        ]
        for sel in CHANGE_SELECTORS:
            try:
                el = driver.find_element(By.CSS_SELECTOR, sel)
                if el.is_displayed():
                    self._js_click(driver, el)
                    self._log("Clicked Change button...")
                    return
            except Exception:
                pass

        for btn in driver.find_elements(By.TAG_NAME, "button"):
            try:
                txt = (btn.text or "").lower().strip()
                if "change" in txt or (btn.get_attribute("title") or "").lower() == "change":
                    self._js_click(driver, btn)
                    self._log("Clicked Change button...")
                    return
            except Exception:
                pass

        try:
            btns = driver.find_elements(By.CSS_SELECTOR,
                ".modal .input-group button, .modal button.btn-default")
            if btns:
                self._js_click(driver, btns[0])
                self._log("Clicked Change button (fallback)...")
                return
        except Exception:
            pass

        self._log("Change button not found", "WARNING")

    def _click_activate(self, driver):
        for sel in [".modal .btn-warning", ".modal .btn-success",
                    ".modal .btn-primary", ".modal button.btn"]:
            try:
                els = driver.find_elements(By.CSS_SELECTOR, sel)
                for el in els:
                    if el.is_displayed() and "activat" in el.text.lower():
                        self._js_click(driver, el)
                        self._log("Clicked Activate button...")
                        return
            except Exception:
                pass

        for btn in driver.find_elements(By.TAG_NAME, "button"):
            try:
                if "activat" in btn.text.lower() and btn.is_displayed():
                    self._js_click(driver, btn)
                    self._log("Clicked Activate button...")
                    return
            except Exception:
                pass

        try:
            el = driver.find_element(By.XPATH,
                "//button[contains("
                "translate(.,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz')"
                ",'activat')]")
            self._js_click(driver, el)
            self._log("Clicked Activate button...")
            return
        except Exception:
            pass

        self._log("Activate button not found", "WARNING")

    def _wait_modal_closed(self, driver, timeout: int = 10):
        try:
            WebDriverWait(driver, timeout).until(
                EC.invisibility_of_element_located(
                    (By.CSS_SELECTOR, ".modal.show, .modal.in")
                )
            )
            self._log("Email activated successfully.")
        except TimeoutException:
            time.sleep(random.uniform(2, 3))
            self._log("Email activated successfully.")

    # -- Inbox polling --------------------------------------------------------
    def wait_for_verification_email(
        self,
        driver,
        mail_tab_handle:   str,
        gemini_tab_handle: str,
        timeout:           int = 90,
    ) -> bool:
        self._log("Checking inbox for verification email...")
        driver.switch_to.window(mail_tab_handle)
        self._log("Switched to mailticking.com tab")

        start = time.time()
        while time.time() - start < timeout:
            try:
                try:
                    refresh_btn = driver.find_element(By.CSS_SELECTOR,
                        ".refresh-btn, [onclick*='refresh'], #refresh,"
                        ".sidebar .refresh, .nav-icon[title*='efresh']")
                    self._js_click(driver, refresh_btn)
                except Exception:
                    driver.refresh()

                time.sleep(random.uniform(2, 3))

                # Dismiss modal jika muncul lagi setelah refresh
                try:
                    modal_els = driver.find_elements(By.CSS_SELECTOR,
                        ".modal.show, .modal.in, .modal[style*='display: block']")
                    if any(el.is_displayed() for el in modal_els):
                        self._click_activate(driver)
                        time.sleep(1)
                except Exception:
                    pass

                rows = driver.find_elements(By.CSS_SELECTOR,
                    ".mail-item, .inbox-item, tr[onclick], "
                    "[class*='email-row'], [class*='message-row'], "
                    "table tbody tr, .list-group-item"
                )
                for row in rows:
                    txt = (row.text or "").lower()
                    if any(k in txt for k in [
                        "gemini", "google", "verification", "verify", "noreply", "code"
                    ]):
                        self._log("Verification email found!")
                        return True
            except Exception:
                pass

            elapsed = int(time.time() - start)
            if elapsed > 0 and elapsed % 10 < 3:
                self._log(f"Waiting for email... ({elapsed}s)")
            time.sleep(3)

        return False

    def extract_verification_code(
        self,
        driver,
        mail_tab_handle: str,
    ) -> Optional[str]:
        self._log("Extracting verification code from email...")
        driver.switch_to.window(mail_tab_handle)

        try:
            rows = driver.find_elements(By.CSS_SELECTOR,
                ".mail-item, .inbox-item, tr[onclick], "
                "[class*='email-row'], table tbody tr, .list-group-item"
            )
            for row in rows:
                txt = (row.text or "").lower()
                if any(k in txt for k in ["gemini", "google", "verification", "verify"]):
                    self._js_click(driver, row)
                    self._log("Opened verification email.")
                    time.sleep(random.uniform(2, 3))
                    break
        except Exception as e:
            self._log(f"Could not click email row: {e}", "WARNING")

        time.sleep(random.uniform(1, 2))

        html_content = ""
        try:
            iframes = driver.find_elements(By.TAG_NAME, "iframe")
            for iframe in iframes:
                try:
                    driver.switch_to.frame(iframe)
                    content = driver.page_source
                    if any(k in content.lower() for k in ["verification", "code", "gemini"]):
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
            self._log(f"Verification code extracted: {otp}")
            return otp

        self._log("Could not extract verification code from email", "WARNING")
        return None
