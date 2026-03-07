"""
account_manager.py

Logika registrasi akun: email submit, OTP, nama, agree & get started,
dan initial setup (dismiss popup, tools, Veo selection).
"""

import time
import random

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import TimeoutException

from App.js_constants import (
    _JS_DISMISS_POPUP,
    _JS_CLICK_TOOLS,
    _JS_CLICK_VEO,
)

GEMINI_HOME_URL        = "https://business.gemini.google/"
OTP_TIMEOUT            = 90
MAX_ACCOUNT_RETRY      = 3
MAX_EMAIL_SUBMIT_RETRY = 5   # dinaikkan karena ada kemungkinan retry dari error page

# JS path exact untuk tombol "Sign up or sign in" di error page
_JS_SIGN_IN_ERROR_BTN = (
    'return document.querySelector('
    '"#yDmH0d > c-wiz > div > div > div > div > div > div '
    '> div > div > div > div > div > button > span.AeBiU-vQzf8d");'
)

# Teks yang mengindikasikan error page "Let's try something else"
_ERROR_PAGE_INDICATORS = [
    "let's try something else",
    "lets try something else",
    "trouble retrieving the email",
    "go back to sign up or sign in",
    "sign up or sign in",
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
        self._log(f"[W-{worker_id}] Step 1 & 2: Membuka business.gemini.google")
        try:
            driver.get(GEMINI_HOME_URL)
            WebDriverWait(driver, 20).until(lambda d: d.current_url != "about:blank")
        except Exception:
            pass
        self._wait_page_ready(driver, timeout=30, extra_selector="#email-input", label="Gemini Home (Email Input)")
        gemini_tab = driver.current_window_handle

        self._log("Step 3: Membuka mailticking.com di tab baru")
        driver.execute_script("window.open('about:blank', '_blank');")
        time.sleep(0.5)
        driver.switch_to.window(driver.window_handles[-1])
        mail_tab = driver.current_window_handle

        from App.mailticking import MAILTICKING_URL
        driver.get(MAILTICKING_URL)
        self._wait_page_ready(driver, timeout=30, label="mailticking.com")

        email = self._mail_client.get_fresh_email(driver)
        if not email or "@" not in email:
            self._log("Failed to get temp email", "ERROR")
            return False
        self._log(f"Temp email obtained: {email}")

        self._log("Step 4: Kembali ke Gemini, input email, crosscheck, dan lanjut")
        driver.switch_to.window(gemini_tab)

        submitted = self._step_4_submit_email(driver, email)
        if not submitted:
            return False

        self._log("Step 5: Tunggu OTP page dan 'code sent'")
        self._wait_page_ready(driver, timeout=20, label="OTP Page")
        otp_page_ok = self._wait_for_otp_page(driver)
        if not otp_page_ok:
            self._log("OTP page failed to load properly", "ERROR")
            return False
        self._log("OTP page loaded and 'Code sent' verified.")

        self._log("Step 6: Kembali ke mailticking, cek inbox")
        driver.switch_to.window(mail_tab)
        found = self._mail_client.wait_for_verification_email(
            driver,
            mail_tab_handle=mail_tab,
            gemini_tab_handle=gemini_tab,
            timeout=OTP_TIMEOUT,
        )
        if not found:
            self._log("Verification email not received (timeout)", "ERROR")
            return False

        self._log("Step 7: Ambil OTP, input di Gemini, lalu verify")
        otp = self._mail_client.extract_verification_code(driver, mail_tab_handle=mail_tab)
        if not otp:
            self._log("Could not extract OTP", "ERROR")
            return False
        self._log(f"OTP obtained: {otp}")

        driver.switch_to.window(gemini_tab)
        self._wait_page_ready(driver, timeout=15, label="Gemini Tab (OTP)")

        otp_submitted = False
        for otp_sub_try in range(1, 4):
            otp_submitted = self._submit_otp(driver, otp)
            if otp_submitted:
                break
            self._log(f"OTP submission attempt {otp_sub_try}/3 failed, retrying...", "WARNING")
            time.sleep(2)
        if not otp_submitted:
            self._log("OTP submission failed after 3 attempts", "ERROR")
            self._debug_dump(driver, "otp_submit_failed")
            return False
        self._log("OTP entered")
        time.sleep(random.uniform(0.3, 0.6))

        verify_clicked = False
        for verify_try in range(1, 4):
            verify_clicked = self._click_verify_button(driver)
            if verify_clicked:
                break
            self._log(f"Verify button attempt {verify_try}/3 failed", "WARNING")
            try:
                src = driver.page_source.lower()
                if any(k in src for k in ["full name", "fullname", "agree", "get started"]):
                    self._log("Page already past verification, continuing...")
                    verify_clicked = True
                    break
            except Exception:
                pass
            time.sleep(2)
        if not verify_clicked:
            self._log("Verify button click failed", "WARNING")

        self._log("Step 8: Tunggu isi nama, lalu Agree & get started")
        if not self._validate_step(driver, "Post-Verify",
                success_indicators=["full name", "fullname", "agree", "get started", "signing you in", "welcome"],
                failure_indicators=["invalid verification code", "wrong code", "code is incorrect"],
                timeout=30):
            return False

        name_entered = False
        for name_try in range(1, 4):
            try:
                name_entered = self._enter_name(driver)
                if name_entered:
                    break
                src = driver.page_source.lower()
                if any(k in src for k in ["signing you in", "welcome", "i'll do this later"]):
                    self._log("Page already past name entry, continuing...")
                    name_entered = True
                    break
            except Exception as e:
                self._log(f"Name entry error: {e}", "WARNING")
            time.sleep(3)
        if not name_entered:
            self._log("Name form not found after retries, proceeding...", "WARNING")

        self._validate_step(driver, "Post-Name",
            success_indicators=["agree", "get started", "signing you in", "welcome"],
            timeout=10)

        agree_clicked = False
        for agree_try in range(1, 4):
            try:
                agree_clicked = self._click_agree_button(driver)
                if agree_clicked:
                    break
                src = driver.page_source.lower()
                if any(k in src for k in ["signing you in", "welcome", "i'll do this later"]):
                    self._log("Page already past agree step, continuing...")
                    agree_clicked = True
                    break
            except Exception as e:
                self._log(f"Agree button error: {e}", "WARNING")
            time.sleep(2)
        if not agree_clicked:
            self._log("Agree button not clicked", "WARNING")

        self._log("Step 9: Tunggu signing in selesai")
        if not self._validate_step(driver, "Post-Agree",
                success_indicators=["signing you in", "welcome", "do this later", "gemini", "search"],
                failure_indicators=["something went wrong", "couldn't sign you in"],
                timeout=30):
            return False

        sign_in_ok = self._wait_gone(driver, "h1.title", timeout=60)
        self._log("Signing in completed.")
        self._wait_page_ready(driver, timeout=20, label="Post-SignIn")

        self._log("Step 10: Initial setup (dismiss popup, click tools, select Veo)")
        setup_ok = False
        for setup_try in range(1, 4):
            try:
                self._initial_setup(driver)
                setup_ok = True
                break
            except Exception as e:
                self._log(f"Initial setup error: {e}", "WARNING")
                time.sleep(3)
                try:
                    driver.refresh()
                    time.sleep(random.uniform(3, 5))
                except Exception:
                    pass
        if not setup_ok:
            return False

        self._log("Account registration and setup completed successfully!")
        return True

    # =========================================================================
    # Helper: deteksi dan tangani error page "Let's try something else"
    # =========================================================================

    def _is_lets_try_error_page(self, driver) -> bool:
        """Return True jika halaman menampilkan error 'Let's try something else'."""
        try:
            src = driver.page_source.lower()
            return any(k in src for k in _ERROR_PAGE_INDICATORS)
        except Exception:
            return False

    def _handle_lets_try_something_else(self, driver, email: str) -> bool:
        """
        Deteksi error page "Let's try something else".
        Klik tombol 'Sign up or sign in', tunggu kembali ke halaman email input,
        lalu submit email lagi.
        Return True jika berhasil kembali ke OTP flow.
        """
        self._log(
            "[!] 'Let's try something else' page detected! "
            "Clicking 'Sign up or sign in'...",
            "WARNING"
        )
        self._debug_dump(driver, "lets_try_error_page")

        clicked = False

        # Priority 1: exact JS path dari inspect element
        try:
            btn = driver.execute_script(_JS_SIGN_IN_ERROR_BTN)
            if btn and btn.is_displayed():
                driver.execute_script("arguments[0].click();", btn)
                self._log("Clicked 'Sign up or sign in' via exact JS path")
                clicked = True
        except Exception as e:
            self._log(f"Exact JS path click error: {e}", "WARNING")

        # Priority 2: cari tombol/link berdasarkan text
        if not clicked:
            for tag in ["button", "a", "span"]:
                try:
                    for el in driver.find_elements(By.TAG_NAME, tag):
                        txt = (el.text or "").strip().lower()
                        if "sign up" in txt or "sign in" in txt:
                            if el.is_displayed():
                                driver.execute_script("arguments[0].click();", el)
                                self._log(f"Clicked 'Sign up or sign in' via text fallback ({tag})")
                                clicked = True
                                break
                except Exception:
                    pass
                if clicked:
                    break

        # Priority 3: span class AeBiU-vQzf8d (inner span dari button)
        if not clicked:
            try:
                spans = driver.find_elements(By.CSS_SELECTOR, "span.AeBiU-vQzf8d")
                for span in spans:
                    if span.is_displayed():
                        # Klik parent button-nya
                        try:
                            parent = span.find_element(By.XPATH, "./ancestor::button")
                            driver.execute_script("arguments[0].click();", parent)
                        except Exception:
                            driver.execute_script("arguments[0].click();", span)
                        self._log("Clicked 'Sign up or sign in' via span.AeBiU-vQzf8d")
                        clicked = True
                        break
            except Exception:
                pass

        if not clicked:
            self._log("'Sign up or sign in' button not found, navigating to home...", "WARNING")
            try:
                driver.get(GEMINI_HOME_URL)
            except Exception:
                pass

        # Tunggu halaman kembali ke email input
        self._log("Waiting for email input page to load...")
        try:
            WebDriverWait(driver, 20).until(
                lambda d: any(k in d.current_url.lower() for k in [
                    "business.gemini.google",
                    "accounts.google",
                    "gemini.google",
                ]) and "lets-try" not in d.current_url.lower()
            )
        except TimeoutException:
            pass

        self._wait_page_ready(driver, timeout=20, label="Post-ErrorPage Recovery")

        # Verifikasi email input sudah ada
        email_el_present = False
        for check in range(8):
            try:
                el = driver.execute_script('return document.querySelector("#email-input");')
                if el and el.is_displayed():
                    email_el_present = True
                    break
            except Exception:
                pass
            time.sleep(1)

        if not email_el_present:
            self._log("Email input not found after recovery, navigating to home...", "WARNING")
            try:
                driver.get(GEMINI_HOME_URL)
                self._wait_page_ready(driver, timeout=20, extra_selector="#email-input")
            except Exception:
                pass

        self._log("Recovery complete - re-submitting email...")
        return True

    # =========================================================================
    # Step 4: Submit email + handle error page
    # =========================================================================

    def _step_4_submit_email(self, driver, email: str) -> bool:
        for attempt in range(1, MAX_EMAIL_SUBMIT_RETRY + 1):
            self._log(f"Submit email attempt {attempt}/{MAX_EMAIL_SUBMIT_RETRY}")

            # ── Cek dulu apakah kita di error page ──────────────────────────────────
            if self._is_lets_try_error_page(driver):
                recovered = self._handle_lets_try_something_else(driver, email)
                if not recovered:
                    self._log("Recovery from error page failed", "ERROR")
                    return False
                # Setelah recovery, lanjut ke input email di attempt berikutnya
                time.sleep(1)
                continue

            # ── Cari email input ──────────────────────────────────────────────────
            email_el = None
            try:
                email_el = driver.execute_script('return document.querySelector("#email-input");')
                if email_el and email_el.is_displayed():
                    self._log("Email input found: #email-input")
                else:
                    email_el = None
            except Exception:
                pass

            if not email_el:
                self._log("Email input not found", "WARNING")
                self._debug_dump(driver, f"no_email_input_attempt{attempt}")
                time.sleep(2)
                driver.refresh()
                self._wait_page_ready(driver, timeout=30, extra_selector="#email-input")
                continue

            if not self._verified_type(driver, email_el, email, field_name="Email"):
                self._log("Email input typing failed!", "ERROR")
                self._debug_dump(driver, f"email_verify_fail_{attempt}")
                continue

            actual_email = driver.execute_script("return arguments[0].value;", email_el) or ""
            if actual_email.strip().lower() != email.strip().lower():
                self._log(f"EMAIL MISMATCH! Expected: '{email}', Got: '{actual_email}'", "ERROR")
                self._debug_dump(driver, f"email_mismatch_{attempt}")
                continue
            self._log(f"Email cross-check OK: '{actual_email}'")
            time.sleep(random.uniform(0.3, 0.6))

            submit_el = None
            try:
                submit_el = driver.execute_script(
                    'return document.querySelector("#log-in-button > span.UywwFc-RLmnJb");'
                )
            except Exception:
                pass

            if submit_el and submit_el.is_displayed():
                self._human_click(driver, submit_el)
                self._log("Clicked 'Continue with email'")
            else:
                email_el.send_keys(Keys.RETURN)
                self._log("Pressed Enter to submit email")

            # ── Tunggu sebentar lalu cek apakah langsung kena error page ─────────
            time.sleep(2)
            if self._is_lets_try_error_page(driver):
                self._log("Error page appeared immediately after submit", "WARNING")
                recovered = self._handle_lets_try_something_else(driver, email)
                if not recovered:
                    return False
                continue  # retry submit dari awal

            return True

        self._log("Failed to submit email after all attempts", "ERROR")
        return False

    # =========================================================================
    def _wait_for_otp_page(self, driver) -> bool:
        self._log("Waiting for Gemini redirect to verification page...")
        deadline = time.time() + 60
        while time.time() < deadline:
            try:
                url = driver.current_url.lower()
                # Sukses: sudah di OTP page
                if any(k in url for k in [
                    "accountverification", "verify-oob-code",
                    "oauth2/authorize", "signin-callback"
                ]):
                    self._log(f"Target URL reached: {driver.current_url}")
                    break

                # Error page terdeteksi saat menunggu redirect
                if self._is_lets_try_error_page(driver):
                    self._log(
                        "'Let's try something else' detected while waiting for OTP redirect!",
                        "WARNING"
                    )
                    self._debug_dump(driver, "lets_try_during_otp_wait")
                    return False  # signal ke _register_once untuk retry

            except Exception:
                pass
            time.sleep(1)
        else:
            self._log(
                f"URL did not reach verification page after 60s. Current: {driver.current_url}",
                "WARNING"
            )
            self._debug_dump(driver, "email_redirect_timeout")

        self._wait_page_ready(driver, timeout=30, label="OTP/Verification Page Content")

        otp_content_ready = False
        for content_check in range(10):
            try:
                src = driver.page_source.lower()

                # Sekali lagi cek error page di sini
                if any(k in src for k in _ERROR_PAGE_INDICATORS):
                    self._log(
                        "'Let's try something else' detected on OTP wait!",
                        "WARNING"
                    )
                    self._debug_dump(driver, "lets_try_on_otp_content_check")
                    return False

                if any(k in src for k in ["code sent", "verification code", "enter verification"]):
                    otp_content_ready = True
                    self._log("OTP page content ('code sent') confirmed loaded")
                    break
            except Exception:
                pass
            time.sleep(2)

        if not otp_content_ready:
            self._log("OTP page 'code sent' not detected, proceeding anyway...", "WARNING")
            self._debug_dump(driver, "otp_content_not_found")

        if self._is_error_page(driver):
            self._log("Error page detected passing to OTP.", "ERROR")
            self._debug_dump(driver, "otp_error_page")
            return False
        return True

    def _submit_otp(self, driver, otp: str) -> bool:
        self._log(f"Attempting to enter OTP: {otp} ({len(otp)} chars)")
        self._wait_page_ready(driver, timeout=15, label="OTP Form")
        time.sleep(1)

        first_input = None
        for find_attempt in range(5):
            try:
                all_inputs = driver.find_elements(By.CSS_SELECTOR, "input")
                for inp in all_inputs:
                    try:
                        if inp.is_displayed():
                            inp_type = (inp.get_attribute("type") or "").lower()
                            if inp_type in ("text", "tel", "number", ""):
                                first_input = inp
                                break
                    except Exception:
                        pass
                if first_input:
                    self._log(f"OTP first input found (type={first_input.get_attribute('type')})")
                    break
            except Exception as e:
                self._log(f"OTP input search attempt {find_attempt+1}/5: {e}", "WARNING")
            time.sleep(2)

        if not first_input:
            self._log("OTP input NOT FOUND on page!", "ERROR")
            self._debug_dump(driver, "otp_input_not_found")
            return False

        for attempt in range(3):
            try:
                try:
                    first_input.click()
                except Exception:
                    driver.execute_script("arguments[0].focus();", first_input)
                time.sleep(0.3)
                self._log(f"Typing OTP char-by-char (attempt {attempt+1}/3)...")
                for char in otp:
                    ActionChains(driver).send_keys(char).perform()
                    time.sleep(random.uniform(0.15, 0.30))
                time.sleep(1)
                self._log(f"OTP typed successfully: {otp}")
                return True
            except Exception as e:
                self._log(f"OTP typing error (attempt {attempt+1}/3): {e}", "WARNING")
                time.sleep(2)
                try:
                    all_inputs = driver.find_elements(By.CSS_SELECTOR, "input")
                    for inp in all_inputs:
                        if inp.is_displayed() and (inp.get_attribute("type") or "").lower() in ("text", "tel", "number", ""):
                            first_input = inp
                            break
                except Exception:
                    pass

        self._log("OTP input failed after 3 attempts!", "ERROR")
        self._debug_dump(driver, "otp_typing_failed")
        return False

    def _click_verify_button(self, driver) -> bool:
        try:
            verify_btn = driver.execute_script(
                'return document.querySelector("#yDmH0d > c-wiz > div > div > div.keerLb > div > div > div > form > div.rPlx0b > div > div:nth-child(1) > span > div.VfPpkd-dgl2Hf-ppHlrf-sM5MNb > button > span.YUhpIc-RLmnJb");'
            )
            if verify_btn and verify_btn.is_displayed():
                self._human_click(driver, verify_btn)
                self._log("Clicked verify button via verified selector")
                return True
        except Exception as e:
            self._log(f"Verify button click error: {e}", "WARNING")

        for sel in [
            "button[jsname='LgbsSe']",
            "button[type='submit']",
            ".YUhpIc-RLmnJb",
        ]:
            try:
                els = driver.find_elements(By.CSS_SELECTOR, sel)
                for el in els:
                    if el.is_displayed():
                        self._human_click(driver, el)
                        self._log(f"Clicked verify via fallback: {sel}")
                        return True
            except Exception:
                pass

        for el in driver.find_elements(By.TAG_NAME, "button"):
            try:
                if any(w in el.text.lower() for w in ["verify", "confirm", "continue"]) and el.is_displayed():
                    self._human_click(driver, el)
                    self._log("Clicked verify (text fallback)")
                    return True
            except Exception:
                pass
        return False

    def _enter_name(self, driver) -> bool:
        name_el = None
        try:
            name_el = driver.execute_script('return document.querySelector("#mat-input-0");')
            if name_el and name_el.is_displayed():
                self._log("Name input found: #mat-input-0")
        except Exception:
            pass

        if not name_el:
            for sel in [
                "input[formcontrolname='fullName']",
                "input[placeholder='Full name']",
                "input[type='text'][required]",
            ]:
                el = self._wait_for(driver, sel, timeout=10)
                if el and el.is_displayed():
                    name_el = el
                    self._log(f"Name input found via fallback: {sel}")
                    break

        if name_el:
            name = _random_name()
            if self._verified_type(driver, name_el, name, field_name="Name"):
                return True
            self._fast_type(driver, name_el, name)
            self._log(f"Name entered (fallback): {name}")
            time.sleep(0.3)
            return True
        return False

    def _click_agree_button(self, driver) -> bool:
        try:
            agree_btn = driver.execute_script(
                'return document.querySelector("body > saasfe-root > main > saasfe-onboard-component > div > div > div > form > button > span.mat-mdc-button-touch-target");'
            )
            if agree_btn and agree_btn.is_displayed():
                self._human_click(driver, agree_btn)
                self._log("Clicked 'Agree & get started' via verified selector")
                return True
        except Exception as e:
            self._log(f"Agree button click error: {e}", "WARNING")

        for sel in [".mdc-button__label", "button.mdc-button", "button[mat-flat-button]"]:
            try:
                els = driver.find_elements(By.CSS_SELECTOR, sel)
                for el in els:
                    txt = (el.text or "").strip()
                    if "agree" in txt.lower() or "get started" in txt.lower():
                        try:
                            btn = el.find_element(By.XPATH, "./ancestor::button")
                            self._human_click(driver, btn)
                        except Exception:
                            self._human_click(driver, el)
                        self._log("Clicked 'Agree & get started' (fallback)")
                        return True
            except Exception:
                pass
        return False

    def _initial_setup(self, driver):
        self._log("Step 16: Closing 'I'll do this later' popup...")
        dismissed = False
        for dismiss_try in range(1, 4):
            try:
                btn = driver.execute_script(_JS_DISMISS_POPUP)
                if btn:
                    driver.execute_script("arguments[0].click();", btn)
                    self._log("Popup 'I'll do this later' dismissed")
                    dismissed = True
                    break
            except Exception as e:
                if dismiss_try < 3:
                    self._log(f"Dismiss popup attempt {dismiss_try}/3: {e}", "WARNING")
                    time.sleep(2)
                else:
                    self._log(f"Dismiss popup error: {e}", "WARNING")

        if not dismissed:
            self._log("No 'do this later' popup found, proceeding...", "WARNING")
        self._wait_page_ready(driver, timeout=15, label="Post-Dismiss Popup")

        self._log("Step 17: Clicking tools button...")
        tools_clicked = False
        for tools_try in range(1, 4):
            try:
                btn = driver.execute_script(_JS_CLICK_TOOLS)
                if btn:
                    driver.execute_script("arguments[0].click();", btn)
                    self._log("Tools button clicked")
                    tools_clicked = True
                    break
            except Exception as e:
                self._log(f"Tools button attempt {tools_try}/3: {e}", "WARNING")
            if tools_try < 3:
                time.sleep(2)
                try:
                    driver.refresh()
                    self._wait_page_ready(driver, timeout=20, label="Tools Refresh")
                except Exception:
                    pass

        if not tools_clicked:
            self._log("Tools button not found after retries", "WARNING")
            self._debug_dump(driver, "tools_btn_not_found")
            return

        self._wait_page_ready(driver, timeout=15, label="Post-Tools Click")

        self._log("Step 18: Selecting 'Create videos with Veo'...")
        veo_clicked = False
        for veo_try in range(1, 4):
            try:
                menu_item = driver.execute_script(_JS_CLICK_VEO)
                if menu_item:
                    driver.execute_script("arguments[0].click();", menu_item)
                    self._log("Clicked 'Create videos with Veo'")
                    veo_clicked = True
                    break
            except Exception as e:
                self._log(f"Veo menu attempt {veo_try}/3: {e}", "WARNING")

            if not veo_clicked:
                try:
                    for el in driver.find_elements(By.XPATH,
                            "//*[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ',"
                            "'abcdefghijklmnopqrstuvwxyz'),'create video') or "
                            "contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ',"
                            "'abcdefghijklmnopqrstuvwxyz'),'veo')]"):
                        try:
                            if el.is_displayed():
                                self._human_click(driver, el)
                                self._log("Clicked Veo (fallback text)")
                                veo_clicked = True
                                break
                        except Exception:
                            pass
                except Exception:
                    pass

            if veo_clicked:
                break
            if veo_try < 3:
                time.sleep(2)
                try:
                    btn = driver.execute_script(_JS_CLICK_TOOLS)
                    if btn:
                        driver.execute_script("arguments[0].click();", btn)
                        time.sleep(1.5)
                except Exception:
                    pass

        if not veo_clicked:
            self._log("Veo option not found after retries", "WARNING")
            self._debug_dump(driver, "veo_not_found")

        self._wait_page_ready(driver, timeout=15, label="Post-Veo Selection")
        self._log("Initial setup completed!")
