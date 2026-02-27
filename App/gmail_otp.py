"""
gmail_otp.py  —  GmailOTPReader

Baca OTP dari Gmail secara otomatis via Google API.
Khusus untuk Gemini Enterprise (Google Cloud OTP).

Strategi ekstraksi OTP (berurutan, berhenti di yang pertama berhasil):
  1. HTML-first: cari elemen <td>/<div>/<p> dengan font-size besar (>= 20px)
     atau warna teks biru (#4285f4, #1a73e8, dll) — kolom OTP Google persis ini
  2. HTML-first: cari elemen yang HANYA berisi teks 4-8 karakter alphanumeric
     (tanpa spasi, tanpa kata lain) — blok kode mandiri
  3. Regex di plain-text AFTER strip header Firefox Relay
     — hanya angka murni 6-digit atau pola eksplisit "code is: XXXX"
     — SKIP kata bahasa Inggris (THIS, THAT, FROM, ...) via kamus stopword
     — SKIP angka dalam konteks copyright/footer

Tidak ada lagi fallback broad r'\\b([A-Z0-9]{6})\\b' yang menyebabkan
false positive seperti "THIS", "THAT", "ALIAS", dll.
"""
import base64
import os
import pickle
import re
import time
import datetime
from typing import Callable, Optional
from bs4 import BeautifulSoup, Tag

from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]

IGNORE_SUBJECTS = [
    "welcome", "newsletter", "get started",
    "subscription", "announcement",
]

# Warna biru yang dipakai Google di blok OTP
GOOGLE_BLUE_COLORS = {
    "#4285f4", "#1a73e8", "#1558d6", "#1967d2",
    "#185abc", "#174ea6", "#0d47a1", "#1976d2",
    "rgb(66,133,244)", "rgb(26,115,232)", "rgb(21,90,214)",
}

# Kata bahasa Inggris umum yang BUKAN OTP (false positive dari plain text)
# Daftar ini bisa diperluas sesuai kebutuhan
ENGLISH_STOPWORDS = {
    "THIS", "THAT", "FROM", "WITH", "HAVE", "WILL", "YOUR", "EMAIL",
    "ALIAS", "SENT", "STOP", "LINK", "CLICK", "HERE", "MORE", "INFO",
    "MAIL", "TEAM", "SIGN", "OPEN", "VIEW", "HELP", "NEXT", "BACK",
    "CODE", "VERIFY", "GOOGLE", "GMAIL", "RELAY", "FIREFOX", "MOZMAIL",
    "LEARN", "ABOUT", "BELOW", "ABOVE", "ENTER", "INPUT", "SUBMIT",
    "PLEASE", "CHECK", "VALID", "EXPIR", "NEVER", "SHARE", "PASS",
    "THANK", "SINCER", "FORWARD", "IGNORE", "REQUEST", "RECEIVED",
    "ACCESS", "ENTERPRISE", "BUSINESS", "EDITION", "VERIFY", "GEMINI",
}

# Pattern regex — HANYA untuk angka murni atau pola eksplisit
# Tidak ada lagi alphanumeric broad match
NUMERIC_OTP_PATTERNS = [
    # "code is: 123456" / "code: 123456"
    r'(?:verification\s+)?code\s*(?:is\s*)?[:\s]+([0-9]{4,8})\b',
    r'one-time\s+(?:verification\s+)?code[^0-9]{0,20}([0-9]{4,8})\b',
    r'Your\s+(?:verification\s+)?code\s+is[:\s]+([0-9]{4,8})\b',
    r'OTP[:\s]+([0-9]{4,8})\b',
    # Standalone 6-digit number
    r'\b([0-9]{6})\b',
    # Standalone 7-8 digit
    r'\b([0-9]{7,8})\b',
    # Standalone 4-digit number (fallback terakhir)
    r'\b([0-9]{4})\b',
]

