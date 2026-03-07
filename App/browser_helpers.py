"""
browser_helpers.py

Selenium helper methods: wait, type, click, page validation.
Dipakai sebagai mixin oleh GeminiEnterpriseProcessor.
"""

import time
import random
from typing import Optional

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys

from App.js_constants import _JS_GET_ALL_TEXT_DEEP

EMAIL_SUBMIT_ERROR_KEYWORDS = [
    "couldn't sign you in",
    "couldn't sign in",
    "can't sign you in",
    "disallowed_useragent",
    "access_denied",
    "error 400",
    "error 403",
    "something went wrong",
    "try again",
    "sign-in is not allowed",
    "not supported",
    "browser not supported",
    "let's try something else",
    "try something else",
    "had trouble retrieving",
]


class BrowserHelpersMixin:

    def _js_click(self, driver, element):
        driver.execute_script("arguments[0].click();", element)

    def _wait_for(self, driver, css_selector, timeout=15):
        try:
            return WebDriverWait(driver, timeout).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, css_selector)))
        except TimeoutException:
            return None

    def _wait_visible(self, driver, css_selector, timeout=15):
        try:
            return WebDriverWait(driver, timeout).until(
                EC.visibility_of_element_located((By.CSS_SELECTOR, css_selector)))
        except TimeoutException:
            return None

    def _wait_gone(self, driver, css_selector, timeout=60):
        try:
            el = driver.find_element(By.CSS_SELECTOR, css_selector)
            if el.is_displayed():
                self._log(f"Validation OK: Element '{css_selector}' exists. Waiting for it to disappear...")
            else:
                self._log(f"Element '{css_selector}' exists in DOM but already hidden.", "WARNING")
        except Exception:
            self._log(f"Element '{css_selector}' not found initially before wait_gone.", "WARNING")
        try:
            WebDriverWait(driver, timeout).until(
                EC.invisibility_of_element_located((By.CSS_SELECTOR, css_selector)))
            return True
        except TimeoutException:
            return False

    def _wait_page_ready(self, driver, timeout=30, extra_selector=None, label=""):
        tag = f" [{label}]" if label else ""
        try:
            WebDriverWait(driver, timeout).until(
                lambda d: d.execute_script("return document.readyState") == "complete"
            )
        except TimeoutException:
            self._log(f"Page readyState timeout{tag} ({timeout}s)", "WARNING")
        try:
            for _ in range(min(timeout, 15)):
                pending = driver.execute_script(
                    "try { return (window.performance.getEntriesByType('resource')"
                    ".filter(r => !r.responseEnd).length) } catch(e) { return 0; }"
                )
                if pending == 0:
                    break
                time.sleep(1)
        except Exception:
            pass
        time.sleep(0.5)
        if extra_selector:
            el = self._wait_visible(driver, extra_selector, timeout=min(timeout, 20))
            if not el:
                self._log(f"Extra element '{extra_selector}' not found{tag}", "WARNING")
        self._log(f"Page ready{tag}")

    def _close_extra_tabs(self, driver):
        try:
            handles = driver.window_handles
            if len(handles) > 1:
                main = handles[0]
                for h in handles[1:]:
                    try:
                        driver.switch_to.window(h)
                        driver.close()
                    except Exception:
                        pass
                driver.switch_to.window(main)
                self._log(f"Closed {len(handles) - 1} extra tab(s)")
        except Exception as e:
            self._log(f"Error closing tabs: {e}", "WARNING")

    def _verified_type(self, driver, element, text: str, field_name="field") -> bool:
        try:
            if not element.is_displayed() or not element.is_enabled():
                self._log(f"Validation FAILED: Input field '{field_name}' is not interactable!", "ERROR")
                return False
            self._log(f"Validation OK: Input field '{field_name}' is available.")
        except Exception as e:
            self._log(f"Error validating input field '{field_name}': {e}", "WARNING")

        for attempt in range(3):
            try:
                element.click()
                time.sleep(0.1)
                driver.execute_script(
                    "arguments[0].value = '';"
                    "arguments[0].value = arguments[1];"
                    "arguments[0].dispatchEvent(new Event('input', {bubbles:true}));"
                    "arguments[0].dispatchEvent(new Event('change', {bubbles:true}));",
                    element, text
                )
                time.sleep(0.3)
                actual = driver.execute_script("return arguments[0].value;", element) or ""
                if actual.strip() == text.strip():
                    self._log(f"{field_name} verified OK: '{text}'")
                    return True
                self._log(f"{field_name} mismatch (got '{actual}'), retrying with send_keys...", "WARNING")
                element.clear()
                time.sleep(0.1)
                element.send_keys(text)
                time.sleep(0.3)
                actual2 = driver.execute_script("return arguments[0].value;", element) or ""
                if actual2.strip() == text.strip():
                    self._log(f"{field_name} verified OK (send_keys): '{text}'")
                    return True
                self._log(f"{field_name} still mismatch: expected '{text}', got '{actual2}'", "WARNING")
            except Exception as e:
                self._log(f"{field_name} input error (attempt {attempt+1}): {e}", "WARNING")
            time.sleep(0.5)
        self._log(f"Failed to verify {field_name} input after 3 attempts!", "ERROR")
        return False

    def _validate_step(self, driver, step_name: str, success_indicators: list,
                       failure_indicators: list = None, timeout: int = 10) -> bool:
        self._wait_page_ready(driver, timeout=timeout, label=f"Validate: {step_name}")
        for check in range(3):
            try:
                src = driver.page_source.lower()
                url = driver.current_url.lower()
                combined = src + " " + url
                if failure_indicators:
                    if any(k in combined for k in failure_indicators):
                        self._log(f"STEP VALIDATION FAILED [{step_name}]: failure indicator found", "WARNING")
                        self._debug_dump(driver, f"validate_fail_{step_name}")
                        return False
                if any(k in combined for k in success_indicators):
                    self._log(f"STEP VALIDATED [{step_name}]: OK ✓")
                    return True
                if check < 2:
                    time.sleep(2)
            except Exception as e:
                self._log(f"Validation error [{step_name}]: {e}", "WARNING")
                time.sleep(2)
        self._log(f"STEP VALIDATION [{step_name}]: indicators not found, proceeding cautiously", "WARNING")
        self._debug_dump(driver, f"validate_uncertain_{step_name}")
        return True

    def _fast_type(self, driver, element, text: str):
        try:
            element.click()
            time.sleep(0.1)
            driver.execute_script(
                "arguments[0].value = '';"
                "arguments[0].value = arguments[1];"
                "arguments[0].dispatchEvent(new Event('input', {bubbles:true}));"
                "arguments[0].dispatchEvent(new Event('change', {bubbles:true}));",
                element, text
            )
            time.sleep(0.15)
        except Exception:
            self._human_type(driver, element, text)

    def _human_type(self, driver, element, text: str):
        try:
            if not element.is_displayed() or not element.is_enabled():
                self._log("Validation FAILED: Input field is not interactable!", "WARNING")
            else:
                self._log("Validation OK: Input field is available for typing.")
        except Exception:
            pass
        element.click()
        time.sleep(random.uniform(0.1, 0.2))
        element.clear()
        time.sleep(0.1)
        ac = ActionChains(driver)
        for char in text:
            ac.send_keys(char)
            ac.pause(random.uniform(0.03, 0.08))
        ac.perform()
        time.sleep(random.uniform(0.1, 0.3))

    def _human_click(self, driver, element):
        try:
            if element.is_displayed() and element.is_enabled():
                self._log("Validation OK: Button is available & clickable.")
            else:
                self._log("Validation FAILED: Button is not interactable/visible!", "WARNING")
        except Exception:
            pass
        try:
            ActionChains(driver).move_to_element(element).pause(
                random.uniform(0.05, 0.15)).click().perform()
        except Exception:
            element.click()

    def _is_error_page(self, driver) -> bool:
        try:
            src = driver.page_source.lower()
            url = driver.current_url.lower()
            if any(k in src for k in EMAIL_SUBMIT_ERROR_KEYWORDS):
                return True
            if any(k in url for k in [
                "error=", "disallowed", "access_denied",
                "authError", "servicerestricted"
            ]):
                return True
        except Exception:
            pass
        return False

    def _navigate_to_gemini_home(self, driver):
        from App.gemini_enterprise import GEMINI_HOME_URL
        self._log(f"Navigating to {GEMINI_HOME_URL} ...")
        try:
            from selenium.webdriver.support.ui import WebDriverWait
            driver.get(GEMINI_HOME_URL)
            WebDriverWait(driver, 20).until(
                lambda d: d.current_url != "about:blank")
        except Exception:
            pass
        self._wait_page_ready(driver, timeout=30, extra_selector="#email-input", label="Gemini Home")
