"""
gmail_otp.py  —  GmailOTPReader

Baca OTP dari Gmail secara otomatis via Google API.
Khusus untuk Gemini Enterprise (Google Cloud OTP).

Strategi ekstraksi OTP (berurutan, berhenti di yang pertama berhasil):
  1. HTML-first: cari <span>/<td>/<div> dengan font-size >= 20px
     atau background-color khusus blok kode (biru muda, abu, dll)
     atau color yang merupakan warna kode OTP Google / Gemini
  2. HTML-first: cari elemen STANDALONE yang HANYA berisi 4-8 char alphanumeric
  3. Regex di plain-text AFTER strip header Firefox Relay
     — hanya angka murni 6-digit atau pola eksplisit "code is: XXXX"
     — SKIP kata bahasa Inggris UMUM via stopword list
     — SKIP angka dalam konteks copyright/footer

Catatan penting:
  - _is_english_word() HANYA dipakai di plain-text fallback (strategi 3)
  - Untuk strategi 1 & 2 (HTML), pure-alpha OTP seperti FPXSBS TETAP valid
    karena sudah difilter oleh HTML context (font besar / background khusus)
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

# ── Warna yang dipakai Google / Gemini di blok OTP ────────────────────────
# Termasuk navy dark blue (#1c3a70) yang dipakai Gemini Enterprise
# dan warna-warna lain yang umum di email transaksional Google
OTP_BLOCK_COLORS = {
    # Google standard blue
    "#4285f4", "#1a73e8", "#1558d6", "#1967d2",
    "#185abc", "#174ea6", "#0d47a1", "#1976d2",
    # Gemini Enterprise navy dark blue
    "#1c3a70", "#1b3a6b", "#1e3a5f", "#1a3560",
    "#2c4a8a", "#1d3461", "#1f3d7a", "#173060",
    # rgb variants
    "rgb(66,133,244)", "rgb(26,115,232)", "rgb(21,90,214)",
    "rgb(28,58,112)",  # #1c3a70 in rgb
}

# Background warna untuk blok kode (light blue, abu-abu muda, dll)
OTP_BG_COLORS = {
    "#eaf2ff", "#e8f0fe", "#f1f8ff", "#e3f2fd",
    "#f0f4ff", "#dce8fc", "#cfe2ff", "#d2e3fc",
    "#f5f5f5", "#eeeeee", "#f8f9fa", "#f2f2f2",
}

# Kata bahasa Inggris PENDEK yang sering muncul sebagai false positive
# di plain-text fallback. Daftar ini TIDAK dipakai untuk HTML-parsed code.
ENGLISH_STOPWORDS_PLAINTEXT = {
    "THIS", "THAT", "FROM", "WITH", "HAVE", "WILL", "YOUR", "EMAIL",
    "ALIAS", "SENT", "STOP", "LINK", "CLICK", "HERE", "MORE", "INFO",
    "MAIL", "TEAM", "SIGN", "OPEN", "VIEW", "HELP", "NEXT", "BACK",
    "VERIFY", "GOOGLE", "GMAIL", "RELAY", "FIREFOX", "MOZMAIL",
    "LEARN", "ABOUT", "BELOW", "ABOVE", "ENTER", "INPUT", "SUBMIT",
    "PLEASE", "CHECK", "VALID", "EXPIR", "NEVER", "SHARE", "PASS",
    "THANK", "SINCER", "FORWARD", "IGNORE", "REQUEST", "RECEIVED",
    "ACCESS", "ENTERPRISE", "BUSINESS", "EDITION", "GEMINI", "CLOUD",
    "ALIAS", "INBOX", "SPAM", "DRAFT", "SENT", "TRASH", "LABEL",
}

# Pattern regex — HANYA untuk angka murni atau pola eksplisit
NUMERIC_OTP_PATTERNS = [
    r'(?:verification\s+)?code\s*(?:is\s*)?[:\s]+([0-9]{4,8})\b',
    r'one-time\s+(?:verification\s+)?code[^0-9]{0,20}([0-9]{4,8})\b',
    r'Your\s+(?:verification\s+)?code\s+is[:\s]+([0-9]{4,8})\b',
    r'OTP[:\s]+([0-9]{4,8})\b',
    r'\b([0-9]{6})\b',
    r'\b([0-9]{7,8})\b',
    r'\b([0-9]{4})\b',
]

FOOTER_CONTEXT_KEYWORDS = [
    "copyright", "©", "all rights", "google llc",
    "mountain view", "amphitheatre", "94043",
    "1600", "privacy", "terms", "unsubscribe",
    "manage", "preferences", "address",
]

FALSE_POSITIVE_YEARS = {str(y) for y in range(2018, 2032)}


def _normalize_color(raw: str) -> str:
    """Lowercase dan strip spasi dari string warna CSS."""
    return raw.lower().replace(" ", "").strip()


def _color_matches_otp_set(color_str: str, color_set: set) -> bool:
    """Cek apakah color_str cocok dengan salah satu warna di color_set."""
    c = _normalize_color(color_str)
    if c in color_set:
        return True
    # Partial match untuk hex pendek / variasi
    for ref in color_set:
        if c.startswith(ref[:4]) and len(c) >= 4:
            return True
    return False


def _extract_style_props(style: str) -> dict:
    """
    Parse inline CSS style string menjadi dict property → value.
    Contoh: "font-size:28px;color:#1c3a70" → {"font-size": "28px", "color": "#1c3a70"}
    """
    props = {}
    for decl in style.split(";"):
        decl = decl.strip()
        if ":" in decl:
            k, _, v = decl.partition(":")
            props[k.strip().lower()] = v.strip().lower()
    return props


def _is_otp_styled_element(tag) -> tuple:
    """
    Deteksi apakah elemen HTML ini adalah blok kode OTP berdasarkan style.
    Return (is_otp_block: bool, reason: str)

    Kriteria:
      - font-size >= 20px / 15pt
      - color cocok dengan OTP_BLOCK_COLORS
      - background-color cocok dengan OTP_BG_COLORS
      - letter-spacing (biasanya ada di blok kode)
      - kombinasi font-weight:bold + font-size >= 16px
    """
    style_raw = tag.get("style", "") or ""
    if not style_raw:
        # Juga cek attribute color dan bgcolor langsung
        color_attr = _normalize_color(tag.get("color", ""))
        bgcolor_attr = _normalize_color(tag.get("bgcolor", ""))
        if color_attr and _color_matches_otp_set(color_attr, OTP_BLOCK_COLORS):
            return True, f"color attr={color_attr}"
        if bgcolor_attr and _color_matches_otp_set(bgcolor_attr, OTP_BG_COLORS):
            return True, f"bgcolor attr={bgcolor_attr}"
        return False, ""

    props = _extract_style_props(style_raw)

    # Cek font-size
    fs_raw = props.get("font-size", "")
    is_large_font = False
    if fs_raw:
        m = re.match(r'([\d.]+)(px|pt|em|rem)', fs_raw)
        if m:
            val  = float(m.group(1))
            unit = m.group(2)
            px   = val if unit == "px" else \
                   val * 1.333 if unit == "pt" else \
                   val * 16
            if px >= 20:
                is_large_font = True
        elif fs_raw in ("large", "x-large", "xx-large", "larger"):
            is_large_font = True

    if is_large_font:
        return True, f"font-size={fs_raw}"

    # Cek color (text color)
    color_val = props.get("color", "")
    if color_val and _color_matches_otp_set(color_val, OTP_BLOCK_COLORS):
        return True, f"color={color_val}"

    # Cek background-color
    bg_val = props.get("background-color", "") or props.get("background", "")
    if bg_val and _color_matches_otp_set(bg_val, OTP_BG_COLORS):
        return True, f"background-color={bg_val}"

    # Cek letter-spacing (hampir selalu ada di blok kode)
    ls_raw = props.get("letter-spacing", "")
    if ls_raw and ls_raw not in ("normal", "0", "0px", "0em"):
        # Hanya valid jika font-weight bold atau font-size >= 14px
        fw = props.get("font-weight", "")
        if fw in ("bold", "700", "800", "900"):
            return True, f"letter-spacing={ls_raw} + font-weight={fw}"

    return False, ""


def _extract_otp_from_html(html: str, log_fn=None) -> Optional[str]:
    """
    Strategi 1 & 2: Parse HTML langsung.

    Penting: untuk HTML-parsed candidates, TIDAK dipakai _is_english_word()
    karena OTP seperti FPXSBS sudah difilter oleh konteks HTML (style).
    Stopword hanya berlaku di plain-text fallback.
    """
    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception:
        return None

    candidates = []  # list of (priority, code)

    # ── Strategi 1: Elemen dengan OTP style (font besar / warna kode) ─────
    for tag in soup.find_all(True):
        is_otp, reason = _is_otp_styled_element(tag)
        if not is_otp:
            continue

        # Ambil inner text, strip whitespace
        text = re.sub(r'\s+', '', tag.get_text(separator="", strip=True))

        # Harus persis 4-8 karakter alphanumeric
        if not re.fullmatch(r'[A-Z0-9]{4,8}', text, re.IGNORECASE):
            continue

        code = text.upper()
        if log_fn:
            log_fn(
                f"   🎯 OTP via HTML style [{reason}]: '{code}'",
                "WARNING"
            )
        candidates.append((1, code))

    # ── Strategi 2: Standalone block 4-8 char alphanumeric ────────────────
    # Menangkap <td>/<div>/<span> yang isinya HANYA kode, tanpa teks lain
    STANDALONE_TAGS = ["td", "div", "p", "span", "h1", "h2", "h3",
                       "b", "strong", "center", "blockquote"]
    for tag in soup.find_all(STANDALONE_TAGS):
        text = re.sub(r'\s+', '', tag.get_text(separator="", strip=True))
        if not re.fullmatch(r'[A-Z0-9]{4,8}', text, re.IGNORECASE):
            continue
        code = text.upper()

        # Pastikan child tag tidak punya teks tambahan
        child_text = re.sub(
            r'\s+', '',
            "".join(c.get_text(strip=True) for c in tag.children if isinstance(c, Tag))
        )
        if child_text and not re.fullmatch(r'[A-Z0-9]{4,8}', child_text, re.IGNORECASE):
            continue

        # Untuk standalone block, SKIP kata-kata HTML umum yang bukan kode
        # Tapi JANGAN skip pure-alpha karena OTP bisa full-alpha (FPXSBS)
        # Hanya skip yang ada di stopword list
        if code in ENGLISH_STOPWORDS_PLAINTEXT:
            continue

        if log_fn:
            log_fn(
                f"   🎯 OTP via standalone <{tag.name}>: '{code}'",
                "WARNING"
            )
        candidates.append((2, code))

    if candidates:
        candidates.sort(key=lambda x: x[0])
        # Dedup: jika ada kode yang sama di priority 1 dan 2, ambil priority 1
        return candidates[0][1]

    return None


def _extract_otp_from_text(plain_text: str, log_fn=None) -> Optional[str]:
    """
    Strategi 3: Regex di plain text.
    Hanya angka murni, SKIP kata bahasa Inggris dan angka footer.
    """
    relay_strip = re.compile(
        r'^.*?(?:This email was sent to your alias[^.]*\.'
        r'|You received this email because[^.]*\.'
        r'|To stop receiving emails sent to this alias[^.]*\.)\s*',
        re.DOTALL | re.IGNORECASE
    )
    stripped = relay_strip.sub("", plain_text).strip()
    text_to_search = stripped if stripped else plain_text

    for pattern in NUMERIC_OTP_PATTERNS:
        for m in re.finditer(pattern, text_to_search, re.IGNORECASE):
            code = m.group(1).upper()

            if re.fullmatch(r'[0-9]{4}', code) and code in FALSE_POSITIVE_YEARS:
                continue

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
        html_parts = []
        text_parts = []

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
        if not plain_str and html_str:
            plain_str = BeautifulSoup(html_str, "lxml").get_text(separator=" ")

        return html_str, plain_str

    def _extract_otp_code(self, msg_id: str) -> Optional[str]:
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

        # Strategi 1 & 2: HTML-first
        if html_str:
            otp = _extract_otp_from_html(html_str, log_fn=self._log)
            if otp:
                self._log(f"   ✅ OTP: '{otp}' (via HTML)", "WARNING")
                return otp

        # Strategi 3: Regex plain text fallback
        if plain_str:
            otp = _extract_otp_from_text(plain_str, log_fn=self._log)
            if otp:
                self._log(f"   ✅ OTP: '{otp}' (via text)", "WARNING")
                return otp

        self._log("   ⚠️  Tidak ada kode OTP valid di email ini", "WARNING")
        return None

    def _search_messages_latest(self, query: str, max_results: int = 10) -> list:
        try:
            result = self._svc().users().messages().list(
                userId="me", q=query, maxResults=max_results,
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
            queries += [
                ("INBOX mask+subject", f'to:{mask_email} subject:"verification code"{ts_filter}'),
                ("SPAM mask+subject",  f'in:spam to:{mask_email} subject:"verification code"{ts_filter}'),
                ("INBOX by mask",      f"to:{mask_email}{ts_filter}"),
                ("SPAM by mask",       f"in:spam to:{mask_email}{ts_filter}"),
            ]
        queries += [
            ("INBOX googlecloud-sender", f"from:noreply-googlecloud@google.com{ts_filter}"),
            ("SPAM googlecloud-sender",  f"in:spam from:noreply-googlecloud@google.com{ts_filter}"),
            ("INBOX gemini-subject",     f'subject:"Gemini Enterprise verification code"{ts_filter}'),
            ("SPAM gemini-subject",      f'in:spam subject:"Gemini Enterprise verification code"{ts_filter}'),
            ("INBOX google.com",         f"from:google.com{ts_filter}"),
            ("SPAM google.com",          f"in:spam from:google.com{ts_filter}"),
        ]

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
