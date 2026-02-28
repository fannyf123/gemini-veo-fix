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

EXACT ELEMENTS dari inspect:
  Tombol Change (klik berulang sampai email BUKAN @gmail/@googlemail):
    <button class="btn btn-info" type="button" id="modalChange">
      <i class="fa fa-random"></i>
      <span class="d-none d-md-inline"> Change</span>
    </button>

  Checkbox domain (TARGET - HANYA ini yang dicentang):
    <input class="form-check-input type" type="checkbox" name="type" id="type4" value="4" checked="">
    <label class="form-check-label" for="type4">abc@<b class="red">domain</b>.com</label>

  Activate button:
    <a href="javascript:;" class="btn btn-warning mx-auto btn-lg activeBtn">

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


def _is_banned_email(email: str) -> bool:
    """Return True jika email berformat @gmail.com atau @googlemail.com."""
    low = email.lower().strip()
    return any(low.endswith(d) for d in BANNED_DOMAINS)


def _extract_otp_from_html(html: str) -> Optional[str]:
    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception:
        return None

    for tag in soup.find_all("span", class_="verification-code"):
        text = re.sub(r'\s+', '', tag.get_text(strip=True))
        if re.fullmatch(r'[A-Z0-9]{4,8}', text, re.IGNORECASE):
            return text.upper()

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

    def _safe_click(self, driver, element):
        for attempt in range(3):
            try:
                if attempt == 1:
                    driver.execute_script(
                        "arguments[0].scrollIntoView({block:'center'});", element)
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

    def _wait_for_modal(self, driver, timeout: int = 15) -> bool:
        try:
            WebDriverWait(driver, timeout).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, "a.activeBtn, .activeBtn"))
            )
            return True
        except TimeoutException:
            pass
        try:
            WebDriverWait(driver, 5).until(
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
        time.sleep(0.5)
        driver.switch_to.window(driver.window_handles[-1])
        driver.get(MAILTICKING_URL)
        try:
            WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.TAG_NAME, "body")))
        except Exception:
            pass
        time.sleep(random.uniform(3, 4))
        self._log("mailticking.com loaded.")
        return driver.current_window_handle

    # -------------------------------------------------------------------------
    def get_fresh_email(self, driver) -> str:
        """
        Step 3-6:
          3. Klik button#modalChange berulang sampai email BUKAN @gmail/@googlemail
          4. Centang HANYA input#type4 (abc@domain.com), uncheck semua lainnya
          5. Klik a.activeBtn (Activate)
          6. Tunggu halaman reload -> baca email dari input bar
        """
        modal_found = self._wait_for_modal(driver, timeout=12)
        if modal_found:
            self._log("Modal 'Your Temp Email is Ready' detected.")
        else:
            self._log("Modal not detected, proceeding anyway...", "WARNING")

        # Step 3: Loop klik Change sampai email bukan @gmail / @googlemail
        email = self._click_change_until_non_gmail(driver)
        self._log(f"Non-gmail email ready: {email}")

        # Step 4: Centang HANYA type4 (abc@domain.com)
        self._configure_checkboxes(driver)
        time.sleep(0.5)

        # Step 5: Klik Activate
        self._click_activate(driver)

        # Step 6: Tunggu halaman reload
        self._log("Waiting for page to reload after Activate...")
        time.sleep(random.uniform(3, 5))

        # Baca email aktif dari navbar
        final_email = self._read_email_from_navbar(driver) or email
        self._log(f"Temp email obtained: {final_email}")
        return final_email

    # -------------------------------------------------------------------------
    def _read_email_from_modal(self, driver) -> str:
        """Baca email yang sedang tampil di field modal (sebelum activate)."""
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

    def _click_change_until_non_gmail(
        self, driver, max_attempts: int = 20
    ) -> str:
        """
        Klik button#modalChange berulang sampai email field BUKAN @gmail.com
        maupun @googlemail.com (karena Google register butuh non-Gmail address).

        EXACT: <button class="btn btn-info" type="button" id="modalChange">

        Target: abc@domain.com (id=type4) -> domain selain gmail/googlemail

        Alur per iterasi:
          1. Baca email saat ini
          2. Jika bukan @gmail.com DAN bukan @googlemail.com -> selesai
          3. Klik Change button
          4. Tunggu email di field berubah
          5. Ulangi sampai max_attempts
        """
        CHANGE_SELECTORS = [
            "button#modalChange",
            "#modalChange",
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

        for attempt in range(1, max_attempts + 1):
            current_email = self._read_email_from_modal(driver)

            # Kondisi sukses: email ada dan bukan banned domain
            if current_email and not _is_banned_email(current_email):
                self._log(
                    f"Email valid (non-gmail) on attempt {attempt}: {current_email}")
                return current_email

            reason = "(kosong)" if not current_email else f"'{current_email}' adalah @gmail/@googlemail"
            self._log(
                f"Attempt {attempt}/{max_attempts}: {reason}, klik Change..."
            )

            btn = _find_change_btn()
            if not btn:
                self._log("Change button tidak ditemukan", "WARNING")
                break

            self._js_click(driver, btn)

            # Tunggu email berubah (max 3 detik polling)
            deadline = time.time() + 3
            while time.time() < deadline:
                time.sleep(0.4)
                new_email = self._read_email_from_modal(driver)
                if new_email and new_email != current_email:
                    break

        last_email = self._read_email_from_modal(driver)
        self._log(
            f"Max attempts reached. Last email: {last_email}", "WARNING")
        return last_email

    # -------------------------------------------------------------------------
    def _configure_checkboxes(self, driver):
        """
        Centang HANYA id="type4" (abc@domain.com).
        Uncheck semua checkbox lain (type1, type2, type3, dll).

        EXACT dari inspect:
          <input class="form-check-input type" type="checkbox"
                 name="type" id="type4" value="4" checked="">
          <label class="form-check-label" for="type4">
            abc@<b class="red">domain</b>.com
          </label>
        """
        try:
            checkboxes = driver.find_elements(
                By.CSS_SELECTOR, "input[type='checkbox'][name='type']")
            if not checkboxes:
                checkboxes = driver.find_elements(
                    By.CSS_SELECTOR, "input[type='checkbox']")
            if not checkboxes:
                self._log("No checkboxes found in modal", "WARNING")
                return

            for cb in checkboxes:
                try:
                    cb_id    = cb.get_attribute("id") or ""
                    cb_value = (cb.get_attribute("value") or "").strip()

                    # Ambil label text untuk deteksi
                    label_text = ""
                    if cb_id:
                        try:
                            lbl = driver.find_element(
                                By.XPATH, f"//label[@for='{cb_id}']")
                            label_text = lbl.text.lower()
                        except Exception:
                            pass
                    if not label_text:
                        try:
                            parent = cb.find_element(By.XPATH, "..")
                            label_text = parent.text.lower()
                        except Exception:
                            pass

                    # id="type4" ATAU value="4" ATAU label mengandung "domain"
                    # dan TIDAK mengandung "gmail" atau "googlemail"
                    is_domain = (
                        cb_id == "type4"
                        or cb_value == "4"
                        or (
                            "domain" in label_text
                            and "gmail" not in label_text
                            and "googlemail" not in label_text
                        )
                    )

                    currently_checked = cb.is_selected()

                    if is_domain:
                        if not currently_checked:
                            self._js_click(driver, cb)
                            time.sleep(0.2)
                            self._log(f"Checked: abc@domain.com (id={cb_id})")
                        else:
                            self._log(f"Already checked: abc@domain.com (id={cb_id})")
                    else:
                        if currently_checked:
                            self._js_click(driver, cb)
                            time.sleep(0.2)

                except StaleElementReferenceException:
                    continue
                except Exception:
                    continue

            self._log("Checkboxes configured: only abc@domain.com (type4) selected")
        except Exception as e:
            self._log(f"Checkbox config error: {e}", "WARNING")

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
        """
        EXACT: <a href="javascript:;" class="btn btn-warning mx-auto btn-lg activeBtn">
        """
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
                    self._log("Clicked Activate button (a.activeBtn)")
                    return
            except Exception:
                pass
        for tag in ["a", "button"]:
            for el in driver.find_elements(By.TAG_NAME, tag):
                try:
                    if "activat" in el.text.lower() and el.is_displayed():
                        self._js_click(driver, el)
                        self._log(f"Clicked Activate button (fallback {tag})")
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
        self._log("Checking inbox for verification email...")
        driver.switch_to.window(mail_tab_handle)
        self._log("Switched to mailticking.com tab")

        start = time.time()
        while time.time() - start < timeout:
            try:
                driver.refresh()
                try:
                    WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located((By.TAG_NAME, "body")))
                except Exception:
                    pass
                time.sleep(random.uniform(2, 3))

                try:
                    act_btn = driver.find_elements(By.CSS_SELECTOR, "a.activeBtn, .activeBtn")
                    if any(b.is_displayed() for b in act_btn):
                        for b in act_btn:
                            if b.is_displayed():
                                self._js_click(driver, b)
                                time.sleep(1.5)
                                break
                except Exception:
                    pass

                row = self._find_gemini_row(driver)
                if row:
                    self._log("Verification email found!")
                    return True

            except Exception:
                pass

            elapsed = int(time.time() - start)
            if elapsed > 0 and elapsed % 10 < 3:
                self._log(f"Waiting for email... ({elapsed}s)")
            time.sleep(3)

        return False

    # -------------------------------------------------------------------------
    def extract_verification_code(
        self,
        driver,
        mail_tab_handle: str,
    ) -> Optional[str]:
        self._log("Extracting verification code from email...")
        driver.switch_to.window(mail_tab_handle)

        row = self._find_gemini_row(driver)
        if row:
            self._js_click(driver, row)
            self._log("Clicked 'Gemini Enterprise verification code' link")
            try:
                WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located(
                        (By.CSS_SELECTOR, "span.verification-code, .verification-code"))
                )
            except TimeoutException:
                pass
            time.sleep(random.uniform(2, 3))
        else:
            self._log("Could not find Gemini email link", "WARNING")
            time.sleep(2)

        try:
            otp_el = driver.find_element(By.CSS_SELECTOR, "span.verification-code")
            otp = otp_el.text.strip()
            if re.fullmatch(r'[A-Z0-9]{4,8}', otp, re.IGNORECASE):
                self._log(f"Verification code extracted (span.verification-code): {otp.upper()}")
                return otp.upper()
        except Exception:
            pass

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
            self._log(f"Verification code extracted: {otp}")
            return otp

        self._log("Could not extract verification code from email", "WARNING")
        return None
