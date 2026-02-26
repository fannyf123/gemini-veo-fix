"""
gemini_enterprise.py

Otomasi login + generate video di business.gemini.google
via Playwright + OTP otomatis dari GmailOTPReader.

Anti-bot level 2:
    - Pakai playwright-stealth library (patch 30+ fingerprint)
    - Deteksi path Chrome/Chromium secara manual
    - Hapus semua flag automation Playwright
    - Human-like mouse + typing + random delay
"""

import os
import re
import time
import random
import threading
from typing import Optional, Callable

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

try:
    from playwright_stealth import stealth_sync
    HAS_STEALTH = True
except ImportError:
    HAS_STEALTH = False

from App.gmail_otp import GmailOTPReader

GEMINI_LOGIN_URL  = "https://auth.business.gemini.google/login?continueUrl=https://business.gemini.google/"
GEMINI_HOME_URL   = "https://business.gemini.google/"

OTP_TIMEOUT       = 120
VIDEO_GEN_TIMEOUT = 600
POLLING_INTERVAL  = 8
MAX_OTP_RETRY     = 3

# ── Path Chrome yang umum di Windows ─────────────────────────────────────────
CHROME_PATHS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    os.path.expanduser(r"~\AppData\Local\Google\Chrome\Application\chrome.exe"),
    r"C:\Program Files\Google\Chrome Beta\Application\chrome.exe",
    r"C:\Program Files\Chromium\Application\chrome.exe",
]

# ── Fallback stealth JS (dipakai jika playwright-stealth tidak terinstall) ────
MINIMAL_STEALTH_JS = """
    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
    delete window.cdc_adoQpoasnfa76pfcZLmcfl_Array;
    delete window.cdc_adoQpoasnfa76pfcZLmcfl_Promise;
    delete window.cdc_adoQpoasnfa76pfcZLmcfl_Symbol;
    Object.defineProperty(navigator, 'plugins', { get: () => [1,2,3,4,5] });
    Object.defineProperty(navigator, 'languages', { get: () => ['en-US','en'] });
    window.chrome = { runtime:{}, loadTimes:function(){}, csi:function(){}, app:{} };
    const _pq = window.navigator.permissions.query;
    window.navigator.permissions.query = (p) =>
        p.name==='notifications'
        ? Promise.resolve({state:Notification.permission})
        : _pq(p);
"""

