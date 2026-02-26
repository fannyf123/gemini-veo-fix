"""
gemini_enterprise.py

Otomasi generate video di business.gemini.google
via Playwright.

Mode operasi:
    1. SESSION MODE (prioritas)  : Load cookies dari session/gemini_session.json
    2. LOGIN MODE (fallback)     : Login otomatis via email + OTP
                                   + auto-retry jika muncul 'Let's try something else'
"""

import os
import json
import time
import random
import threading
from typing import Optional, Callable

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

from App.gmail_otp import GmailOTPReader
from App._stealth_compat import apply_stealth, stealth_info, STEALTH_VERSION

GEMINI_HOME_URL   = "https://business.gemini.google/"

OTP_TIMEOUT       = 120
VIDEO_GEN_TIMEOUT = 600
POLLING_INTERVAL  = 8
MAX_OTP_RETRY     = 3
MAX_LOGIN_RETRY   = 4   # Maksimal retry saat muncul 'Let's try something else'

CHROME_PATHS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    os.path.expanduser(r"~\AppData\Local\Google\Chrome\Application\chrome.exe"),
    r"C:\Program Files\Google\Chrome Beta\Application\chrome.exe",
]

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
    "input[name='loginHint']",
    "input[id='email-input']",
    "input[jsname='YPqjbf']",
    "input[type='email']",
    "input[name='email']",
    "input[id*='email' i]",
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
]