# Konteks yang menandakan angka adalah bagian dari footer/alamat, bukan OTP
FOOTER_CONTEXT_KEYWORDS = [
    "copyright", "©", "all rights", "google llc",
    "mountain view", "amphitheatre", "94043",
    "1600", "privacy", "terms", "unsubscribe",
    "manage", "preferences", "address",
]

# Tahun yang sering muncul di footer
FALSE_POSITIVE_YEARS = {str(y) for y in range(2018, 2032)}


def _is_english_word(token: str) -> bool:
    """Return True jika token adalah kata bahasa Inggris umum (bukan OTP)."""
    upper = token.upper()
    # Cek exact match
    if upper in ENGLISH_STOPWORDS:
        return True
    # Cek apakah semua karakter adalah huruf (bukan alphanumeric campuran)
    # OTP yang valid biasanya campuran huruf+angka atau angka saja
    if upper.isalpha() and len(upper) >= 4:
        return True
    return False


def _extract_otp_from_html(html: str, log_fn=None) -> Optional[str]:
    """
    Strategi 1 & 2: Parse HTML langsung dengan BeautifulSoup.

    Cari elemen yang merupakan blok kode OTP berdasarkan:
      - font-size >= 20px di style attribute / inline CSS
      - warna teks biru (Google brand color)
      - elemen yang HANYA berisi teks 4-8 karakter alphanumeric
    """
    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception:
        return None

    candidates = []

    # ── Strategi 1: Elemen dengan font besar atau warna biru ──────────────
    for tag in soup.find_all(True):
        style = tag.get("style", "") or ""
        style_lower = style.lower().replace(" ", "")

        is_large_font = False
        is_blue = False

        # Cek font-size
        fs_match = re.search(r'font-size\s*:\s*(\d+(?:\.\d+)?)(px|pt|em|rem)', style_lower)
        if fs_match:
            size_val  = float(fs_match.group(1))
            size_unit = fs_match.group(2)
            # Konversi ke px approx
            if size_unit == "px":
                size_px = size_val
            elif size_unit == "pt":
                size_px = size_val * 1.333
            elif size_unit in ("em", "rem"):
                size_px = size_val * 16
            else:
                size_px = size_val
            if size_px >= 20:
                is_large_font = True

        # Cek warna biru
        for blue in GOOGLE_BLUE_COLORS:
            if blue.replace(" ", "") in style_lower:
                is_blue = True
                break
        # Juga cek color attribute langsung
        color_attr = (tag.get("color") or "").lower().strip()
        if color_attr in GOOGLE_BLUE_COLORS or color_attr.startswith("#42") or color_attr.startswith("#1a"):
            is_blue = True

        if is_large_font or is_blue:
            text = tag.get_text(separator="", strip=True)
            # Bersihkan spasi dan newline
            text = re.sub(r'\s+', '', text)
            if re.fullmatch(r'[A-Z0-9]{4,8}', text, re.IGNORECASE):
                code = text.upper()
                if not _is_english_word(code):
                    if log_fn:
                        log_fn(
                            f"   🎯 OTP via HTML style (font={is_large_font}, blue={is_blue}): '{code}'",
                            "WARNING"
                        )
                    candidates.append((1, code))  # priority 1

    # ── Strategi 2: Elemen yang HANYA berisi 4-8 char alphanumeric ────────
    # Ini menangkap <td> atau <div> yang isinya cuma kode (tanpa teks lain)
    STANDALONE_TAGS = ["td", "div", "p", "span", "h1", "h2", "h3", "b", "strong"]
    for tag in soup.find_all(STANDALONE_TAGS):
        text = tag.get_text(separator="", strip=True)
        text_clean = re.sub(r'\s+', '', text)
        # Harus persis 4-8 karakter alphanumeric, tidak lebih
        if re.fullmatch(r'[A-Z0-9]{4,8}', text_clean, re.IGNORECASE):
            code = text_clean.upper()
            if not _is_english_word(code):
                # Pastikan tidak ada child tag yang mengandung lebih banyak teks
                child_text = "".join(
                    c.get_text(strip=True) for c in tag.children if isinstance(c, Tag)
                )
                if not child_text or re.fullmatch(r'[A-Z0-9]{4,8}', re.sub(r'\s+', '', child_text), re.IGNORECASE):
                    if log_fn:
                        log_fn(
                            f"   🎯 OTP via standalone HTML block <{tag.name}>: '{code}'",
                            "WARNING"
                        )
                    candidates.append((2, code))  # priority 2

    if candidates:
        # Ambil candidate dengan priority terbaik (angka terkecil = lebih tinggi)
        candidates.sort(key=lambda x: x[0])
        return candidates[0][1]

    return None


