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

# ── Semua kemungkinan selector email input ─────────────────────────────────
EMAIL_SELECTORS = [
    "input[type='email']",
    "input[name='email']",
    "input[id*='email']",
    "input[placeholder*='mail']",
    "input[placeholder*='Email']",
    "input[autocomplete='email']",
    "input[jsname]",                 # Google sering pakai jsname
    "input[type='text']",            # fallback: text input biasa
    "input",                         # fallback total
]

# ── Selector submit button ─────────────────────────────────────────────────
SUBMIT_SELECTORS = [
    "button[type='submit']",
    "button:has-text('Continue')",
    "button:has-text('Next')",
    "button:has-text('Send')",
    "button:has-text('Sign in')",
    "[role='button']:has-text('Continue')",
    "[jsname][role='button']",
]


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
        self.debug_dir   = os.path.join(base_dir, "DEBUG")

    def _log(self, msg, level="INFO"):
        if self.log_cb: self.log_cb(msg, level)

    def _progress(self, pct, msg):
        if self.progress_cb: self.progress_cb(pct, msg)

    def _done(self, ok, msg, path=""):
        if self.finished_cb: self.finished_cb(ok, msg, path)

    def cancel(self):
        self._cancelled = True

    # ── Debug helper: simpan screenshot + HTML ────────────────────────────
    def _debug_dump(self, page, label: str):
        """Simpan screenshot dan HTML ke folder DEBUG/ untuk analisis."""
        try:
            os.makedirs(self.debug_dir, exist_ok=True)
            ts       = int(time.time())
            ss_path  = os.path.join(self.debug_dir, f"{label}_{ts}.png")
            html_path= os.path.join(self.debug_dir, f"{label}_{ts}.html")

            page.screenshot(path=ss_path, full_page=True)
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(page.content())

            self._log(f"🔍 DEBUG screenshot: {ss_path}", "WARNING")
            self._log(f"🔍 DEBUG HTML dump : {html_path}", "WARNING")
        except Exception as e:
            self._log(f"⚠️  Debug dump gagal: {e}", "WARNING")

    # ── Cari input element dengan multi-selector fallback ─────────────────
    def _find_input(self, page, selectors: list, timeout_ms: int = 15_000):
        """
        Coba selector satu per satu sampai ada yang ketemu.
        Return element atau None.
        """
        # Coba semua selector sekaligus dalam satu query
        combined = ", ".join(selectors)
        try:
            el = page.wait_for_selector(combined, timeout=timeout_ms)
            if el:
                tag  = el.evaluate("el => el.tagName")
                name = el.get_attribute("name") or ""
                typ  = el.get_attribute("type") or ""
                self._log(f"   ✅ Input ditemukan: <{tag.lower()} type='{typ}' name='{name}'>")
                return el
        except PWTimeout:
            pass

        # Fallback: coba satu-satu
        for sel in selectors:
            el = page.query_selector(sel)
            if el:
                tag  = el.evaluate("el => el.tagName")
                name = el.get_attribute("name") or ""
                typ  = el.get_attribute("type") or ""
                self._log(f"   ✅ Input fallback [{sel}]: <{tag.lower()} type='{typ}' name='{name}'>")
                return el

        return None

    # ── Log semua input di halaman (debug) ────────────────────────────────
    def _log_all_inputs(self, page):
        """Log semua <input> yang ada di halaman untuk debug."""
        try:
            inputs = page.query_selector_all("input, textarea")
            self._log(f"🔍 Total input/textarea di halaman: {len(inputs)}", "WARNING")
            for i, el in enumerate(inputs[:10]):
                typ  = el.get_attribute("type") or "-"
                name = el.get_attribute("name") or "-"
                pid  = el.get_attribute("id") or "-"
                ph   = el.get_attribute("placeholder") or "-"
                jsn  = el.get_attribute("jsname") or "-"
                self._log(f"   [{i}] type={typ} name={name} id={pid} placeholder={ph} jsname={jsn}", "WARNING")
        except Exception as e:
            self._log(f"⚠️  Log inputs gagal: {e}", "WARNING")

    # ──────────────────────────────────────────────────────────────────────
    def run(self):
        os.makedirs(self.output_dir, exist_ok=True)
        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch(
                    headless=self.config.get("headless", False),
                    args=[
                        "--no-sandbox",
                        "--disable-blink-features=AutomationControlled",
                        "--disable-dev-shm-usage",
                    ]
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

    # ──────────────────────────────────────────────────────────────────────
    def _run_session(self, page) -> Optional[str]:

        # ── 1. Buka halaman login ──────────────────────────────────────────
        self._log("🌐 Membuka halaman login Gemini Enterprise...")
        self._progress(5, "Membuka halaman login...")
        page.goto(GEMINI_LOGIN_URL, wait_until="networkidle", timeout=40_000)
        page.wait_for_timeout(3000)
        self._log(f"   URL saat ini: {page.url}")
        if self._cancelled: return None

        # ── 2. Input email ─────────────────────────────────────────────────
        self._log(f"📧 Mencari field email...")
        self._progress(10, "Input email...")

        # Debug: log semua input yang ada
        self._log_all_inputs(page)

        email_input = self._find_input(page, EMAIL_SELECTORS, timeout_ms=15_000)

        if not email_input:
            self._log("❌ Input email tidak ditemukan! Menyimpan debug info...", "ERROR")
            self._debug_dump(page, "step2_email_not_found")
            self._log("   Cek folder DEBUG/ untuk screenshot dan HTML.", "WARNING")
            return None

        self._log(f"📧 Input email: {self.mask_email}")
        try:
            email_input.scroll_into_view_if_needed()
            email_input.click()
            page.wait_for_timeout(300)
            email_input.fill("")
            email_input.type(self.mask_email, delay=80)
            page.wait_for_timeout(500)

            # Debug: cek value yang terisi
            val = email_input.input_value()
            self._log(f"   ✅ Nilai input: '{val}'")

            # Cari tombol submit
            submit_el = None
            for sel in SUBMIT_SELECTORS:
                submit_el = page.query_selector(sel)
                if submit_el:
                    self._log(f"   ✅ Tombol submit: [{sel}]")
                    break

            if submit_el:
                submit_el.click()
            else:
                self._log("   ⚠️  Tombol submit tidak ditemukan, pakai Enter", "WARNING")
                page.keyboard.press("Enter")

            self._log("✅ Email tersubmit, menunggu halaman OTP...")
            page.wait_for_timeout(3000)

        except Exception as e:
            self._log(f"❌ Error saat input email: {e}", "ERROR")
            self._debug_dump(page, "step2_email_error")
            return None

        if self._cancelled: return None

        # ── 3. Baca OTP dari Gmail ─────────────────────────────────────────
        self._progress(20, "Menunggu OTP dari Gmail...")
        self._log(f"   URL setelah submit email: {page.url}")

        # Debug: dump halaman OTP
        self._debug_dump(page, "step3_otp_page")
        self._log_all_inputs(page)

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
                        page.goto(GEMINI_LOGIN_URL, wait_until="networkidle")
                        page.wait_for_timeout(2000)
                        ei = self._find_input(page, EMAIL_SELECTORS, timeout_ms=10_000)
                        if ei:
                            ei.fill(self.mask_email)
                            page.keyboard.press("Enter")
                            page.wait_for_timeout(2000)
                            reg_ts = int(time.time())

        if not otp_code:
            self._log("❌ Gagal dapat OTP setelah semua percobaan!", "ERROR")
            self._debug_dump(page, "step3_otp_failed")
            return None
        if self._cancelled: return None

        # ── 4. Input OTP ke form ───────────────────────────────────────────
        self._progress(35, "Memasukkan kode OTP...")
        self._log("✏️  Input OTP ke form...")

        # Debug: log semua input
        self._log_all_inputs(page)

        try:
            otp_inputs = page.query_selector_all(
                "input[type='text'][maxlength='1'], "
                "input[autocomplete='one-time-code'], "
                "input[name*='otp'], input[name*='code'], "
                "input[placeholder*='code'], input[placeholder*='OTP']"
            )
            if len(otp_inputs) > 1:
                self._log(f"   Multi-digit input: {len(otp_inputs)} kotak")
                for i, digit in enumerate(otp_code[:len(otp_inputs)]):
                    otp_inputs[i].fill(digit)
                    page.wait_for_timeout(120)
            elif len(otp_inputs) == 1:
                self._log("   Single OTP input")
                otp_inputs[0].fill(otp_code)
            else:
                self._log("   Fallback: type keyboard", "WARNING")
                page.keyboard.type(otp_code, delay=100)

            page.wait_for_timeout(800)
            verify_btn = page.query_selector(
                "button[type='submit'], button:has-text('Verify'), "
                "button:has-text('Continue'), button:has-text('Sign in')"
            )
            if verify_btn: verify_btn.click()
            else:          page.keyboard.press("Enter")

            self._log("✅ OTP tersubmit, menunggu redirect dashboard...")
            page.wait_for_url("**/business.gemini.google/**", timeout=25_000)
            self._log("✅ Login berhasil!", "SUCCESS")

        except PWTimeout:
            self._log("❌ Login gagal — redirect timeout!", "ERROR")
            self._debug_dump(page, "step4_otp_submit_failed")
            return None
        if self._cancelled: return None

        # ── 5. Klik "+" → "Create videos with Veo" ────────────────────────
        self._progress(50, "Membuka menu Create videos with Veo...")
        self._log("🎬 Mencari tombol tools...")
        page.wait_for_timeout(3000)

        # Debug halaman dashboard
        self._debug_dump(page, "step5_dashboard")

        try:
            # Coba berbagai kemungkinan selector tools/+ button
            tools_selectors = [
                "button[aria-label*='tool' i]",
                "button[aria-label*='attach' i]",
                "button[aria-label*='more' i]",
                "button[data-tooltip*='tool' i]",
                "[role='button'][aria-label*='tool' i]",
                "button[jsname]:not([type='submit'])",
                # Selector berdasarkan posisi di form area
                "form button:first-of-type",
                "form [role='button']:first-of-type",
            ]
            tools_btn = None
            for sel in tools_selectors:
                el = page.query_selector(sel)
                if el:
                    self._log(f"   ✅ Tools button ditemukan: [{sel}]")
                    tools_btn = el
                    break

            if not tools_btn:
                self._log("❌ Tombol tools tidak ditemukan! Cek DEBUG/", "ERROR")
                self._debug_dump(page, "step5_tools_not_found")
                return None

            tools_btn.click()
            page.wait_for_timeout(1200)

            # Klik item "Create videos with Veo"
            veo_selectors = [
                "[role='menuitem']:has-text('Create videos with Veo')",
                "[role='option']:has-text('Create videos with Veo')",
                "li:has-text('Create videos with Veo')",
                "div[role='menuitem']:has-text('Create videos')",
                "*:has-text('Create videos with Veo')",
            ]
            veo_item = None
            for sel in veo_selectors:
                try:
                    veo_item = page.wait_for_selector(sel, timeout=5_000)
                    if veo_item:
                        self._log(f"   ✅ Veo menu item: [{sel}]")
                        break
                except PWTimeout:
                    continue

            if not veo_item:
                self._log("❌ Menu 'Create videos with Veo' tidak ditemukan!", "ERROR")
                self._debug_dump(page, "step5_veo_menu_not_found")
                return None

            veo_item.click()
            self._log("✅ 'Create videos with Veo' dipilih!", "SUCCESS")
            page.wait_for_timeout(2000)

        except Exception as e:
            self._log(f"❌ Error menu tools: {e}", "ERROR")
            self._debug_dump(page, "step5_error")
            return None
        if self._cancelled: return None

        # ── 6. Input prompt ────────────────────────────────────────────────
        self._progress(60, "Memasukkan prompt video...")
        self._log(f"✏️  Prompt: {self.prompt[:80]}...")

        # Debug setelah klik Veo
        self._debug_dump(page, "step6_after_veo_click")

        try:
            prompt_selectors = [
                "textarea",
                "[contenteditable='true']",
                "input[placeholder*='prompt' i]",
                "input[placeholder*='describe' i]",
                "input[placeholder*='video' i]",
                "[role='textbox']",
            ]
            prompt_el = self._find_input(page, prompt_selectors, timeout_ms=12_000)

            if not prompt_el:
                self._log("❌ Input prompt tidak ditemukan!", "ERROR")
                self._debug_dump(page, "step6_prompt_not_found")
                return None

            prompt_el.click()
            page.wait_for_timeout(300)
            prompt_el.fill(self.prompt)
            page.wait_for_timeout(800)

            send_btn = page.query_selector(
                "button[aria-label*='send' i], button[aria-label*='generate' i], "
                "button[aria-label*='Submit' i], button[type='submit']"
            )
            if send_btn:
                send_btn.click()
            else:
                page.keyboard.press("Enter")

            self._log("✅ Prompt tersubmit! Menunggu Veo generate...", "SUCCESS")

        except Exception as e:
            self._log(f"❌ Error input prompt: {e}", "ERROR")
            self._debug_dump(page, "step6_error")
            return None
        if self._cancelled: return None

        # ── 7. Polling sampai video siap ───────────────────────────────────
        self._progress(70, "Menunggu Veo generate video...")
        self._log(f"⏳ Polling max {VIDEO_GEN_TIMEOUT}s...")
        start       = time.time()
        video_ready = False

        while time.time() - start < VIDEO_GEN_TIMEOUT:
            if self._cancelled: return None
            elapsed = int(time.time() - start)
            pct     = min(70 + int((elapsed / VIDEO_GEN_TIMEOUT) * 18), 88)
            self._progress(pct, f"Generate... {elapsed}s/{VIDEO_GEN_TIMEOUT}s")

            dl = page.query_selector(
                "button:has-text('Download'), a[download], "
                "button[aria-label*='download' i], [role='button']:has-text('Download')"
            )
            if dl:
                self._log("✅ Video siap didownload!", "SUCCESS")
                video_ready = True
                break

            vid = page.query_selector("video[src]")
            if vid:
                src = vid.get_attribute("src") or ""
                if src and "blob" not in src:
                    self._log("✅ Elemen video ditemukan!", "SUCCESS")
                    video_ready = True
                    break

            time.sleep(POLLING_INTERVAL)

        if not video_ready:
            self._log(f"❌ Timeout {VIDEO_GEN_TIMEOUT}s — video tidak selesai.", "ERROR")
            self._debug_dump(page, "step7_timeout")
            return None
        if self._cancelled: return None

        # ── 8. Download video ──────────────────────────────────────────────
        self._progress(90, "Mendownload video...")
        self._log("📥 Mendownload video hasil...")
        try:
            out_path = os.path.join(
                self.output_dir, f"gemini_veo_{int(time.time())}.mp4"
            )
            with page.expect_download(timeout=120_000) as dl_info:
                dl_btn = page.query_selector(
                    "button:has-text('Download'), a[download], "
                    "button[aria-label*='download' i]"
                )
                if dl_btn:
                    dl_btn.click()
                else:
                    raise Exception("Tombol download tidak ditemukan")

            dl_info.value.save_as(out_path)
            self._log(f"✅ Video tersimpan: {out_path}", "SUCCESS")
            self._progress(100, "Selesai!")
            return out_path

        except Exception as e:
            self._log(f"❌ Download gagal: {e}", "ERROR")
            self._debug_dump(page, "step8_download_failed")
            return None
