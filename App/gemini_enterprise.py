"""
gemini_enterprise.py

Entry point utama — slim orchestrator.
Semua logika dipecah ke modul terpisah:
  - App/js_constants.py       : Shadow DOM JS selectors
  - App/chrome_utils.py       : Chrome version & ChromeDriver setup
  - App/browser_helpers.py    : Selenium helper methods (mixin)
  - App/account_manager.py    : Account registration, email/OTP (mixin)
  - App/video_generator.py    : Prompt input, generation, download (mixin)
"""

import os
import shutil
import tempfile
import threading
import time
import math
from typing import Optional, Callable
from concurrent.futures import ThreadPoolExecutor

from PySide6.QtCore import QThread, Signal

try:
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.chrome.options import Options
except ImportError:
    pass

try:
    from selenium_stealth import stealth
except ImportError:
    stealth = None

from App.mailticking import MailtickingClient
from App.chrome_utils import _setup_chromedriver
from App.browser_helpers import BrowserHelpersMixin
from App.account_manager import AccountManagerMixin
from App.video_generator import VideoGeneratorMixin

GEMINI_HOME_URL = "https://business.gemini.google/"

MAX_TAB_RETRY = 3
MAX_ACCOUNT_RETRY = 3


class GeminiEnterpriseProcessor(BrowserHelpersMixin, AccountManagerMixin, VideoGeneratorMixin, QThread):
    log_signal           = Signal(str, str)
    progress_signal      = Signal(int, str)
    finished_signal      = Signal(bool, str, str)
    prompt_status_signal = Signal(int, str)

    def __init__(
        self,
        base_dir:          str,
        prompts:           list,
        output_dir:        str,
        config:            dict,
        log_callback:      Optional[Callable] = None,
        progress_callback: Optional[Callable] = None,
        finished_callback: Optional[Callable] = None,
        start_index:       int = 0,
    ):
        super().__init__()
        self.base_dir       = base_dir
        self.prompts        = prompts
        self.output_dir     = output_dir or os.path.join(base_dir, "OUTPUT_GEMINI")
        self.config         = config
        self.log_cb         = log_callback
        self.progress_cb    = progress_callback
        self.finished_cb    = finished_callback
        self.start_index    = start_index
        self._cancelled     = False
        self.active_drivers = []
        self._mail_client   = MailtickingClient(log_callback=log_callback)
        self.debug_dir      = os.path.join(base_dir, "DEBUG")

    # ── Signal/callback helpers ──────────────────────────────────────────
    def _log(self, msg, level="INFO"):
        if self.log_cb:
            self.log_cb(msg, level)
        self.log_signal.emit(msg, level)

    def _progress(self, pct, msg):
        if self.progress_cb:
            self.progress_cb(pct, msg)
        self.progress_signal.emit(pct, msg)

    def _done(self, ok, msg, path=""):
        if self.finished_cb:
            self.finished_cb(ok, msg, path)
        self.finished_signal.emit(ok, msg, path)

    def cancel(self):
        self._cancelled = True
        for d in self.active_drivers:
            try:
                d.quit()
            except Exception:
                pass

    def _debug_dump(self, driver, label: str):
        try:
            os.makedirs(self.debug_dir, exist_ok=True)
            ts = int(time.time())
            driver.save_screenshot(os.path.join(self.debug_dir, f"{label}_{ts}.png"))
        except Exception:
            pass

    # ── Driver setup ─────────────────────────────────────────────────────
    def _create_driver(self) -> tuple[Optional[object], Optional[str]]:
        self._log("Setting up fresh Chrome browser...")
        cd_path = _setup_chromedriver(self.base_dir, self._log)
        temp_profile = tempfile.mkdtemp(prefix="gemini_profile_")
        self._log(f"Using fresh browser profile: {temp_profile}")

        headless = self.config.get("headless", False)
        # Incognito mode: default True, bisa dimatikan via config {"incognito": false}
        incognito = self.config.get("incognito", True)

        opts = Options()
        opts.add_argument(f"--user-data-dir={temp_profile}")
        opts.add_argument("--no-first-run")
        opts.add_argument("--no-default-browser-check")
        opts.add_argument("--disable-blink-features=AutomationControlled")
        opts.add_argument("--disable-infobars")
        opts.add_argument("--lang=en-US")
        opts.add_argument("--window-size=1280,900")
        opts.add_argument("--disable-popup-blocking")
        if incognito:
            opts.add_argument("--incognito")
            self._log("Chrome incognito mode: ENABLED")
        opts.add_experimental_option("excludeSwitches", ["enable-automation"])
        opts.add_experimental_option("useAutomationExtension", False)
        opts.add_experimental_option("prefs", {
            "intl.accept_languages": "en,en_US",
            "download.default_directory": self.output_dir,
            "download.prompt_for_download": False,
            "download.directory_upgrade": True,
            "safebrowsing.enabled": True,
        })
        if headless:
            opts.add_argument("--headless=new")

        try:
            if cd_path:
                svc    = Service(executable_path=cd_path)
                driver = webdriver.Chrome(service=svc, options=opts)
            else:
                driver = webdriver.Chrome(options=opts)

            self.active_drivers.append(driver)

            if stealth and self.config.get("stealth", True):
                stealth(driver,
                    languages=["en-US", "en"],
                    vendor="Google Inc.",
                    platform="Win32",
                    webgl_vendor="Intel Inc.",
                    renderer="Intel Iris OpenGL Engine",
                    fix_hairline=True,
                )

            driver.execute_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            self._log("Chrome browser initialized")
            return driver, temp_profile
        except Exception as e:
            self._log(f"Failed to create Chrome driver: {e}", "ERROR")
            return None, None

    def _quit_driver(self, driver, temp_profile):
        try:
            if driver:
                if driver in self.active_drivers:
                    self.active_drivers.remove(driver)
                driver.quit()
        except Exception:
            pass
        if temp_profile and os.path.exists(temp_profile):
            shutil.rmtree(temp_profile, ignore_errors=True)

    # ── Main run ──────────────────────────────────────────────────────────
    def run(self):
        os.makedirs(self.output_dir, exist_ok=True)
        total       = len(self.prompts)
        delay       = int(self.config.get("delay", 5))
        retries     = int(self.config.get("retry", 1))
        max_workers = int(self.config.get("max_workers", 1))

        self._log("--- STARTING AUTOMATION ---")
        self._log(f"Total prompts: {total} | Max Workers: {max_workers}")
        self._log(f"Settings: delay {delay}s, retry {retries}x")

        self._completed_lock  = threading.Lock()
        self._completed_count = self.start_index

        todos = self.prompts[self.start_index:]
        if not todos:
            self._done(True, "All prompts already processed.")
            return

        if max_workers <= 1:
            chunks = [todos]
        else:
            chunk_size = math.ceil(len(todos) / max_workers)
            chunks = [todos[i:i + chunk_size] for i in range(0, len(todos), chunk_size)]

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = []
            curr_global_idx = self.start_index
            for w_idx, chunk in enumerate(chunks, 1):
                futures.append(executor.submit(self._worker_run, w_idx, chunk, curr_global_idx, total))
                curr_global_idx += len(chunk)
                if w_idx < len(chunks):
                    self._log(f"Waiting 10s before starting Worker {w_idx + 1}...")
                    time.sleep(10)

            for f in futures:
                try:
                    f.result()
                except Exception as e:
                    self._log(f"Worker crashed: {e}", "ERROR")

        if not self._cancelled:
            self._log("All workers finished!")
            self._done(True, f"Done! {self._completed_count} prompts processed.")
        else:
            self._done(False, "Cancelled.")

    def _worker_run(self, worker_id: int, chunk: list, start_global_idx: int, total_prompts: int):
        self._log(f"[W-{worker_id}] Started processing {len(chunk)} prompts")
        delay   = int(self.config.get("delay", 5))
        retries = int(self.config.get("retry", 1))

        current_idx     = 0
        re_enter_prompt = None

        while current_idx < len(chunk) and not self._cancelled:
            driver, temp_profile = self._create_driver()
            if driver is None:
                self._log(f"[W-{worker_id}] Failed to create browser.", "ERROR")
                return

            ok = self._register_account(driver, worker_id)
            if not ok:
                self._quit_driver(driver, temp_profile)
                self._log(f"[W-{worker_id}] Account registration failed.", "ERROR")
                return

            rate_limited = False
            gen_retries  = {}

            while current_idx < len(chunk) and not self._cancelled:
                prompt     = re_enter_prompt or chunk[current_idx]
                re_enter_prompt = None
                prompt_num = start_global_idx + current_idx + 1

                self._log(f"[W-{worker_id}] --- Processing Prompt {prompt_num}/{total_prompts} ---")
                if self.prompt_status_signal:
                    self.prompt_status_signal.emit(prompt_num - 1, "loading")

                result = self._process_prompt(driver, prompt, prompt_num, total_prompts, delay)

                if result == "rate_limit":
                    self._log(f"[W-{worker_id}] Rate limit detected - switching account...")
                    rate_limited    = True
                    re_enter_prompt = prompt
                    break
                elif result == "auth_error":
                    self._log(f"[W-{worker_id}] Auth/load error - recreating account...")
                    rate_limited    = True
                    re_enter_prompt = prompt
                    break
                elif result == "ok":
                    gen_retries.pop(current_idx, None)
                    if self.prompt_status_signal:
                        self.prompt_status_signal.emit(prompt_num - 1, "success")
                    current_idx += 1
                    with self._completed_lock:
                        self._completed_count += 1
                        pct = int((self._completed_count / total_prompts) * 100)
                        self._progress(pct, f"Processed {self._completed_count}/{total_prompts} prompts")
                    if current_idx < len(chunk):
                        time.sleep(delay)
                else:
                    count = gen_retries.get(current_idx, 0) + 1
                    gen_retries[current_idx] = count
                    if count < retries:
                        self._log(f"[W-{worker_id}] Prompt {prompt_num} failed (attempt {count}/{retries}), retrying...", "WARNING")
                        if self.prompt_status_signal:
                            self.prompt_status_signal.emit(prompt_num - 1, "error")
                        time.sleep(delay)
                        try:
                            driver.get(GEMINI_HOME_URL)
                            self._wait_page_ready(driver, timeout=20, label="Worker Retry Nav")
                            self._initial_setup(driver)
                        except Exception:
                            pass
                        re_enter_prompt = prompt
                    else:
                        self._log(f"[W-{worker_id}] Skipping prompt {prompt_num} after {count} failed attempts", "WARNING")
                        if self.prompt_status_signal:
                            self.prompt_status_signal.emit(prompt_num - 1, "error")
                        gen_retries.pop(current_idx, None)
                        current_idx += 1
                        with self._completed_lock:
                            self._completed_count += 1
                            pct = int((self._completed_count / total_prompts) * 100)
                            self._progress(pct, f"Processed {self._completed_count}/{total_prompts} prompts")

            self._quit_driver(driver, temp_profile)
            if rate_limited:
                time.sleep(5)
