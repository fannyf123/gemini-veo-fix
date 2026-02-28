"""
mailticking.py

Otomasi mendapatkan temp email dari mailticking.com via Selenium.
Alur:
  1. Buka mailticking.com di tab baru
  2. Dismiss modal/popup jika ada (sering muncul saat load)
  3. Uncheck Gmail format checkboxes
  4. Klik Change → dapat email random (domain non-gmail)
  5. Klik Activate
  6. Poll inbox untuk cari email verifikasi
  7. Buka email → masuk iframe → ekstrak kode OTP
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
        ElementClickInterceptedException, ElementNotInteractableException
    )
    from bs4 import BeautifulSoup
except ImportError:
    pass

MAILTICKING_URL = "https://mailticking.com"

OTP_BG_COLORS   = {"#eaf2ff", "#e8f0fe", "#f1f8ff", "#e3f2fd", "#f0f4ff", "#dce8fc"}
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

    def _safe_click(self, driver, element):
        """
        Klik elemen dengan 3 fallback:
          1. click() biasa
          2. scroll into view + click()
          3. JavaScript click (bypass overlay)
        """
        try:
            element.click()
            return
        except (ElementClickInterceptedException, ElementNotInteractableException):
            pass
        try:
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", element)
            time.sleep(0.4)
            element.click()
            return
        except (ElementClickInterceptedException, ElementNotInteractableException):
            pass
        # JS click terakhir — selalu lolos overlay/modal
        driver.execute_script("arguments[0].click();", element)

    def _dismiss_modals(self, driver):
        """
        Tutup semua modal / popup / overlay yang mungkin muncul di mailticking.
        Coba:
          - Klik tombol X / close / dismiss di modal
          - Tekan Escape
          - Klik backdrop modal via JS
        """
        # Selector tombol close modal yang umum
        CLOSE_SELECTORS = [
            ".modal .close",
            ".modal-header .close",
            ".modal button.close",
            "button[data-dismiss='modal']",
            "[aria-label='Close']",
            ".modal-footer button",
            ".modal .btn",
        ]
        dismissed = False
        for sel in CLOSE_SELECTORS:
            try:
                els = driver.find_elements(By.CSS_SELECTOR, sel)
                for el in els:
                    if el.is_displayed():
                        driver.execute_script("arguments[0].click();", el)
                        dismissed = True
                        time.sleep(0.5)
                        break
            except Exception:
                pass
            if dismissed:
                break

        # Escape key fallback
        try:
            from selenium.webdriver.common.keys import Keys
            driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
            time.sleep(0.4)
        except Exception:
            pass

        # Klik backdrop via JS jika masih ada
        try:
            driver.execute_script(
                "var m = document.querySelector('.modal-backdrop');"
                "if(m){ m.style.display='none'; }"
                "var ms = document.querySelectorAll('.modal.show,.modal.in');"
                "ms.forEach(function(x){ x.style.display='none'; x.classList.remove('show','in'); });"
                "document.body.classList.remove('modal-open');"
                "document.body.style.overflow='';"
            )
        except Exception:
            pass

        if dismissed:
            self._log("Modal dismissed.")

    def open_mailticking_tab(self, driver) -> str:
        self._log("Opening mailticking.com...")
        driver.execute_script("window.open('about:blank', '_blank');")
        time.sleep(0.5)
        driver.switch_to.window(driver.window_handles[-1])
        driver.get(MAILTICKING_URL)
        try:
            WebDriverWait(driver, 12).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
        except Exception:
            pass
        time.sleep(random.uniform(3, 4.5))
        # Dismiss modal yang sering muncul saat load pertama
        self._dismiss_modals(driver)
        time.sleep(0.5)
        self._log("mailticking.com loaded.")
        return driver.current_window_handle

    def get_fresh_email(self, driver) -> str:
        # Pastikan tidak ada modal yang tersisa
        self._dismiss_modals(driver)
        time.sleep(0.3)

        # ─ Baca email saat ini ──────────────────────────────────────────
        current_email = ""
        for sel in [
            "#email", "input[id*='email']",
            ".email-display", "[class*='email']",
            "input[readonly]", "input[type='text']",
        ]:
            try:
                el  = driver.find_element(By.CSS_SELECTOR, sel)
                val = el.get_attribute("value") or el.text or ""
                if "@" in val:
                    current_email = val.strip()
                    break
            except Exception:
                pass
        self._log(f"Current email: {current_email}")

        # ─ Uncheck Gmail checkboxes ────────────────────────────────────
        try:
            for cb in driver.find_elements(By.CSS_SELECTOR, "input[type='checkbox']"):
                if cb.is_selected():
                    label_txt = ""
                    try:
                        cb_id = cb.get_attribute("id")
                        if cb_id:
                            label_txt = driver.find_element(
                                By.XPATH, f"//label[@for='{cb_id}']"
                            ).text.lower()
                    except Exception:
                        pass
                    if "gmail" in label_txt or "google" in label_txt or not label_txt:
                        self._safe_click(driver, cb)
                        time.sleep(0.3)
            self._log("Gmail format checkboxes unchecked")
        except Exception:
            pass

        # ─ Klik Change button ───────────────────────────────────────
        change_clicked = False

        # Coba selector CSS/XPATH spesifik dulu
        CHANGE_CSS = [
            "button.dropdown-toggle",
            ".input-group-btn button",
            "button[data-toggle='dropdown']",
            "button[onclick*='change']",
            "button[id*='change']",
            "#change-btn", ".change-btn",
        ]
        for sel in CHANGE_CSS:
            try:
                el = driver.find_element(By.CSS_SELECTOR, sel)
                if el.is_displayed():
                    self._safe_click(driver, el)
                    change_clicked = True
                    self._log("Clicked Change button...")
                    break
            except Exception:
                pass

        if not change_clicked:
            # Fallback: cari semua button, filter teks "change"
            for btn in driver.find_elements(By.TAG_NAME, "button"):
                try:
                    if "change" in btn.text.lower() and btn.is_displayed():
                        self._safe_click(driver, btn)
                        change_clicked = True
                        self._log("Clicked Change button...")
                        break
                except Exception:
                    pass

        time.sleep(random.uniform(1.5, 2.5))
        # Dismiss modal yang mungkin muncul setelah klik Change
        self._dismiss_modals(driver)
        time.sleep(0.5)

        # ─ Baca email baru dari dropdown list ────────────────────────────
        # mailticking menampilkan daftar domain di dropdown setelah klik Change
        new_email = ""

        # Coba klik item pertama di dropdown yang terbuka
        DROPDOWN_ITEM_SELECTORS = [
            ".dropdown-menu li a",
            ".dropdown-menu li",
            ".dropdown-menu .domain-option",
            "ul.dropdown-menu li",
        ]
        for sel in DROPDOWN_ITEM_SELECTORS:
            try:
                items = driver.find_elements(By.CSS_SELECTOR, sel)
                if items:
                    # Ambil item pertama yang bukan gmail
                    for item in items:
                        txt = item.text.lower()
                        if txt and "gmail" not in txt and "google" not in txt:
                            self._safe_click(driver, item)
                            self._log(f"Selected domain: {item.text.strip()}")
                            time.sleep(random.uniform(1, 1.5))
                            break
                    break
            except Exception:
                pass

        time.sleep(random.uniform(1, 1.5))

        # Baca email yang sekarang aktif
        for sel in [
            "#email", "input[id*='email']", ".email-address",
            "[class*='email-display']", "[data-email]",
            "input[readonly]", "input[type='text']",
        ]:
            try:
                el  = driver.find_element(By.CSS_SELECTOR, sel)
                val = el.get_attribute("value") or el.get_attribute("data-email") or el.text or ""
                if "@" in val:
                    new_email = val.strip()
                    break
            except Exception:
                pass

        if not new_email:
            # Fallback regex di page source
            src = driver.page_source
            m = re.search(
                r'([a-zA-Z0-9._%+\-]+'
                r'@(?!gmail\.com|googlemail\.com)'
                r'[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})',
                src
            )
            if m:
                new_email = m.group(1)

        self._log(f"New email obtained: {new_email}")

        # ─ Klik Activate ───────────────────────────────────────────────
        activate_clicked = False
        ACTIVATE_CSS = [
            "button[onclick*='activat']",
            "button[id*='activat']",
            "#activate-btn", ".activate-btn",
            "button.btn-success", "button.btn-primary",
        ]
        for sel in ACTIVATE_CSS:
            try:
                el = driver.find_element(By.CSS_SELECTOR, sel)
                if el.is_displayed():
                    self._safe_click(driver, el)
                    activate_clicked = True
                    break
            except Exception:
                pass

        if not activate_clicked:
            for btn in driver.find_elements(By.TAG_NAME, "button"):
                try:
                    if "activat" in btn.text.lower() and btn.is_displayed():
                        self._safe_click(driver, btn)
                        activate_clicked = True
                        break
                except Exception:
                    pass

        if activate_clicked:
            self._log("Clicked Activate button...")
            time.sleep(random.uniform(1.5, 2))
            self._log("Email activated successfully.")
        else:
            self._log("Activate button not found, continuing...", "WARNING")

        time.sleep(random.uniform(1, 1.5))
        self._log(f"Temp email obtained: {new_email}")
        return new_email

    # ── Inbox polling ───────────────────────────────────────────────────
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
                time.sleep(random.uniform(2, 3))
                self._dismiss_modals(driver)  # modal bisa muncul lagi setelah refresh

                rows = driver.find_elements(By.CSS_SELECTOR,
                    ".mail-item, .inbox-item, tr[onclick], "
                    "[class*='email-row'], [class*='message-row'], "
                    "table tbody tr"
                )
                for row in rows:
                    txt = row.text.lower()
                    if any(k in txt for k in [
                        "gemini", "google", "verification", "verify",
                        "noreply", "code"
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
        self._dismiss_modals(driver)

        # Klik email Gemini/Google
        try:
            rows = driver.find_elements(By.CSS_SELECTOR,
                ".mail-item, .inbox-item, tr[onclick], "
                "[class*='email-row'], table tbody tr"
            )
            for row in rows:
                txt = row.text.lower()
                if any(k in txt for k in ["gemini", "google", "verification", "verify"]):
                    self._safe_click(driver, row)
                    self._log("Opened verification email.")
                    time.sleep(random.uniform(2, 3))
                    break
        except Exception as e:
            self._log(f"Could not click email row: {e}", "WARNING")

        time.sleep(random.uniform(1, 2))
        self._dismiss_modals(driver)

        # Coba masuk iframe email
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
