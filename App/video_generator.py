"""
video_generator.py

Logika input prompt, monitoring thinking/generation, dan download video
dari business.gemini.google via Shadow DOM.
"""

import os
import time
import random
import base64

from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys

from App.js_constants import (
    _JS_GET_PROMPT_INPUT,
    _JS_GET_THINKING,
    _JS_CLICK_DOWNLOAD,
    _JS_GET_ATTACHMENT_STATUS,
    _JS_GET_ALL_TEXT_DEEP,
    _JS_CLICK_REGENERATE,
    _JS_GET_VIDEO_SRC,
    _JS_FETCH_BLOB_BASE64,
)

VIDEO_GEN_TIMEOUT = 600
POLLING_INTERVAL = 3
RATE_LIMIT_THINKING_THRESHOLD = 5.0


class VideoGeneratorMixin:

    def _process_prompt(self, driver, prompt: str, prompt_num: int, total: int, delay: int) -> str:
        self._wait_page_ready(driver, timeout=15, label="Pre-Prompt Input")
        self._progress(int((prompt_num / total) * 100), f"Prompt {prompt_num}/{total}")

        self._log(f"Step 19: Inputting prompt {prompt_num}/{total}")
        typed_ok = False
        for input_try in range(1, 4):
            prompt_el = None
            try:
                prompt_el = driver.execute_script(_JS_GET_PROMPT_INPUT)
                if prompt_el and prompt_el.is_displayed():
                    self._log("Prompt input found via shadow DOM path")
            except Exception as e:
                self._log(f"Prompt input error: {e}", "WARNING")

            if not prompt_el:
                for sel in [
                    "div.ProseMirror",
                    "div[contenteditable='true'].ProseMirror",
                    "[contenteditable='true']",
                    "div[role='textbox']",
                    "textarea",
                ]:
                    el = self._wait_for(driver, sel, timeout=10)
                    if el and el.is_displayed():
                        prompt_el = el
                        self._log(f"Prompt input found via fallback: {sel}")
                        break

            if not prompt_el:
                self._log(f"Prompt input not found (attempt {input_try}/3)", "WARNING")
                self._debug_dump(driver, f"no_prompt_input_{input_try}")
                if input_try < 3:
                    time.sleep(3)
                    continue
                self._log("Prompt input not found after retries", "ERROR")
                return "error"

            try:
                driver.execute_script("arguments[0].click();", prompt_el)
                time.sleep(0.2)
                ActionChains(driver).key_down(Keys.CONTROL).send_keys("a").key_up(Keys.CONTROL).perform()
                time.sleep(0.1)
                ActionChains(driver).send_keys(Keys.DELETE).perform()
                time.sleep(0.1)

                driver.execute_script(
                    "arguments[0].focus();"
                    "document.execCommand('insertText', false, arguments[1]);",
                    prompt_el, prompt
                )
                inserted = driver.execute_script("return arguments[0].textContent;", prompt_el) or ""
                if prompt[:20] not in inserted:
                    self._log("insertText failed, fallback to Ctrl+V", "WARNING")
                    try:
                        import pyperclip
                        pyperclip.copy(prompt)
                        ActionChains(driver).key_down(Keys.CONTROL).send_keys("v").key_up(Keys.CONTROL).perform()
                    except Exception:
                        ac = ActionChains(driver)
                        i = 0
                        while i < len(prompt):
                            chunk = prompt[i:i + random.randint(5, 15)]
                            ac.send_keys(chunk)
                            ac.pause(0.02)
                            i += len(chunk)
                        ac.perform()
                self._log("Prompt entered (paste)")
                typed_ok = True
                break
            except Exception as e:
                self._log(f"Prompt typing error (attempt {input_try}/3): {e}", "WARNING")
                time.sleep(2)

        if not typed_ok:
            self._log("Failed to type prompt after retries", "ERROR")
            return "error"

        time.sleep(random.uniform(0.3, 0.5))
        self._log("Pressing Enter to generate...")
        try:
            ActionChains(driver).send_keys(Keys.RETURN).perform()
        except Exception as e:
            self._log(f"Enter key error: {e}", "WARNING")
            try:
                driver.execute_script(
                    "arguments[0].dispatchEvent(new KeyboardEvent('keydown',"
                    "{key:'Enter',code:'Enter',keyCode:13,bubbles:true}));",
                    prompt_el)
            except Exception:
                pass
        self._log("Generation started")
        self._wait_page_ready(driver, timeout=15, label="Post-Prompt Submit")
        return self._wait_for_generation(driver, prompt_num)

    def _wait_for_generation(self, driver, prompt_num: int) -> str:
        thinking_appeared = False
        thinking_start = None
        for check_i in range(20):
            try:
                thinking_el = driver.execute_script(_JS_GET_THINKING)
                if thinking_el and thinking_el.is_displayed():
                    thinking_appeared = True
                    thinking_start = time.time()
                    self._log("Thinking...")
                    break
            except Exception:
                pass

            if check_i > 0 and check_i % 5 == 0:
                try:
                    src = driver.page_source.lower()
                    try:
                        shadow_text = str(driver.execute_script(_JS_GET_ALL_TEXT_DEEP)).lower()
                        src = src + " " + shadow_text
                    except Exception:
                        pass
                    if any(k in src for k in ["rate limit", "quota exceeded", "try again later", "too many requests", "usage limit"]):
                        self._log("Rate limit detected on page (no thinking appeared)", "WARNING")
                        self._debug_dump(driver, f"rate_limit_no_think_{prompt_num}")
                        return "rate_limit"
                    if any(k in src for k in ["not allowed to perform this operation", "contact an administrator"]):
                        self._log("Permission block detected. Attempting regeneration...", "WARNING")
                        try:
                            driver.execute_script(_JS_CLICK_REGENERATE)
                        except Exception:
                            pass
                        time.sleep(2)
                        return self._wait_for_generation(driver, prompt_num)
                    if any(k in src for k in ["authentication required", "invalid authentication", "failed to load", "something went wrong", "couldn't generate", "unable to generate", "an error occurred"]):
                        self._log("Error message detected before thinking started", "ERROR")
                        self._debug_dump(driver, f"gen_error_no_think_{prompt_num}")
                        return "auth_error"
                except Exception:
                    pass
            time.sleep(0.5)

        if not thinking_appeared:
            self._log("Thinking never appeared — checking page state...", "WARNING")
            self._debug_dump(driver, f"no_thinking_{prompt_num}")
            try:
                src = driver.page_source.lower()
                try:
                    shadow_text = str(driver.execute_script(_JS_GET_ALL_TEXT_DEEP)).lower()
                    src = src + " " + shadow_text
                except Exception:
                    pass
                if any(k in src for k in ["rate limit", "quota exceeded", "try again later", "too many requests", "usage limit"]):
                    self._log("RATE LIMIT: explicit rate limit text found on page")
                    return "rate_limit"
                if any(k in src for k in ["authentication required", "invalid authentication", "failed to load", "something went wrong", "couldn't generate", "unable to generate", "an error occurred"]):
                    self._log("Auth/Load error detected on page (no thinking)", "ERROR")
                    return "auth_error"
                has_response = any(k in src for k in ["video", "render", "generat", "attachment", "download"])
                if not has_response:
                    self._log("RATE LIMIT: page is blank/unresponsive after prompt")
                    return "rate_limit"
            except Exception as e:
                self._log(f"Page check failed: {e}", "WARNING")
                return "rate_limit"

        if thinking_appeared and thinking_start:
            time.sleep(2)
            try:
                thinking_el = driver.execute_script(_JS_GET_THINKING)
                thinking_gone = not (thinking_el and thinking_el.is_displayed())
                elapsed = time.time() - thinking_start
                if thinking_gone and elapsed < RATE_LIMIT_THINKING_THRESHOLD:
                    self._log(f"Thinking gone in {elapsed:.1f}s - RATE LIMIT!")
                    return "rate_limit"
            except Exception:
                pass

        self._log("Waiting for thinking to complete...")
        start = time.time()
        while time.time() - start < 120:
            try:
                thinking_el = driver.execute_script(_JS_GET_THINKING)
                if not (thinking_el and thinking_el.is_displayed()):
                    break
            except Exception:
                break

            if int(time.time() - start) % 15 == 0 and int(time.time() - start) > 0:
                try:
                    src = driver.page_source.lower()
                    try:
                        shadow_text = str(driver.execute_script(_JS_GET_ALL_TEXT_DEEP)).lower()
                        src = src + " " + shadow_text
                    except Exception:
                        pass
                    if any(k in src for k in ["rate limit", "quota exceeded", "try again later", "too many requests", "usage limit"]):
                        self._log("Rate limit detected during thinking phase")
                        return "rate_limit"
                    if any(k in src for k in ["not allowed to perform this operation", "contact an administrator"]):
                        self._log("Permission block during thinking. Attempting regeneration...", "WARNING")
                        try:
                            driver.execute_script(_JS_CLICK_REGENERATE)
                        except Exception:
                            pass
                        time.sleep(2)
                        return self._wait_for_generation(driver, prompt_num)
                    if any(k in src for k in ["authentication required", "invalid authentication", "failed to load", "something went wrong", "couldn't generate", "unable to generate", "an error occurred"]):
                        self._log("Error message detected during thinking", "ERROR")
                        self._debug_dump(driver, f"gen_error_thinking_{prompt_num}")
                        return "auth_error"
                except Exception:
                    pass
            time.sleep(0.5)

        self._log("Thinking completed. Waiting for video render...")
        start = time.time()
        while time.time() - start < VIDEO_GEN_TIMEOUT:
            if self._cancelled:
                return "error"
            elapsed = int(time.time() - start)

            try:
                try:
                    attachment_text = driver.execute_script(_JS_GET_ATTACHMENT_STATUS)
                    if attachment_text:
                        att_lower = attachment_text.strip().lower()
                        if any(k in att_lower for k in ["failed to load", "failed", "error", "couldn't generate", "unable to generate", "something went wrong", "try again", "authentication required", "invalid authentication"]):
                            self._log(f"SHADOW DOM ERROR: '{attachment_text.strip()}' — triggering account restart", "WARNING")
                            self._debug_dump(driver, f"shadow_dom_error_{prompt_num}")
                            return "auth_error"
                except Exception:
                    pass

                src = driver.page_source.lower()
                try:
                    shadow_text = str(driver.execute_script(_JS_GET_ALL_TEXT_DEEP)).lower()
                    src = src + " " + shadow_text
                except Exception:
                    pass

                if any(k in src for k in ["rate limit", "quota exceeded", "try again later", "too many requests", "usage limit"]):
                    self._log("Rate limit message on page")
                    return "rate_limit"

                if any(k in src for k in ["not allowed to perform this operation", "contact an administrator"]):
                    self._log("Permission block during post-generation. Attempting regeneration...", "WARNING")
                    try:
                        driver.execute_script(_JS_CLICK_REGENERATE)
                    except Exception:
                        pass
                    time.sleep(2)
                    return self._wait_for_generation(driver, prompt_num)

                if any(k in src for k in ["authentication required", "invalid authentication", "failed to load attachment", "failed to load", "something went wrong", "couldn't generate", "unable to generate", "content generation error", "an error occurred"]):
                    self._log("Auth or Generation error detected during generation", "ERROR")
                    self._debug_dump(driver, f"gen_failed_{prompt_num}")
                    return "auth_error"

                try:
                    dl_btn = driver.execute_script(_JS_CLICK_DOWNLOAD)
                    if dl_btn:
                        break
                except Exception:
                    pass

                if elapsed % 15 == 0 and elapsed > 0:
                    self._log(f"Still rendering... ({elapsed}s)")

            except Exception:
                pass
            time.sleep(POLLING_INTERVAL)
        else:
            self._log("Video generation timeout", "WARNING")
            return "error"

        self._log("Video render complete!")
        return self._download_video(driver, prompt_num)

    def _download_video(self, driver, prompt_num: int) -> str:
        self._log(f"Step 21: Extracting generated Video Blob... (Prompt {prompt_num})")

        blob_url = None
        for try_idx in range(1, 4):
            try:
                blob_url = driver.execute_script(_JS_GET_VIDEO_SRC)
                if blob_url and blob_url.startswith("blob:"):
                    self._log(f"Found Blob URL: {blob_url}")
                    break
            except Exception:
                pass
            time.sleep(2)

        if not blob_url:
            self._log("Failed to locate <video> Blob URL inside Shadow DOM!", "ERROR")
            self._debug_dump(driver, "no_blob_ext")
            return "error"

        self._log("Fetching video blob buffer via Base64 injection...")
        try:
            b64_string = driver.execute_async_script(_JS_FETCH_BLOB_BASE64, blob_url)
        except Exception as e:
            self._log(f"Javascript Blob fetch failed: {e}", "ERROR")
            self._debug_dump(driver, "blob_fetch_err")
            return "error"

        if not b64_string:
            self._log("Javascript returned an empty buffer.", "ERROR")
            return "error"

        if b64_string.startswith("ERROR:"):
            self._log(f"Javascript internal fetch error: {b64_string}", "ERROR")
            return "error"

        self._log("Decoding Base64 payload back to binary MP4...")
        try:
            video_data = base64.b64decode(b64_string)
        except Exception as e:
            self._log(f"Failed to decode base64 video string: {e}", "ERROR")
            return "error"

        fname = f"ReenzAuto_G-Business_{prompt_num}_{int(time.time() * 1000)}.mp4"
        dest = os.path.join(self.output_dir, fname)
        try:
            with open(dest, 'wb') as f:
                f.write(video_data)
            self._log(f"Video saved natively to: {fname}", "SUCCESS")
        except Exception as e:
            self._log(f"Could not write file to disk: {e}", "ERROR")
            return "error"

        self._log(f"Successfully processed prompt {prompt_num}")
        return "ok"
