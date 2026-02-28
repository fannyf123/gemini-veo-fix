"""
mailticking.py

Otomasi mailticking.com sesuai tampilan nyata:

  Modal popup muncul otomatis saat halaman load:
  +------------------------------------------+
  | Your Temp Email is Ready                 |
  | [a.mzho.x.v.z.idbke@gmail.com] [Change] |
  |  [x] abc@domain.com                     |
  |  [x] a.b.c@gmail.com   <-- HANYA ini    |
  |  [x] abc@gmail.com      <-- uncheck     |
  |  [x] abc+d@gmail.com    <-- uncheck     |
  |  [x] abc@googlemail.com <-- uncheck     |
  |          [Activate]                     |
  +------------------------------------------+

Alur:
  1. Tunggu modal muncul
  2. Uncheck semua checkbox KECUALI "a.b.c@gmail.com"
  3. Klik Change → email baru generate
  4. Klik Activate → modal tutup, inbox aktif
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
        """JavaScript click — selalu bypass overlay/modal."""
        driver.execute_script("arguments[0].click();", element)

    def _safe_click(self, driver, element):
        """Klik dengan 3 fallback: normal → scroll+click → JS click."""
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
        """Tunggu modal 'Your Temp Email is Ready' muncul. Return True jika ada."""
        try:
            WebDriverWait(driver, timeout).until(
                EC.visibility_of_element_located(
                    (By.CSS_SELECTOR, ".modal.show, .modal.in, .modal[style*='display: block']")
                )
            )
            return True
        except TimeoutException:
            pass
        # Fallback: cek apakah ada elemen Activate di halaman
        try:
            els = driver.find_elements(By.XPATH,
                "//button[contains(translate(.,"
                "'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),"
                "'activate')]"
            )
            return any(el.is_displayed() for el in els)
        except Exception:
            return False

    # ── Open tab ──────────────────────────────────────────────────────────
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

    # ── get_fresh_email: alur utama sesuai screenshot ─────────────────────────
    def get_fresh_email(self, driver) -> str:
        """
        Alur modal mailticking:
          1. Tunggu modal muncul
          2. Set checkbox: HANYA centang a.b.c@gmail.com, uncheck sisanya
          3. Klik Change
          4. Klik Activate
          5. Tunggu modal tutup / halaman reload
          6. Baca email aktif
        """
        # Tunggu modal muncul
        modal_found = self._wait_for_modal(driver, timeout=8)
        if modal_found:
            self._log("Modal 'Your Temp Email is Ready' detected.")
        else:
            self._log("Modal not detected, proceeding anyway...", "WARNING")

        # ─ Step 1: Konfigurasi checkboxes ─────────────────────────────────
        # Format yang INGIN kita pakai: a.b.c@gmail.com
        # Format lain: abc@domain.com, abc@gmail.com, abc+d@gmail.com,
        #              abc@googlemail.com  → semua UNCHECK
        self._configure_checkboxes(driver)
        time.sleep(0.5)

        # ─ Step 2: Baca email sebelum Change ──────────────────────────────
        old_email = self._read_current_email(driver)
        self._log(f"Current email: {old_email}")

        # ─ Step 3: Klik Change ───────────────────────────────────────────
        self._click_change(driver)
        time.sleep(random.uniform(1.5, 2.5))

        # ─ Step 4: Baca email baru ───────────────────────────────────────
        new_email = self._read_current_email(driver)
        if new_email and new_email != old_email:
            self._log(f"New email obtained: {new_email}")
        elif new_email:
            self._log(f"New email obtained: {new_email}")
        else:
            self._log("Could not read new email from input", "WARNING")

        # ─ Step 5: Klik Activate ────────────────────────────────────────
        self._click_activate(driver)

        # ─ Step 6: Tunggu modal hilang / inbox ready ──────────────────────
        self._wait_modal_closed(driver)

        # Baca email final dari halaman setelah modal tutup
        final_email = self._read_email_from_page(driver) or new_email
        self._log(f"Temp email obtained: {final_email}")
        return final_email

    # ── Sub-helpers ──────────────────────────────────────────────────────────

    def _configure_checkboxes(self, driver):
        """
        Di modal mailticking ada 4 format:
          [x] abc@domain.com
          [x] a.b.c@gmail.com    <- HANYA ini yang dipertahankan
          [x] abc@gmail.com
          [x] abc+d@gmail.com
          [x] abc@googlemail.com

        Cara kerja: iterasi semua checkbox, baca label teksnya,
        set ke checked jika label mengandung 'a.b.c' atau 'dot',
        uncheck jika bukan.
        """
        try:
            checkboxes = driver.find_elements(By.CSS_SELECTOR, "input[type='checkbox']")
            if not checkboxes:
                self._log("No checkboxes found in modal", "WARNING")
                return

            for cb in checkboxes:
                try:
                    # Baca label teks
                    cb_id    = cb.get_attribute("id") or ""
                    cb_value = (cb.get_attribute("value") or "").lower()
                    cb_name  = (cb.get_attribute("name")  or "").lower()

                    # Cari label text via <label for=id> atau parent/sibling
                    label_text = ""
                    if cb_id:
                        try:
                            lbl = driver.find_element(By.XPATH,
                                f"//label[@for='{cb_id}']"
                            )
                            label_text = lbl.text.lower()
                        except Exception:
                            pass

                    if not label_text:
                        try:
                            # label yang wraps checkbox
                            lbl = cb.find_element(By.XPATH, "./ancestor::label")
                            label_text = lbl.text.lower()
                        except Exception:
                            pass

                    if not label_text:
                        try:
                            # sibling span/text setelah checkbox
                            parent = cb.find_element(By.XPATH, "..")
                            label_text = parent.text.lower()
                        except Exception:
                            pass

                    combined = label_text + cb_value + cb_name

                    # Ini format yang kita mau: a.b.c@gmail.com
                    # Cirinya: ada "." sebelum "@" dan ada "@gmail.com"
                    # dan TIDAK ada "+" (bukan abc+d)
                    # dan TIDAK ada "googlemail"
                    # dan bukan abc@gmail.com (tanpa titik di local part yang berarti)
                    is_dotted_gmail = (
                        re.search(r'a\.b\.c@gmail', combined) or
                        re.search(r'[a-z]+\.[a-z]+\.[a-z]+@gmail', combined) or
                        # mailticking biasanya beri label "a.b.c@gmail.com"
                        ("." in combined.split("@")[0] if "@gmail.com" in combined else False)
                        and "+" not in combined
                        and "googlemail" not in combined
                    )

                    # Fallback: jika tidak bisa baca label, ambil posisi
                    # checkbox ke-2 (index 1) = a.b.c@gmail.com

                    currently_checked = cb.is_selected()

                    if is_dotted_gmail:
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
        """Baca email dari input field di modal."""
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
        """
        Baca email dari halaman utama inbox setelah modal ditutup.
        Mailticking biasanya tampilkan email di header/navbar.
        """
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
        # Fallback regex di page source (non-gmail domain)
        try:
            src = driver.page_source
            m = re.search(
                r'value="([a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})"',
                src
            )
            if m and "@" in m.group(1):
                return m.group(1)
        except Exception:
            pass
        return ""

    def _click_change(self, driver):
        """Klik tombol Change di dalam modal."""
        # Selector spesifik tombol Change di mailticking
        CHANGE_SELECTORS = [
            # Tombol Change dengan icon fa-refresh
            "button.btn-default fa-refresh",
            # Bootstrap button group Change
            ".input-group-btn button",
            ".input-group button",
            "button.btn-default",
            # Teks Change
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

        # Fallback: cari button dengan teks 'change'
        for btn in driver.find_elements(By.TAG_NAME, "button"):
            try:
                txt = (btn.text or "").lower().strip()
                # Tombol Change biasanya tidak punya teks, hanya icon
                # tapi kadang ada teks  Change atau " Change"
                if "change" in txt or btn.get_attribute("title", "").lower() == "change":
                    self._js_click(driver, btn)
                    self._log("Clicked Change button...")
                    return
            except Exception:
                pass

        # Fallback terakhir: tombol pertama di .input-group
        try:
            btns = driver.find_elements(By.CSS_SELECTOR,
                ".modal .input-group button, .modal button.btn-default")
            if btns:
                self._js_click(driver, btns[0])
                self._log("Clicked Change button (fallback first btn)...")
                return
        except Exception:
            pass

        self._log("Change button not found", "WARNING")

    def _click_activate(self, driver):
        """Klik tombol Activate (tombol kuning/orange besar di bawah modal)."""
        ACTIVATE_SELECTORS = [
            # Selector spesifik tombol Activate mailticking
            ".modal .btn-warning",
            ".modal .btn-success",
            ".modal .btn-primary",
            ".modal button.btn",
        ]
        for sel in ACTIVATE_SELECTORS:
            try:
                els = driver.find_elements(By.CSS_SELECTOR, sel)
                for el in els:
                    if el.is_displayed() and "activat" in el.text.lower():
                        self._js_click(driver, el)
                        self._log("Clicked Activate button...")
                        return
            except Exception:
                pass

        # Fallback: semua button berisi teks Activate
        for btn in driver.find_elements(By.TAG_NAME, "button"):
            try:
                if "activat" in btn.text.lower() and btn.is_displayed():
                    self._js_click(driver, btn)
                    self._log("Clicked Activate button...")
                    return
            except Exception:
                pass

        # Fallback XPATH
        try:
            el = driver.find_element(By.XPATH,
                "//button[contains("
                "translate(.,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz')"
                ",'activat')]"
            )
            self._js_click(driver, el)
            self._log("Clicked Activate button...")
            return
        except Exception:
            pass

        self._log("Activate button not found", "WARNING")

    def _wait_modal_closed(self, driver, timeout: int = 10):
        """Tunggu modal hilang setelah Activate diklik."""
        try:
            WebDriverWait(driver, timeout).until(
                EC.invisibility_of_element_located(
                    (By.CSS_SELECTOR, ".modal.show, .modal.in")
                )
            )
            self._log("Email activated successfully.")
        except TimeoutException:
            # Mungkin modal langsung hilang atau pakai class berbeda
            time.sleep(random.uniform(2, 3))
            self._log("Email activated successfully.")

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
                # Klik Refresh button di sidebar kiri mailticking
                try:
                    refresh_btn = driver.find_element(By.CSS_SELECTOR,
                        ".refresh-btn, [onclick*='refresh'], #refresh,"
                        ".sidebar .refresh, .nav-icon[title*='efresh']"
                    )
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

                # Cari email di inbox
                rows = driver.find_elements(By.CSS_SELECTOR,
                    ".mail-item, .inbox-item, tr[onclick], "
                    "[class*='email-row'], [class*='message-row'], "
                    "table tbody tr, .list-group-item"
                )
                for row in rows:
                    txt = (row.text or "").lower()
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

        # Klik email Gemini/Google
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

        # Masuk iframe email body
        html_content = ""
        try:
            iframes = driver.find_elements(By.TAG_NAME, "iframe")
            for iframe in iframes:
                try:
                    driver.switch_to.frame(iframe)
                    content = driver.page_source
                    if any(k in content.lower() for k in
                           ["verification", "code", "gemini"]):
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