def _extract_otp_from_text(plain_text: str, log_fn=None) -> Optional[str]:
    """
    Strategi 3: Regex di plain text.
    Hanya angka murni, dan pola eksplisit "code is: XXXX".
    SKIP kata bahasa Inggris dan angka dalam konteks footer.
    """
    # Strip header Firefox Relay (teks sebelum body asli Google)
    # Header Relay biasanya: "This email was sent to your alias ..."
    relay_strip = re.compile(
        r'^.*?(?:This email was sent to your alias[^.]*\.|'
        r'You received this email because[^.]*\.|'
        r'To stop receiving emails sent to this alias[^.]*\.)\\s*',
        re.DOTALL | re.IGNORECASE
    )
    stripped = relay_strip.sub("", plain_text).strip()
    # Kalau strip tidak berhasil (pattern tidak match), pakai full text
    text_to_search = stripped if stripped else plain_text

    for pattern in NUMERIC_OTP_PATTERNS:
        for m in re.finditer(pattern, text_to_search, re.IGNORECASE):
            code = m.group(1).upper()

            # Skip tahun
            if re.fullmatch(r'[0-9]{4}', code) and code in FALSE_POSITIVE_YEARS:
                continue

            # Skip konteks footer
            ctx_start = max(0, m.start() - 40)
            ctx_end   = min(len(text_to_search), m.end() + 20)
            context   = text_to_search[ctx_start:ctx_end].lower()
            if any(kw in context for kw in FOOTER_CONTEXT_KEYWORDS):
                continue

            if log_fn:
                log_fn(f"   🎯 OTP via regex plain-text: '{code}'", "WARNING")
            return code

    return None