# Selector tombol 'Sign up or sign in' di halaman error
SIGNIN_RETRY_SELECTORS = [
    "a:has-text('Sign up or sign in')",
    "button:has-text('Sign up or sign in')",
    "[role='button']:has-text('Sign up or sign in')",
    "a:has-text('sign in')",
    "a:has-text('Sign in')",
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
        self.base_dir     = base_dir
        self.prompt       = prompt
        self.mask_email   = mask_email
        self.output_dir   = output_dir or os.path.join(base_dir, "OUTPUT_GEMINI")
        self.config       = config
        self.log_cb       = log_callback
        self.progress_cb  = progress_callback
        self.finished_cb  = finished_callback
        self._cancelled   = False
        self._otp_reader  = GmailOTPReader(base_dir)
        self.debug_dir    = os.path.join(base_dir, "DEBUG")
        self.session_file = os.path.join(base_dir, "session", "gemini_session.json")

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
            self._log(f"🔍 DEBUG: DEBUG/{label}_{ts}.*", "WARNING")
        except Exception as e:
            self._log(f"⚠️  Debug dump gagal: {e}", "WARNING")

    def _log_all_inputs(self, page):
        try:
            inputs = page.query_selector_all("input, textarea")
            self._log(f"🔍 {len(inputs)} input ditemukan:", "WARNING")
            for i, el in enumerate(inputs[:8]):
                self._log(
                    f"   [{i}] type={el.get_attribute('type') or '-'} "
                    f"name={el.get_attribute('name') or '-'} "
                    f"id={el.get_attribute('id') or '-'}",
                    "WARNING"
                )
        except:
            pass

    def _find_input(self, page, selectors, timeout_ms=15_000):
        combined = ", ".join(selectors)
        try:
            el = page.wait_for_selector(combined, timeout=timeout_ms)
            if el:
                self._log(f"   ✅ Input: name={el.get_attribute('name')} id={el.get_attribute('id')}")
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
        element.click()
        page.wait_for_timeout(random.randint(300, 600))
        element.fill("")
        page.wait_for_timeout(random.randint(100, 250))
        for char in text:
            element.type(char, delay=random.randint(70, 160))
        page.wait_for_timeout(random.randint(400, 700))

    def _human_click(self, page, element):
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
        for path in CHROME_PATHS:
            if os.path.exists(path):
                self._log(f"   💻 Chrome ditemukan: {path}")
                return path
        return None

    def _has_valid_session(self) -> bool:
        if not os.path.exists(self.session_file):
            return False
        try:
            with open(self.session_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            cookies = data.get("cookies", [])
            google_cookies = [c for c in cookies if ".google.com" in c.get("domain", "")]
            return len(google_cookies) > 0
        except Exception:
            return False

    def _is_error_page(self, page) -> bool:
        """Cek apakah halaman 'Let's try something else' sedang tampil."""
        try:
            content = page.content().lower()
            return "try something else" in content or "let\u2019s try" in content or "let's try" in content
        except:
            return False

    def _click_signin_retry(self, page) -> bool:
        """Klik 'Sign up or sign in' di halaman error. Return True jika berhasil."""
        for sel in SIGNIN_RETRY_SELECTORS:
            try:
                btn = page.wait_for_selector(sel, timeout=4_000)
                if btn:
                    self._log(f"   🔄 Klik retry: [{sel}]")
                    self._human_click(page, btn)
                    page.wait_for_timeout(random.randint(2500, 4000))
                    return True
            except PWTimeout:
                continue
        return False

    # ─────────────────────────────────────────────────────────
    def run(self):
        os.makedirs(self.output_dir, exist_ok=True)

        if STEALTH_VERSION:
            self._log(f"✅ Anti-bot aktif: {stealth_info()}", "SUCCESS")
        else:
            self._log("⚠️  playwright-stealth tidak tersedia", "WARNING")

        use_session = self._has_valid_session()
        if use_session:
            self._log("🔑 Session ditemukan → Mode: SESSION (skip login)", "SUCCESS")
        else:
            self._log("⚠️  Session tidak ada → Mode: LOGIN OTOMATIS", "WARNING")

        try:
            with sync_playwright() as pw:
                headless    = self.config.get("headless", False)
                chrome_path = self._find_chrome_executable()

                launch_args = [
                    "--no-sandbox",
                    "--disable-blink-features=AutomationControlled",
                    "--disable-dev-shm-usage",
                    "--no-first-run",
                    "--no-default-browser-check",
                    "--disable-background-networking",
                    "--password-store=basic",
                    "--use-mock-keychain",
                    "--disable-features=IsolateOrigins,site-per-process",
                ]

                launch_kwargs = dict(
                    headless=headless,
                    args=launch_args,
                    ignore_default_args=["--enable-automation"],
                )

                browser = None
                if chrome_path:
                    try:
                        browser = pw.chromium.launch(executable_path=chrome_path, **launch_kwargs)
                        self._log(f"💻 Pakai Chrome: {chrome_path}", "SUCCESS")
                    except Exception as e:
                        self._log(f"⚠️  Chrome path gagal: {e}", "WARNING")
                        browser = None

                if browser is None:
                    try:
                        browser = pw.chromium.launch(channel="chrome", **launch_kwargs)
                        self._log("💻 Pakai Chrome via channel", "SUCCESS")
                    except Exception:
                        browser = pw.chromium.launch(**launch_kwargs)
                        self._log("💻 Pakai Chromium (fallback)", "WARNING")

                ctx_kwargs = dict(
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

                if use_session:
                    ctx_kwargs["storage_state"] = self.session_file

                ctx = browser.new_context(**ctx_kwargs)
                ctx.add_init_script(MINIMAL_STEALTH_JS)

                page = ctx.new_page()
                page.add_init_script(
                    "Object.defineProperty(navigator, 'webdriver', { get: () => undefined });"
                )

                ok = apply_stealth(page)
                if ok:
                    self._log(f"✅ Stealth applied ({stealth_info()})", "SUCCESS")

                result = self._run_session(page, use_session=use_session)
                browser.close()

            if result:
                self._done(True, f"✅ Video tersimpan: {result}", result)
            else:
                self._done(False, "Generate video gagal atau dibatalkan.")
        except Exception as e:
            self._log(f"❌ Fatal error: {e}", "ERROR")
            self._done(False, str(e))

    # ─────────────────────────────────────────────────────────
    def _run_session(self, page, use_session: bool = False) -> Optional[str]:

        self._progress(5, "Membuka Gemini Enterprise...")
        self._log("🌐 Membuka https://business.gemini.google/ ...")

        if use_session:
            page.goto(GEMINI_HOME_URL, wait_until="networkidle", timeout=40_000)
            page.wait_for_timeout(random.randint(2000, 3500))
            current_url = page.url
            self._log(f"   URL: {current_url}")

            if any(x in current_url for x in ["signin", "login", "accounts.google"]):
                self._log("⚠️  Session expired, fallback ke login otomatis...", "WARNING")
                self._debug_dump(page, "session_expired")
                use_session = False
            else:
                self._log("✅ Session valid! Langsung ke dashboard.", "SUCCESS")
                self._progress(50, "Session OK, buka menu Veo...")
                return self._run_veo(page)

        # ── LOGIN OTOMATIS dengan auto-retry ───────────────────────────
        for login_attempt in range(1, MAX_LOGIN_RETRY + 1):
            if self._cancelled: return None

            self._log(f"🔄 Login attempt {login_attempt}/{MAX_LOGIN_RETRY}...")

            # Warm up hanya di attempt pertama
            if login_attempt == 1:
                page.goto("https://www.google.com", wait_until="domcontentloaded", timeout=20_000)
                page.wait_for_timeout(random.randint(1800, 3000))
                page.mouse.wheel(0, random.randint(100, 300))
                page.wait_for_timeout(random.randint(500, 1000))

            # Buka Gemini → redirect ke login
            page.goto(GEMINI_HOME_URL, wait_until="networkidle", timeout=40_000)
            page.wait_for_timeout(random.randint(2000, 3500))

            current_url = page.url
            self._log(f"   URL setelah redirect: {current_url}")
            self._debug_dump(page, f"login_attempt{login_attempt}_redirect")

            # Cek error page sebelum input email
            if self._is_error_page(page):
                self._log("⚠️  Halaman error sebelum input email!", "WARNING")
                if self._click_signin_retry(page):
                    self._log("   → Klik 'Sign up or sign in' berhasil, coba lagi...", "WARNING")
                    continue
                else:
                    self._log("❌ Tombol retry tidak ditemukan.", "ERROR")
                    break

            if self._cancelled: return None

            # ── Tunggu form email ─────────────────────────────────────
            self._progress(10, f"Menunggu form login ({login_attempt}/{MAX_LOGIN_RETRY})...")
            try:
                page.wait_for_selector(", ".join(EMAIL_SELECTORS[:5]), timeout=20_000)
                self._log("   ✅ Form login terdeteksi")
            except PWTimeout:
                self._log("⚠️  Form email timeout", "WARNING")

            self._log_all_inputs(page)
            email_input = self._find_input(page, EMAIL_SELECTORS, timeout_ms=10_000)
            if not email_input:
                self._log("❌ Input email tidak ditemukan!", "ERROR")
                self._debug_dump(page, f"login_attempt{login_attempt}_no_email")
                continue

            # ── Input email ─────────────────────────────────────────
            self._log(f"📧 Input email: {self.mask_email}")
            try:
                email_input.scroll_into_view_if_needed()
                page.wait_for_timeout(random.randint(400, 800))
                self._human_type(page, email_input, self.mask_email)

                val = email_input.input_value()
                if val != self.mask_email:
                    email_input.fill(self.mask_email)
                    page.wait_for_timeout(500)

                self._log(f"   ✅ Input: '{val}'")

                wd = page.evaluate("navigator.webdriver")
                self._log(f"   🔍 navigator.webdriver = {wd}", "WARNING")

                page.wait_for_timeout(random.randint(900, 1800))

                # Klik submit
                submit_el = None
                for sel in SUBMIT_SELECTORS:
                    submit_el = page.query_selector(sel)
                    if submit_el:
                        self._log(f"   ✅ Submit: [{sel}]")
                        break

                if submit_el:
                    self._human_click(page, submit_el)
                else:
                    page.keyboard.press("Enter")

                self._log("✅ Email tersubmit, menunggu respons...")
                page.wait_for_timeout(random.randint(3000, 5000))

                # Cek apakah muncul halaman error setelah submit
                if self._is_error_page(page):
                    self._log(f"⚠️  Muncul 'Let's try something else' (attempt {login_attempt})", "WARNING")
                    self._debug_dump(page, f"login_attempt{login_attempt}_error")

                    if login_attempt < MAX_LOGIN_RETRY:
                        clicked = self._click_signin_retry(page)
                        if clicked:
                            self._log("   → Klik 'Sign up or sign in', tunggu form lagi...", "WARNING")
                            # Tunggu form email muncul kembali
                            try:
                                page.wait_for_selector(", ".join(EMAIL_SELECTORS[:5]), timeout=15_000)
                                self._log("   ✅ Form email muncul kembali, ulangi input...", "WARNING")
                            except PWTimeout:
                                self._log("   ⚠️  Form tidak muncul setelah retry", "WARNING")
                            # Jeda sebelum retry
                            page.wait_for_timeout(random.randint(2000, 4000))
                            continue  # Langsung ulangi loop dari awal (tidak reload page)
                        else:
                            self._log("   ❌ Tombol 'Sign up or sign in' tidak ditemukan", "ERROR")
                    else:
                        self._log("❌ Semua retry habis.", "ERROR")
                    break  # Keluar dari loop

            except Exception as e:
                self._log(f"❌ Error input email: {e}", "ERROR")
                self._debug_dump(page, f"login_attempt{login_attempt}_exception")
                continue

            if self._cancelled: return None

            # ── OTP ─────────────────────────────────────────────────
            self._progress(20, "Menunggu OTP dari Gmail...")
            self._log(f"   URL setelah submit: {page.url}")
            self._debug_dump(page, "step3_otp_page")

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

            if not otp_code:
                self._log("❌ Gagal dapat OTP!", "ERROR")
                self._debug_dump(page, "step3_failed")
                return None
            if self._cancelled: return None

            # ── Input OTP ──────────────────────────────────────────
            self._progress(35, "Memasukkan kode OTP...")
            self._log("✏️  Input OTP...")
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
                page.wait_for_url("*business.gemini.google*", timeout=25_000)
                self._log("✅ Login berhasil!", "SUCCESS")

                # Auto-save session
                try:
                    os.makedirs(os.path.dirname(self.session_file), exist_ok=True)
                    page.context.storage_state(path=self.session_file)
                    self._log(f"💾 Session tersimpan: {self.session_file}", "SUCCESS")
                except Exception as se:
                    self._log(f"⚠️  Gagal simpan session: {se}", "WARNING")

                return self._run_veo(page)

            except PWTimeout:
                self._log("❌ Login gagal — redirect timeout!", "ERROR")
                self._debug_dump(page, "step4_failed")
                return None

        # Semua retry habis
        self._log("❌ Semua login attempt gagal.", "ERROR")
        self._log("   → Jalankan Save_Session.bat untuk login manual.", "WARNING")
        return None

    # ─────────────────────────────────────────────────────────
    def _run_veo(self, page) -> Optional[str]:

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
                    if veo_item: break
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

        # ── Input prompt ──────────────────────────────────────────
        self._progress(60, "Input prompt...")
        self._debug_dump(page, "step6_veo_open")
        try:
            prompt_el = self._find_input(page, [
                "textarea", "[contenteditable='true']",
                "input[placeholder*='prompt' i]", "[role='textbox']",
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

        # ── Polling video ─────────────────────────────────────────
        self._progress(70, "Menunggu Veo generate...")
        self._log(f"⏳ Polling max {VIDEO_GEN_TIMEOUT}s...")
        start = time.time()
        video_ready = False

        while time.time() - start < VIDEO_GEN_TIMEOUT:
            if self._cancelled: return None
            elapsed = int(time.time() - start)
            self._progress(
                min(70 + int((elapsed / VIDEO_GEN_TIMEOUT) * 18), 88),
                f"Generate... {elapsed}s/{VIDEO_GEN_TIMEOUT}s"
            )
            dl = page.query_selector("button:has-text('Download'), a[download], button[aria-label*='download' i]")
            if dl:
                video_ready = True; break
            vid = page.query_selector("video[src]")
            if vid and "blob" not in (vid.get_attribute("src") or ""):
                video_ready = True; break
            time.sleep(POLLING_INTERVAL)

        if not video_ready:
            self._debug_dump(page, "step7_timeout")
            return None
        if self._cancelled: return None

        # ── Download ──────────────────────────────────────────────
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
