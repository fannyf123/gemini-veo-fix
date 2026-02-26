"""
gemini_enterprise.py

Otomasi login + generate video di business.gemini.google
via Playwright + OTP otomatis dari GmailOTPReader.

Flow:
    1. Buka auth.business.gemini.google/login
    2. Input email (Firefox Relay mask)
    3. OTP otomatis via GmailOTPReader
    4. Masuk dashboard Gemini Enterprise
    5. Klik "+" → "Create videos with Veo"
    6. Input prompt → submit
    7. Polling hingga video selesai
    8. Download → simpan ke OUTPUT_GEMINI/
"""

import os
import re
import time
import threading
from typing import Optional, Callable

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

from App.gmail_otp import GmailOTPReader
from App.firefox_relay import FirefoxRelay

GEMINI_LOGIN_URL  = "https://auth.business.gemini.google/login?continueUrl=https://business.gemini.google/"
GEMINI_HOME_URL   = "https://business.gemini.google/"

OTP_TIMEOUT       = 120
VIDEO_GEN_TIMEOUT = 600
POLLING_INTERVAL  = 8
MAX_OTP_RETRY     = 3


class GeminiEnterpriseProcessor(threading.Thread):
    """
    Satu thread = satu sesi generate video Gemini Enterprise.
    """

    def __init__(
        self,
        base_dir:          str,
        prompt:            str,
        mask_email:        str,
        output_dir:        str,
        config:            dict,
        log_callback:      Optional[Callable] = None,
        progress_callback: Optional[Callable] = None,
        finished_callback: Optional[Callable] = None,
    ):
        super().__init__(daemon=True)
        self.base_dir    = base_dir
        self.prompt      = prompt
        self.mask_email  = mask_email
        self.output_dir  = output_dir or os.path.join(base_dir, "OUTPUT_GEMINI")
        self.config      = config
        self.log_cb      = log_callback
        self.progress_cb = progress_callback
        self.finished_cb = finished_callback
        self._cancelled  = False
        self._otp_reader = GmailOTPReader(base_dir)

    def _log(self, msg, level="INFO"):
        if self.log_cb: self.log_cb(msg, level)

    def _progress(self, pct, msg):
        if self.progress_cb: self.progress_cb(pct, msg)

    def _done(self, ok, msg, path=""):
        if self.finished_cb: self.finished_cb(ok, msg, path)

    def cancel(self):
        self._cancelled = True

    # ──────────────────────────────────────────────────────────────
    def run(self):
        os.makedirs(self.output_dir, exist_ok=True)
        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch(
                    headless=self.config.get("headless", True),
                    args=["--no-sandbox", "--disable-blink-features=AutomationControlled"]
                )
                ctx = browser.new_context(
                    viewport={"width": 1280, "height": 900},
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/122.0.0.0 Safari/537.36"
                    ),
                    locale="en-US",
                )
                page   = ctx.new_page()
                result = self._run_session(page)
                browser.close()

            if result:
                self._done(True, f"✅ Video tersimpan: {result}", result)
            else:
                self._done(False, "Generate video gagal atau dibatalkan.")
        except Exception as e:
            self._log(f"❌ Fatal error: {e}", "ERROR")
            self._done(False, str(e))

    # ──────────────────────────────────────────────────────────────
    def _run_session(self, page) -> Optional[str]:

        # ── 1. Buka halaman login ──────────────────────────────────
        self._log("🌐 Membuka halaman login Gemini Enterprise...")
        self._progress(5, "Membuka halaman login...")
        page.goto(GEMINI_LOGIN_URL, wait_until="domcontentloaded", timeout=30_000)
        page.wait_for_timeout(2000)
        if self._cancelled: return None

        # ── 2. Input email ─────────────────────────────────────────
        self._log(f"📧 Input email: {self.mask_email}")
        self._progress(10, "Input email...")
        try:
            email_input = page.wait_for_selector(
                "input[type='email'], input[name='email'], input[placeholder*='mail']",
                timeout=15_000
            )
            email_input.fill(self.mask_email)
            page.wait_for_timeout(800)
            btn = page.query_selector(
                "button[type='submit'], button:has-text('Continue'), "
                "button:has-text('Next'), button:has-text('Send')"
            )
            if btn: btn.click()
            else:   page.keyboard.press("Enter")
            self._log("✅ Email tersubmit, menunggu halaman OTP...")
            page.wait_for_timeout(2500)
        except PWTimeout:
            self._log("❌ Input email tidak ditemukan!", "ERROR")
            return None
        if self._cancelled: return None

        # ── 3. Baca OTP dari Gmail ─────────────────────────────────
        self._progress(20, "Menunggu OTP dari Gmail...")
        otp_code = None
        reg_ts   = int(time.time())

        for attempt in range(1, MAX_OTP_RETRY + 1):
            self._log(f"📬 Polling OTP (percobaan {attempt}/{MAX_OTP_RETRY})...")
            try:
                otp_code = self._otp_reader.wait_for_otp(
                    sender          = "google.com",
                    timeout         = OTP_TIMEOUT,
                    interval        = 5,
                    log_callback    = self.log_cb,
                    mask_email      = self.mask_email,
                    after_timestamp = reg_ts,
                )
                self._log(f"✅ OTP: {otp_code}", "SUCCESS")
                break
            except TimeoutError:
                self._log(f"⚠️  OTP timeout (percobaan {attempt})", "WARNING")
                if attempt < MAX_OTP_RETRY:
                    resend = page.query_selector(
                        "button:has-text('Resend'), a:has-text('Resend'), "
                        "button:has-text('Send again')"
                    )
                    if resend:
                        self._log("🔄 Klik Resend OTP...")
                        resend.click()
                        page.wait_for_timeout(2000)
                        reg_ts = int(time.time())
                    else:
                        self._log("🔄 Kembali ke halaman login...")
                        page.goto(GEMINI_LOGIN_URL, wait_until="domcontentloaded")
                        page.wait_for_timeout(1500)
                        ei = page.query_selector("input[type='email'], input[name='email']")
                        if ei:
                            ei.fill(self.mask_email)
                            page.keyboard.press("Enter")
                            page.wait_for_timeout(2000)
                            reg_ts = int(time.time())

        if not otp_code:
            self._log("❌ Gagal dapat OTP setelah semua percobaan!", "ERROR")
            return None
        if self._cancelled: return None

        # ── 4. Input OTP ke form ───────────────────────────────────
        self._progress(35, "Memasukkan kode OTP...")
        self._log("✏️  Input OTP ke form...")
        try:
            otp_inputs = page.query_selector_all(
                "input[type='text'][maxlength='1'], "
                "input[autocomplete='one-time-code'], "
                "input[name*='otp'], input[name*='code'], "
                "input[placeholder*='code']"
            )
            if len(otp_inputs) > 1:
                for i, digit in enumerate(otp_code[:len(otp_inputs)]):
                    otp_inputs[i].fill(digit)
                    page.wait_for_timeout(120)
            elif len(otp_inputs) == 1:
                otp_inputs[0].fill(otp_code)
            else:
                page.keyboard.type(otp_code, delay=100)

            page.wait_for_timeout(800)
            verify_btn = page.query_selector(
                "button[type='submit'], button:has-text('Verify'), "
                "button:has-text('Continue'), button:has-text('Sign in')"
            )
            if verify_btn: verify_btn.click()
            else:          page.keyboard.press("Enter")

            self._log("✅ OTP tersubmit, menunggu redirect dashboard...")
            page.wait_for_url("**/business.gemini.google/**", timeout=20_000)
            self._log("✅ Login berhasil!", "SUCCESS")
        except PWTimeout:
            self._log("❌ Login gagal — redirect timeout!", "ERROR")
            return None
        if self._cancelled: return None

        # ── 5. Klik "+" → "Create videos with Veo" ────────────────
        self._progress(50, "Membuka menu Create videos with Veo...")
        self._log("🎬 Mencari menu tools...")
        page.wait_for_timeout(2500)
        try:
            # Klik tombol tools (di samping tombol +)
            tools_btn = page.wait_for_selector(
                "button[aria-label*='tool'], button[aria-label*='attach'], "
                "[role='button'][aria-label*='more'], button[jsname], "
                "button:has-text('+')",
                timeout=10_000
            )
            tools_btn.click()
            page.wait_for_timeout(1000)

            # Klik item "Create videos with Veo"
            veo_item = page.wait_for_selector(
                "[role='menuitem']:has-text('Create videos with Veo'), "
                "li:has-text('Create videos with Veo'), "
                "div:has-text('Create videos with Veo')",
                timeout=8_000
            )
            veo_item.click()
            self._log("✅ 'Create videos with Veo' dipilih!", "SUCCESS")
            page.wait_for_timeout(1500)
        except PWTimeout:
            self._log("❌ Menu 'Create videos with Veo' tidak ditemukan!", "ERROR")
            return None
        if self._cancelled: return None

        # ── 6. Input prompt ────────────────────────────────────────
        self._progress(60, "Memasukkan prompt video...")
        self._log(f"✏️  Prompt: {self.prompt[:80]}...")
        try:
            prompt_el = page.wait_for_selector(
                "textarea, [contenteditable='true'], "
                "input[placeholder*='prompt'], input[placeholder*='describe']",
                timeout=10_000
            )
            prompt_el.click()
            prompt_el.fill(self.prompt)
            page.wait_for_timeout(800)

            send_btn = page.query_selector(
                "button[aria-label*='send'], button[aria-label*='generate'], "
                "button[aria-label*='Submit'], button[type='submit']"
            )
            if send_btn: send_btn.click()
            else:        page.keyboard.press("Enter")

            self._log("✅ Prompt tersubmit! Menunggu Veo generate...", "SUCCESS")
        except PWTimeout:
            self._log("❌ Input prompt tidak ditemukan!", "ERROR")
            return None
        if self._cancelled: return None

        # ── 7. Polling sampai video siap ───────────────────────────
        self._progress(70, "Menunggu Veo generate video...")
        self._log(f"⏳ Polling max {VIDEO_GEN_TIMEOUT}s...")
        start      = time.time()
        video_ready = False

        while time.time() - start < VIDEO_GEN_TIMEOUT:
            if self._cancelled: return None
            elapsed = int(time.time() - start)
            pct     = min(70 + int((elapsed / VIDEO_GEN_TIMEOUT) * 18), 88)
            self._progress(pct, f"Generate... {elapsed}s/{VIDEO_GEN_TIMEOUT}s")

            # Cek tombol Download muncul
            dl = page.query_selector(
                "button:has-text('Download'), a[download], "
                "button[aria-label*='download'], [role='button']:has-text('Download')"
            )
            if dl:
                self._log("✅ Video siap didownload!", "SUCCESS")
                video_ready = True
                break

            # Cek elemen video langsung
            vid = page.query_selector("video[src]")
            if vid and vid.get_attribute("src") and "blob" not in (vid.get_attribute("src") or ""):
                self._log("✅ Elemen video ditemukan!", "SUCCESS")
                video_ready = True
                break

            time.sleep(POLLING_INTERVAL)

        if not video_ready:
            self._log(f"❌ Timeout {VIDEO_GEN_TIMEOUT}s — video tidak selesai.", "ERROR")
            return None
        if self._cancelled: return None

        # ── 8. Download video ──────────────────────────────────────
        self._progress(90, "Mendownload video...")
        self._log("📥 Mendownload video hasil...")
        try:
            out_path = os.path.join(
                self.output_dir, f"gemini_veo_{int(time.time())}.mp4"
            )
            with page.expect_download(timeout=120_000) as dl_info:
                dl_btn = page.query_selector(
                    "button:has-text('Download'), a[download], "
                    "button[aria-label*='download']"
                )
                if dl_btn: dl_btn.click()
                else: raise Exception("Tombol download tidak ditemukan")

            dl_info.value.save_as(out_path)
            self._log(f"✅ Video tersimpan: {out_path}", "SUCCESS")
            self._progress(100, "Selesai!")
            return out_path
        except Exception as e:
            self._log(f"❌ Download gagal: {e}", "ERROR")
            return None
