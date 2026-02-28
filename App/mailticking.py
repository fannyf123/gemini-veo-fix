"""
mailticking.py

Otomasi mendapatkan temp email dari mailticking.com via Selenium.
Alur:
  1. Buka mailticking.com di tab yang sudah ada
  2. Uncheck Gmail format checkboxes
  3. Klik Change → dapat email random (domain non-gmail)
  4. Klik Activate
  5. Poll inbox untuk cari email verifikasi
  6. Buka email → masuk iframe → ekstrak kode OTP
"""
import re
import time
import random
from typing import Optional, Callable

try:
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.common.exceptions import TimeoutException, NoSuchElementException
    from bs4 import BeautifulSoup
except ImportError:
    pass

MAILTICKING_URL = "https://mailticking.com"

# Warna/style blok OTP di email Gemini
OTP_BG_COLORS   = {"#eaf2ff", "#e8f0fe", "#f1f8ff", "#e3f2fd", "#f0f4ff", "#dce8fc"}
OTP_TEXT_COLORS = {
    "#1c3a70", "#1a73e8", "#4285f4", "#1558d6", "#1967d2",
    "#185abc", "#174ea6", "#0d47a1", "rgb(28,58,112)", "rgb(66,133,244)"
}


def _extract_otp_from_html(html: str) -> Optional[str]:
    """Parse HTML email, cari blok OTP berdasarkan style (font besar / warna / bg)."""
    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception:
        return None

    def _normalize(s: str) -> str:
        return s.lower().replace(" ", "").strip()

    def _is_otp_tag(tag) -> bool:
        style = _normalize(tag.get("style", "") or "")
        if not style:
            return False
        # font-size >= 20px
        m = re.search(r'font-size:([\d.]+)(px|pt)', style)
        if m:
            val = float(m.group(1))
            px  = val if m.group(2) == "px" else val * 1.333
            if px >= 20:
                return True
        # warna text OTP
        for c in OTP_TEXT_COLORS:
            if _normalize(c) in style:
                return True
        # background OTP
        for c in OTP_BG_COLORS:
            if _normalize(c) in style:
                return True
        # letter-spacing + bold
        if "letter-spacing" in style and "font-weight:bold" in style:
            return True
        return False

    # Strategi 1: elemen dengan OTP style
    for tag in soup.find_all(True):
        if _is_otp_tag(tag):
            text = re.sub(r'\s+', '', tag.get_text(strip=True))
            if re.fullmatch(r'[A-Z0-9]{4,8}', text, re.IGNORECASE):
                return text.upper()

    # Strategi 2: elemen standalone hanya berisi kode
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

    # Strategi 3: regex eksplisit di plain text
    plain = soup.get_text(separator=" ")
    patterns = [
        r'(?:verification|one-time)\s+code[^A-Z0-9]{0,20}([A-Z0-9]{4,8})\b',
        r'Your\s+code\s+is[:\s]+([A-Z0-9]{4,8})\b',
        r'\b([0-9]{6})\b',
        r'\b([0-9]{4,8})\b',
    ]
    FALSE_YEARS = {str(y) for y in range(2018, 2032)}
    FOOTER_CTX  = ["copyright", "©", "google llc", "mountain view", "privacy", "terms"]
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
    """
    Mengelola interaksi dengan mailticking.com di tab browser yang sudah ada.
    Semua method menerima driver Selenium yang aktif.
    """

    def __init__(self, log_callback: Optional[Callable] = None):
        self._log_cb = log_callback

    def _log(self, msg: str, level: str = "INFO"):
        if self._log_cb:
            self._log_cb(msg, level)

    def _wait(self, driver, css: str, timeout: int = 15):
        try:
            return WebDriverWait(driver, timeout).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, css))
            )
        except TimeoutException:
            return None

    def _wait_visible(self, driver, css: str, timeout: int = 15):
        try:
            return WebDriverWait(driver, timeout).until(
                EC.visibility_of_element_located((By.CSS_SELECTOR, css))
            )
        except TimeoutException:
            return None

    # ── Setup tab ──────────────────────────────────────────────────────
    def open_mailticking_tab(self, driver) -> str:
        """
        Buka mailticking.com di tab baru, return handle tab.
        Driver tetap fokus ke tab baru ini.
        """
        self._log("Opening mailticking.com...")
        driver.execute_script("window.open('about:blank', '_blank');")
        time.sleep(0.5)
        driver.switch_to.window(driver.window_handles[-1])
        driver.get(MAILTICKING_URL)
        self._wait(driver, "body", timeout=10)
        time.sleep(random.uniform(2.5, 4))
        self._log("mailticking.com loaded.")
        return driver.current_window_handle

    def get_fresh_email(self, driver) -> str:
        """
        Di tab mailticking yang sudah terbuka:
          1. Uncheck Gmail format checkboxes
          2. Klik Change untuk dapat email baru (non-gmail)
          3. Klik Activate
        Return: alamat email baru
        """
        # Uncheck Gmail format checkboxes
        try:
            checkboxes = driver.find_elements(By.CSS_SELECTOR,
                "input[type='checkbox']")
            unchecked = 0
            for cb in checkboxes:
                label = ""
                try:
                    label = driver.find_element(
                        By.XPATH, f"//label[@for='{cb.get_attribute('id')}']"
                    ).text.lower()
                except Exception:
                    pass
                if cb.is_selected() and ("gmail" in label or "google" in label or label == ""):
                    cb.click()
                    unchecked += 1
                    time.sleep(0.3)
            if unchecked:
                self._log(f"Gmail format checkboxes unchecked")
        except Exception:
            pass

        # Baca email saat ini
        try:
            current_el = driver.find_element(By.CSS_SELECTOR,
                "#email, input[id*='email'], .email-display, [class*='email']")
            current_email = current_el.get_attribute("value") or current_el.text
            self._log(f"Current email: {current_email}")
        except Exception:
            pass

        # Klik Change
        change_clicked = False
        for sel in [
            "button[onclick*='change']", "button[id*='change']",
            "a[onclick*='change']", "#change-btn", ".change-btn",
            "//button[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'change')]",
            "//a[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'change')]",
        ]:
            try:
                if sel.startswith("//"):
                    el = driver.find_element(By.XPATH, sel)
                else:
                    el = driver.find_element(By.CSS_SELECTOR, sel)
                el.click()
                change_clicked = True
                self._log("Clicked Change button...")
                break
            except Exception:
                pass

        if not change_clicked:
            # Fallback: cari tombol teks "change"
            for btn in driver.find_elements(By.TAG_NAME, "button"):
                if "change" in btn.text.lower():
                    btn.click()
                    change_clicked = True
                    self._log("Clicked Change button...")
                    break

        time.sleep(random.uniform(1.5, 2.5))

        # Baca email baru
        new_email = ""
        for sel in [
            "#email", "input[id*='email']", ".email-address",
            "[class*='email-display']", "[data-email]",
        ]:
            try:
                el = driver.find_element(By.CSS_SELECTOR, sel)
                val = el.get_attribute("value") or el.get_attribute("data-email") or el.text
                if val and "@" in val:
                    new_email = val.strip()
                    break
            except Exception:
                pass

        if not new_email:
            # Fallback: cari semua elemen yang mengandung @
            src = driver.page_source
            m = re.search(r'([a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})', src)
            if m:
                new_email = m.group(1)

        self._log(f"New email obtained: {new_email}")

        # Klik Activate
        activate_clicked = False
        for sel in [
            "button[onclick*='activat']", "button[id*='activat']",
            "#activate-btn", ".activate-btn",
            "//button[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'activat')]",
        ]:
            try:
                if sel.startswith("//"):
                    el = driver.find_element(By.XPATH, sel)
                else:
                    el = driver.find_element(By.CSS_SELECTOR, sel)
                el.click()
                activate_clicked = True
                break
            except Exception:
                pass

        if not activate_clicked:
            for btn in driver.find_elements(By.TAG_NAME, "button"):
                if "activat" in btn.text.lower():
                    btn.click()
                    activate_clicked = True
                    break

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
        mail_tab_handle: str,
        gemini_tab_handle: str,
        timeout: int = 90,
    ) -> bool:
        """
        Switch ke tab mailticking, poll inbox sampai email verifikasi Gemini muncul.
        Return True jika ditemukan.
        """
        self._log("Checking inbox for verification email...")
        driver.switch_to.window(mail_tab_handle)
        self._log("Switched to mailticking.com tab")

        start = time.time()
        while time.time() - start < timeout:
            try:
                # Refresh inbox
                driver.refresh()
                time.sleep(random.uniform(2, 3))

                # Cari email dari Google / Gemini
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
            if elapsed % 10 == 0:
                self._log(f"Waiting for email... ({elapsed}s)")
            time.sleep(3)

        return False

    def extract_verification_code(
        self,
        driver,
        mail_tab_handle: str,
    ) -> Optional[str]:
        """
        Di tab mailticking, buka email verifikasi dan ekstrak kode OTP.
        """
        self._log("Extracting verification code from email...")
        driver.switch_to.window(mail_tab_handle)

        # Klik email Gemini/Google
        try:
            rows = driver.find_elements(By.CSS_SELECTOR,
                ".mail-item, .inbox-item, tr[onclick], "
                "[class*='email-row'], table tbody tr"
            )
            for row in rows:
                txt = row.text.lower()
                if any(k in txt for k in ["gemini", "google", "verification", "verify"]):
                    row.click()
                    self._log("Opened verification email.")
                    time.sleep(random.uniform(2, 3))
                    break
        except Exception as e:
            self._log(f"Could not click email row: {e}", "WARNING")

        time.sleep(random.uniform(1, 2))

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