EMAIL_SELECTORS = [
    "input[name='loginHint']",           # ← dari log debug: name=loginHint
    "input[id='email-input']",           # ← dari log debug: id=email-input
    "input[jsname='YPqjbf']",            # ← dari log debug: jsname=YPqjbf
    "input[type='email']",
    "input[name='email']",
    "input[id*='email' i]",
    "input[placeholder*='mail' i]",
    "input[autocomplete='email']",
    "input[type='text']",
    "input",
]

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

    def _debug_dump(self, page, label: str):
        try:
            os.makedirs(self.debug_dir, exist_ok=True)
            ts = int(time.time())
            page.screenshot(path=os.path.join(self.debug_dir, f"{label}_{ts}.png"), full_page=True)
            with open(os.path.join(self.debug_dir, f"{label}_{ts}.html"), "w", encoding="utf-8") as f:
                f.write(page.content())
            self._log(f"🔍 DEBUG disimpan: DEBUG/{label}_{ts}.*", "WARNING")
        except Exception as e:
            self._log(f"⚠️  Debug dump gagal: {e}", "WARNING")

    def _log_all_inputs(self, page):
        try:
            inputs = page.query_selector_all("input, textarea")
            self._log(f"🔍 {len(inputs)} input ditemukan di halaman:", "WARNING")
            for i, el in enumerate(inputs[:10]):
                self._log(
                    f"   [{i}] type={el.get_attribute('type') or '-'} "
                    f"name={el.get_attribute('name') or '-'} "
                    f"id={el.get_attribute('id') or '-'} "
                    f"placeholder={el.get_attribute('placeholder') or '-'} "
                    f"jsname={el.get_attribute('jsname') or '-'}",
                    "WARNING"
                )
        except:
            pass

    def _find_input(self, page, selectors, timeout_ms=15_000):
        combined = ", ".join(selectors)
        try:
            el = page.wait_for_selector(combined, timeout=timeout_ms)
            if el:
                self._log(f"   ✅ Input: type={el.get_attribute('type')} name={el.get_attribute('name')} id={el.get_attribute('id')}")
                return el
        except PWTimeout:
            pass
        for sel in selectors:
            el = page.query_selector(sel)
            if el:
                self._log(f"   ✅ Input fallback [{sel}]")
                return el
        return None

    def _human_type(self, page, element, text: str):
        """Ketik seperti manusia: random delay antar karakter."""
        element.click()
        page.wait_for_timeout(random.randint(300, 600))
        element.fill("")  # clear
        page.wait_for_timeout(random.randint(100, 250))
        for char in text:
            element.type(char, delay=random.randint(70, 160))
        page.wait_for_timeout(random.randint(400, 700))

    def _human_click(self, page, element):
        """Klik dengan sedikit jitter posisi."""
        try:
            box = element.bounding_box()
            if box:
                x = box["x"] + box["width"] / 2 + random.randint(-4, 4)
                y = box["y"] + box["height"] / 2 + random.randint(-4, 4)
                page.mouse.move(x + random.randint(-20, 20), y + random.randint(-50, -20))
                page.wait_for_timeout(random.randint(100, 250))
                page.mouse.move(x, y)
                page.wait_for_timeout(random.randint(60, 150))
                page.mouse.click(x, y)
            else:
                element.click()
        except:
            element.click()

    def _find_chrome_executable(self) -> Optional[str]:
        """Cari path Chrome yang ada di sistem."""
        for path in CHROME_PATHS:
            if os.path.exists(path):
                self._log(f"   💻 Chrome ditemukan: {path}")
                return path
        return None

    # ────────────────────────────────────────────────────────────────
    def run(self):
        os.makedirs(self.output_dir, exist_ok=True)

        if HAS_STEALTH:
            self._log("✅ playwright-stealth terdeteksi, anti-bot aktif", "SUCCESS")
        else:
            self._log("⚠️  playwright-stealth tidak terinstall! Jalankan:", "WARNING")
            self._log("   pip install playwright-stealth", "WARNING")
            self._log("   Anti-bot mode minimal (mungkin masih terdeteksi)", "WARNING")

        try:
            with sync_playwright() as pw:
                headless    = self.config.get("headless", False)
                chrome_path = self._find_chrome_executable()

                # ── Args wajib untuk bypass bot detection ──────────────────────
                launch_args = [
                    "--no-sandbox",
                    "--disable-blink-features=AutomationControlled",
                    "--disable-dev-shm-usage",
                    "--no-first-run",
                    "--no-default-browser-check",
                    "--disable-background-networking",
                    "--disable-ipc-flooding-protection",
                    "--password-store=basic",
                    "--use-mock-keychain",
                    "--disable-features=IsolateOrigins,site-per-process",
                    "--disable-site-isolation-trials",
                ]

                launch_kwargs = dict(
                    headless=headless,
                    args=launch_args,
                    ignore_default_args=["--enable-automation"],
                )

                # Prioritas 1: Chrome asli via executable_path
                if chrome_path:
                    try:
                        browser = pw.chromium.launch(
                            executable_path=chrome_path,
                            **launch_kwargs
                        )
                        self._log(f"💻 Pakai Chrome: {chrome_path}", "SUCCESS")
                    except Exception as e:
                        self._log(f"⚠️  Chrome path gagal ({e}), coba channel...", "WARNING")
                        chrome_path = None

                # Prioritas 2: channel='chrome'
                if not chrome_path:
                    try:
                        browser = pw.chromium.launch(channel="chrome", **launch_kwargs)
                        self._log("💻 Pakai Chrome via channel", "SUCCESS")
                    except Exception:
                        # Fallback: Chromium biasa
                        browser = pw.chromium.launch(**launch_kwargs)
                        self._log("💻 Pakai Chromium (fallback) — risiko terdeteksi bot!", "WARNING")

                # ── Context dengan fingerprint realistis ──────────────────────
                ctx = browser.new_context(
                    viewport={"width": random.randint(1280, 1440), "height": random.randint(860, 960)},
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/122.0.6261.112 Safari/537.36"
                    ),
                    locale="en-US",
                    timezone_id="Asia/Jakarta",
                    color_scheme="light",
                    java_script_enabled=True,
                    accept_downloads=True,
                    extra_http_headers={
                        "Accept-Language": "en-US,en;q=0.9",
                        "sec-ch-ua": '"Google Chrome";v="122", "Not(A:Brand";v="24", "Chromium";v="122"',
                        "sec-ch-ua-mobile": "?0",
                        "sec-ch-ua-platform": '"Windows"',
                    }
                )

                # ── Inject stealth sebelum halaman manapun load ────────────────
                ctx.add_init_script(MINIMAL_STEALTH_JS)

                page = ctx.new_page()
                page.add_init_script(
                    "Object.defineProperty(navigator, 'webdriver', { get: () => undefined });"
                )

                # ── Terapkan playwright-stealth jika tersedia ──────────────────
                if HAS_STEALTH:
                    stealth_sync(page)
                    self._log("✅ Stealth patches applied (30+ fingerprint patches)", "SUCCESS")

                result = self._run_session(page)
                browser.close()

            if result:
                self._done(True, f"✅ Video tersimpan: {result}", result)
            else:
                self._done(False, "Generate video gagal atau dibatalkan.")
        except Exception as e:
            self._log(f"❌ Fatal error: {e}", "ERROR")
            self._done(False, str(e))

    # ────────────────────────────────────────────────────────────────
    def _run_session(self, page) -> Optional[str]:

        # ── 1. Buka halaman login ─────────────────────────────────────────
        self._log("🌐 Membuka halaman login Gemini Enterprise...")
        self._progress(5, "Membuka halaman login...")

        # Warm up: buka google.com dulu agar cookies terbentuk natural
        page.goto("https://www.google.com", wait_until="domcontentloaded", timeout=20_000)
        page.wait_for_timeout(random.randint(1800, 3000))

        # Scroll sedikit (simulasi manusia)
        page.mouse.wheel(0, random.randint(100, 300))
        page.wait_for_timeout(random.randint(500, 1000))

        # Buka Gemini login
        page.goto(GEMINI_LOGIN_URL, wait_until="networkidle", timeout=40_000)
        page.wait_for_timeout(random.randint(2500, 4000))

        current_url = page.url
        self._log(f"   URL: {current_url}")

        if "signin-error" in current_url:
            self._log("❌ signin-error saat buka halaman (sebelum input email)!", "ERROR")
            self._log("   → Google memblok IP/browser bahkan sebelum form tampil.", "WARNING")
            self._log("   → Solusi: Pastikan 'playwright-stealth' terinstall:", "WARNING")
            self._log("     pip install playwright-stealth", "WARNING")
            self._debug_dump(page, "step1_signin_error")
            return None

        if self._cancelled: return None

        # ── 2. Input email ─────────────────────────────────────────
        self._log("📧 Mencari field email...")
        self._progress(10, "Input email...")
        self._log_all_inputs(page)

        email_input = self._find_input(page, EMAIL_SELECTORS, timeout_ms=15_000)
        if not email_input:
            self._log("❌ Input email tidak ditemukan!", "ERROR")
            self._debug_dump(page, "step2_email_not_found")
            return None

        self._log(f"📧 Mengetik email: {self.mask_email}")
        try:
            email_input.scroll_into_view_if_needed()
            page.wait_for_timeout(random.randint(400, 800))

            self._human_type(page, email_input, self.mask_email)

            val = email_input.input_value()
            self._log(f"   ✅ Nilai input: '{val}'")

            if val != self.mask_email:
                self._log("   ⚠️  Fill ulang...", "WARNING")
                email_input.fill(self.mask_email)
                page.wait_for_timeout(500)

            # Jeda natural sebelum klik submit
            page.wait_for_timeout(random.randint(900, 1800))

            submit_el = None
            for sel in SUBMIT_SELECTORS:
                submit_el = page.query_selector(sel)
                if submit_el:
                    self._log(f"   ✅ Submit: [{sel}]")
                    break

            if submit_el:
                self._human_click(page, submit_el)
            else:
                self._log("   ⚠️  Tombol submit tidak ditemukan, pakai Enter", "WARNING")
                page.keyboard.press("Enter")

            self._log("✅ Email tersubmit, menunggu respons...")
            page.wait_for_timeout(random.randint(3000, 5000))

            # Cek apakah kena bot detection
            if "signin-error" in page.url:
                self._log("❌ Google mendeteksi bot setelah submit email!", "ERROR")
                self._log("", "WARNING")
                self._log("  🔧 SOLUSI (coba berurutan):", "WARNING")
                self._log("  1. Jalankan: pip install playwright-stealth", "WARNING")
                self._log("  2. Install Google Chrome dari https://google.com/chrome", "WARNING")
                self._log("  3. Cek di config.json: headless = false (wajib!)", "WARNING")
                self._log("  4. Tunggu beberapa menit lalu coba lagi (rate-limit IP)", "WARNING")
                self._debug_dump(page, "step2_bot_detected")
                return None

        except Exception as e:
            self._log(f"❌ Error saat input email: {e}", "ERROR")
            self._debug_dump(page, "step2_email_error")
            return None

        if self._cancelled: return None

        # ── 3. Baca OTP dari Gmail ────────────────────────────────────────
        self._progress(20, "Menunggu OTP dari Gmail...")
        self._log(f"   URL setelah submit: {page.url}")
        self._debug_dump(page, "step3_otp_page")
        self._log_all_inputs(page)

        otp_code = None
        reg_ts   = int(time.time())

        for attempt in range(1, MAX_OTP_RETRY + 1):
            self._log(f"📬 Polling OTP ({attempt}/{MAX_OTP_RETRY})...")
            try:
                otp_code = self._otp_reader.wait_for_otp(
                    sender="noreply-googlecloud@google.com",
                    timeout=OTP_TIMEOUT, interval=5,
                    log_callback=self.log_cb,
                    mask_email=self.mask_email,
                    after_timestamp=reg_ts,
                )
                self._log(f"✅ OTP: {otp_code}", "SUCCESS")
                break
            except TimeoutError:
                self._log(f"⚠️  OTP timeout ({attempt})", "WARNING")
                if attempt < MAX_OTP_RETRY:
                    resend = page.query_selector(
                        "button:has-text('Resend'), a:has-text('Resend'), button:has-text('Send again')"
                    )
                    if resend:
                        self._human_click(page, resend)
                        page.wait_for_timeout(2000)
                        reg_ts = int(time.time())
                    else:
                        page.goto(GEMINI_LOGIN_URL, wait_until="networkidle")
                        page.wait_for_timeout(2000)
                        ei = self._find_input(page, EMAIL_SELECTORS, 10_000)
                        if ei:
                            self._human_type(page, ei, self.mask_email)
                            page.keyboard.press("Enter")
                            page.wait_for_timeout(2000)
                            reg_ts = int(time.time())

        if not otp_code:
            self._log("❌ Gagal dapat OTP!", "ERROR")
            self._debug_dump(page, "step3_otp_failed")
            return None
        if self._cancelled: return None

        # ── 4. Input OTP ───────────────────────────────────────────────
        self._progress(35, "Memasukkan kode OTP...")
        self._log("✏️  Input OTP...")
        self._log_all_inputs(page)
        try:
            otp_inputs = page.query_selector_all(
                "input[type='text'][maxlength='1'], input[autocomplete='one-time-code'], "
                "input[name*='otp'], input[name*='code'], input[placeholder*='code']"
            )
            if len(otp_inputs) > 1:
                for i, digit in enumerate(otp_code[:len(otp_inputs)]):
                    otp_inputs[i].fill(digit)
                    page.wait_for_timeout(random.randint(100, 220))
            elif len(otp_inputs) == 1:
                self._human_type(page, otp_inputs[0], otp_code)
            else:
                page.keyboard.type(otp_code, delay=110)

            page.wait_for_timeout(random.randint(700, 1200))
            verify_btn = page.query_selector(
                "button[type='submit'], button:has-text('Verify'), "
                "button:has-text('Continue'), button:has-text('Sign in')"
            )
            if verify_btn:
                self._human_click(page, verify_btn)
            else:
                page.keyboard.press("Enter")

            self._log("✅ OTP tersubmit, menunggu redirect...")
            page.wait_for_url("**/business.gemini.google/**", timeout=25_000)
            self._log("✅ Login berhasil!", "SUCCESS")

        except PWTimeout:
            self._log("❌ Login gagal — redirect timeout!", "ERROR")
            self._debug_dump(page, "step4_otp_failed")
            return None
        if self._cancelled: return None

        # ── 5. Klik "+" → "Create videos with Veo" ───────────────────────
        self._progress(50, "Membuka menu Veo...")
        self._log("🎬 Mencari tombol tools...")
        page.wait_for_timeout(random.randint(2500, 4000))
        self._debug_dump(page, "step5_dashboard")

        try:
            tools_selectors = [
                "button[aria-label*='tool' i]",
                "button[aria-label*='attach' i]",
                "button[aria-label*='more' i]",
                "[role='button'][aria-label*='tool' i]",
                "button[jsname]:not([type='submit'])",
                "form button:first-of-type",
            ]
            tools_btn = None
            for sel in tools_selectors:
                el = page.query_selector(sel)
                if el:
                    self._log(f"   ✅ Tools btn: [{sel}]")
                    tools_btn = el
                    break

            if not tools_btn:
                self._log("❌ Tombol tools tidak ditemukan!", "ERROR")
                self._debug_dump(page, "step5_no_tools")
                return None

            self._human_click(page, tools_btn)
            page.wait_for_timeout(random.randint(900, 1600))

            veo_item = None
            for sel in [
                "[role='menuitem']:has-text('Create videos with Veo')",
                "[role='option']:has-text('Create videos with Veo')",
                "li:has-text('Create videos with Veo')",
                "div:has-text('Create videos with Veo')",
            ]:
                try:
                    veo_item = page.wait_for_selector(sel, timeout=5_000)
                    if veo_item:
                        self._log(f"   ✅ Veo menu: [{sel}]")
                        break
                except PWTimeout:
                    continue

            if not veo_item:
                self._log("❌ Menu Veo tidak ditemukan!", "ERROR")
                self._debug_dump(page, "step5_no_veo")
                return None

            self._human_click(page, veo_item)
            self._log("✅ 'Create videos with Veo' dipilih!", "SUCCESS")
            page.wait_for_timeout(random.randint(1500, 2500))

        except Exception as e:
            self._log(f"❌ Error menu: {e}", "ERROR")
            self._debug_dump(page, "step5_error")
            return None
        if self._cancelled: return None

        # ── 6. Input prompt ──────────────────────────────────────────────
        self._progress(60, "Input prompt...")
        self._debug_dump(page, "step6_veo_open")
        try:
            prompt_el = self._find_input(page, [
                "textarea",
                "[contenteditable='true']",
                "input[placeholder*='prompt' i]",
                "[role='textbox']",
            ], timeout_ms=12_000)

            if not prompt_el:
                self._log("❌ Input prompt tidak ditemukan!", "ERROR")
                self._debug_dump(page, "step6_no_prompt")
                return None

            self._human_type(page, prompt_el, self.prompt)
            page.wait_for_timeout(random.randint(700, 1200))

            send_btn = page.query_selector(
                "button[aria-label*='send' i], button[aria-label*='generate' i], "
                "button[aria-label*='Submit' i], button[type='submit']"
            )
            if send_btn:
                self._human_click(page, send_btn)
            else:
                page.keyboard.press("Enter")

            self._log("✅ Prompt tersubmit!", "SUCCESS")
        except Exception as e:
            self._log(f"❌ Error prompt: {e}", "ERROR")
            self._debug_dump(page, "step6_error")
            return None
        if self._cancelled: return None

        # ── 7. Polling video ──────────────────────────────────────────────
        self._progress(70, "Menunggu Veo generate...")
        self._log(f"⏳ Polling max {VIDEO_GEN_TIMEOUT}s...")
        start       = time.time()
        video_ready = False

        while time.time() - start < VIDEO_GEN_TIMEOUT:
            if self._cancelled: return None
            elapsed = int(time.time() - start)
            self._progress(
                min(70 + int((elapsed / VIDEO_GEN_TIMEOUT) * 18), 88),
                f"Generate... {elapsed}s/{VIDEO_GEN_TIMEOUT}s"
            )
            dl = page.query_selector(
                "button:has-text('Download'), a[download], button[aria-label*='download' i]"
            )
            if dl:
                video_ready = True
                break
            vid = page.query_selector("video[src]")
            if vid and "blob" not in (vid.get_attribute("src") or ""):
                video_ready = True
                break
            time.sleep(POLLING_INTERVAL)

        if not video_ready:
            self._log(f"❌ Timeout {VIDEO_GEN_TIMEOUT}s.", "ERROR")
            self._debug_dump(page, "step7_timeout")
            return None
        if self._cancelled: return None

        # ── 8. Download ──────────────────────────────────────────────────
        self._progress(90, "Mendownload video...")
        try:
            out_path = os.path.join(self.output_dir, f"gemini_veo_{int(time.time())}.mp4")
            with page.expect_download(timeout=120_000) as dl_info:
                dl_btn = page.query_selector(
                    "button:has-text('Download'), a[download], button[aria-label*='download' i]"
                )
                if dl_btn:
                    self._human_click(page, dl_btn)
                else:
                    raise Exception("Tombol download tidak ditemukan")

            dl_info.value.save_as(out_path)
            self._log(f"✅ Tersimpan: {out_path}", "SUCCESS")
            self._progress(100, "Selesai!")
            return out_path
        except Exception as e:
            self._log(f"❌ Download gagal: {e}", "ERROR")
            self._debug_dump(page, "step8_failed")
            return None