class GmailOTPReader:

    def __init__(self, base_dir: str):
        self.base_dir   = base_dir
        self.token_path = os.path.join(base_dir, "token.pickle")
        self.creds_path = os.path.join(base_dir, "credentials.json")
        self._service   = None
        self._log_cb: Optional[Callable] = None

    def _log(self, msg: str, level: str = "INFO"):
        if self._log_cb:
            self._log_cb(msg, level)

    # ── Auth ──────────────────────────────────────────────────────────────
    def _authenticate(self):
        creds = None
        if os.path.exists(self.token_path):
            with open(self.token_path, "rb") as f:
                creds = pickle.load(f)
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                    self._log("🔄 Gmail token di-refresh")
                except Exception:
                    creds = None
            if not creds:
                self._log("🔐 Memulai OAuth Gmail...")
                if not os.path.exists(self.creds_path):
                    raise FileNotFoundError(
                        f"credentials.json tidak ditemukan di: {self.creds_path}"
                    )
                flow  = InstalledAppFlow.from_client_secrets_file(self.creds_path, GMAIL_SCOPES)
                creds = flow.run_local_server(port=0)
            with open(self.token_path, "wb") as f:
                pickle.dump(creds, f)
        self._service = build("gmail", "v1", credentials=creds)
        self._log("✅ Gmail API terautentikasi")

    def _svc(self):
        if not self._service:
            self._authenticate()
        return self._service

    # ── Helpers ───────────────────────────────────────────────────────────
    def _get_message_timestamp(self, msg_id: str) -> int:
        try:
            meta = self._svc().users().messages().get(
                userId="me", id=msg_id, format="metadata", metadataHeaders=[]
            ).execute()
            return int(meta.get("internalDate", 0)) // 1000
        except Exception:
            return 0

    def _get_html_and_text(self, payload) -> tuple:
        """
        Return (html_str, plain_text_str) dari payload email.
        Prioritaskan HTML karena lebih kaya informasi untuk OTP detection.
        """
        html_parts  = []
        text_parts  = []

        def _walk(part):
            mime = part.get("mimeType", "")
            if "parts" in part:
                for p in part["parts"]:
                    _walk(p)
            else:
                data = part.get("body", {}).get("data", "")
                if not data:
                    return
                decoded = base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="ignore")
                if "html" in mime:
                    html_parts.append(decoded)
                elif "plain" in mime:
                    text_parts.append(decoded)

        _walk(payload)

        html_str  = "\n".join(html_parts)
        plain_str = "\n".join(text_parts)

        # Jika tidak ada plain text, generate dari HTML
        if not plain_str and html_str:
            plain_str = BeautifulSoup(html_str, "lxml").get_text(separator=" ")

        return html_str, plain_str

    def _extract_otp_code(self, msg_id: str) -> Optional[str]:
        """
        Ekstrak OTP dari email dengan 3 strategi berurutan:
          1. HTML element dengan font besar / warna biru
          2. HTML element standalone (hanya berisi kode)
          3. Regex di plain text (hanya angka, skip kata bahasa Inggris)
        """
        try:
            msg = self._svc().users().messages().get(
                userId="me", id=msg_id, format="full"
            ).execute()
            headers = {
                h["name"].lower(): h["value"]
                for h in msg.get("payload", {}).get("headers", [])
            }
            self._log(f"   📧 From   : {headers.get('from', '-')}", "WARNING")
            self._log(f"   📧 Subject: {headers.get('subject', '-')}", "WARNING")

            subj_lower = headers.get("subject", "").lower()
            for ign in IGNORE_SUBJECTS:
                if ign in subj_lower:
                    self._log(f"   ⏭️  Diabaikan (subject: {ign})", "WARNING")
                    return None

            html_str, plain_str = self._get_html_and_text(msg["payload"])
            snippet = plain_str[:250].replace("\n", " ").strip()
            self._log(f"   📌 Body: {snippet}", "WARNING")

        except Exception as e:
            self._log(f"   ⚠️  Gagal ambil email: {e}", "WARNING")
            return None

        # ── Strategi 1 & 2: HTML-first ────────────────────────────────────
        if html_str:
            otp = _extract_otp_from_html(html_str, log_fn=self._log)
            if otp:
                self._log(f"   ✅ OTP: '{otp}' (via HTML)", "WARNING")
                return otp

        # ── Strategi 3: Regex plain text ──────────────────────────────────
        if plain_str:
            otp = _extract_otp_from_text(plain_str, log_fn=self._log)
            if otp:
                self._log(f"   ✅ OTP: '{otp}' (via text)", "WARNING")
                return otp

        self._log("   ⚠️  Tidak ada kode OTP valid di email ini", "WARNING")
        return None

    def _search_messages_latest(self, query: str, max_results: int = 10) -> list:
        """
        Cari pesan Gmail, return list ID diurutkan dari TERBARU.
        """
        try:
            result = self._svc().users().messages().list(
                userId="me",
                q=query,
                maxResults=max_results,
            ).execute()
            msg_list = result.get("messages", [])
            if not msg_list:
                return []

            dated = []
            for m in msg_list:
                ts = self._get_message_timestamp(m["id"])
                dated.append((ts, m["id"]))
            dated.sort(key=lambda x: x[0], reverse=True)
            return [mid for _, mid in dated]
        except Exception as e:
            self._log(f"   ⚠️  Search gagal [{query[:60]}]: {e}")
            return []

    def mark_as_read(self, msg_id: str):
        try:
            self._svc().users().messages().modify(
                userId="me", id=msg_id,
                body={"removeLabelIds": ["UNREAD"]}
            ).execute()
        except Exception:
            pass

    def move_from_spam(self, msg_id: str):
        try:
            self._svc().users().messages().modify(
                userId="me", id=msg_id,
                body={"removeLabelIds": ["SPAM"], "addLabelIds": ["INBOX"]}
            ).execute()
            self._log("📥 Email dipindahkan SPAM → INBOX", "WARNING")
        except Exception as e:
            self._log(f"   ⚠️  Gagal pindah dari spam: {e}", "WARNING")

    # ── Main polling ──────────────────────────────────────────────────────
    def wait_for_otp(
        self,
        sender:          str                = "noreply-googlecloud@google.com",
        timeout:         int                = 120,
        interval:        int                = 5,
        log_callback:    Optional[Callable] = None,
        mask_email:      str                = None,
        after_timestamp: int                = 0,
    ) -> str:
        self._log_cb = log_callback
        self._svc()

        ts_str    = (
            datetime.datetime.fromtimestamp(after_timestamp).strftime("%H:%M:%S")
            if after_timestamp else "N/A"
        )
        ts_filter = f" after:{max(0, after_timestamp - 60)}" if after_timestamp else ""

        queries = []

        if mask_email:
            queries.append((
                "INBOX mask+subject",
                f'to:{mask_email} subject:"verification code"{ts_filter}'
            ))
            queries.append((
                "SPAM mask+subject",
                f'in:spam to:{mask_email} subject:"verification code"{ts_filter}'
            ))
            queries.append((
                "INBOX by mask",
                f"to:{mask_email}{ts_filter}"
            ))
            queries.append((
                "SPAM by mask",
                f"in:spam to:{mask_email}{ts_filter}"
            ))

        queries.append((
            "INBOX googlecloud-sender",
            f"from:noreply-googlecloud@google.com{ts_filter}"
        ))
        queries.append((
            "SPAM googlecloud-sender",
            f"in:spam from:noreply-googlecloud@google.com{ts_filter}"
        ))
        queries.append((
            "INBOX gemini-subject",
            f'subject:"Gemini Enterprise verification code"{ts_filter}'
        ))
        queries.append((
            "SPAM gemini-subject",
            f'in:spam subject:"Gemini Enterprise verification code"{ts_filter}'
        ))
        queries.append((
            "INBOX google.com",
            f"from:google.com{ts_filter}"
        ))
        queries.append((
            "SPAM google.com",
            f"in:spam from:google.com{ts_filter}"
        ))

        self._log(
            f"📬 Polling Gmail | cutoff: {ts_str} | {len(queries)} strategi | INBOX+SPAM",
            "WARNING"
        )
        for i, (lbl, _) in enumerate(queries, 1):
            self._log(f"   [{i}] {lbl}")

        start    = time.time()
        seen_ids = set()

        while time.time() - start < timeout:
            for label, q in queries:
                ids = self._search_messages_latest(q, max_results=10)
                for mid in ids:
                    if mid in seen_ids:
                        continue
                    seen_ids.add(mid)

                    if after_timestamp:
                        msg_ts = self._get_message_timestamp(mid)
                        if 0 < msg_ts < (after_timestamp - 60):
                            self._log(
                                f"   ⏩ Email lama "
                                f"({datetime.datetime.fromtimestamp(msg_ts).strftime('%H:%M:%S')}"
                                f" < cutoff {ts_str}) — skip"
                            )
                            continue

                    self._log(f"   🔎 [{label}] id={mid[:8]}...")
                    otp = self._extract_otp_code(mid)
                    if otp:
                        self.mark_as_read(mid)
                        if "spam" in label.lower():
                            self.move_from_spam(mid)
                        self._log(f"✅ OTP ditemukan: {otp}", "SUCCESS")
                        return otp

            elapsed = int(time.time() - start)
            self._log(f"⏳ Polling... {elapsed}s/{timeout}s")
            time.sleep(interval)

        raise TimeoutError(
            f"❌ OTP timeout {timeout}s — email tidak ditemukan di Inbox maupun Spam.\n"
            f"Pastikan Firefox Relay meneruskan email ke Gmail Anda."
        )
