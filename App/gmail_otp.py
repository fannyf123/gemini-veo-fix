"""
gmail_otp.py  —  GmailOTPReader

Baca OTP dari Gmail secara otomatis via Google API.
Khusus untuk Gemini Enterprise (Google Cloud OTP).

Fix:
    - OTP regex diperbaiki: prioritas 6-digit, lalu fallback 4-digit
    - OTP body parsing khusus format Firefox Relay forwarded email
    - Selalu ambil pesan TERBARU (sorted by internalDate desc)
    - Subject filter untuk noreply-googlecloud@google.com
    - Cari di INBOX + SPAM sekaligus
    - Auto pindah ke Inbox jika ketemu di Spam
"""
import base64
import os
import pickle
import re
import time
import datetime
from typing import Callable, Optional
from bs4 import BeautifulSoup

from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]

# ── Subject OTP dari Gemini Enterprise / Google Cloud ────────────────────
OTP_SUBJECTS = [
    "Gemini Enterprise verification code",
    "verification code",
    "Your verification code",
    "Your code",
    "One-time code",
    "Sign in code",
    "Gemini verification",
    "sign in",
]

IGNORE_SUBJECTS = [
    "welcome", "newsletter", "get started",
    "subscription", "announcement",
]

# ── OTP patterns: dari paling spesifik ke paling general ──────────────────
OTP_PATTERNS = [
    # Format eksplisit "verification code is: XXXXXX"
    r'verification\s+code[^\d]{0,20}([A-Z0-9]{4,8})\b',
    r'one-time\s+(?:verification\s+)?code[^\d]{0,20}([A-Z0-9]{4,8})\b',
    r'Your\s+(?:verification\s+)?code\s+is[:\s]+([A-Z0-9]{4,8})\b',
    r'OTP[:\s]+([A-Z0-9]{4,8})\b',
    # Standalone 6-digit number (paling umum untuk Google)
    r'\b([0-9]{6})\b',
    # Standalone 7-8 digit
    r'\b([0-9]{7,8})\b',
    # Alphanumeric 4-8 karakter dalam conteks kode (e.g. JNY3AM)
    r'\b([A-Z0-9]{6})\b',
    # Fallback: 4-digit number
    r'\b([0-9]{4})\b',
]

# Pattern untuk strip footer/header relay sebelum cari OTP
# Ini penting karena Firefox Relay menambah teks di awal body
RELAY_HEADER_PATTERN = re.compile(
    r'^.*?(?:This email was sent to your alias.*?\.|'
    r'You received this email because.*?\.)\s*',
    re.DOTALL | re.IGNORECASE
)


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

    # ── Auth ────────────────────────────────────────────────────────────
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

    # ── Helpers ────────────────────────────────────────────────────────
    def _get_message_timestamp(self, msg_id: str) -> int:
        try:
            meta = self._svc().users().messages().get(
                userId="me", id=msg_id, format="metadata", metadataHeaders=[]
            ).execute()
            return int(meta.get("internalDate", 0)) // 1000
        except Exception:
            return 0

    def _decode_body(self, payload) -> str:
        body = ""
        if "parts" in payload:
            for part in payload["parts"]:
                body += self._decode_body(part)
        else:
            data = payload.get("body", {}).get("data", "")
            if data:
                decoded = base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="ignore")
                if "html" in payload.get("mimeType", ""):
                    body += BeautifulSoup(decoded, "lxml").get_text(separator=" ")
                else:
                    body += decoded
        return body

    def _extract_otp_from_body(self, body: str) -> Optional[str]:
        """
        Cari kode OTP di body email.
        Khusus handle format Firefox Relay forwarded email:
          - Ada header Relay di awal: "This email was sent to your alias..."
          - Lalu body asli dari Google: "Your one-time verification code is: JNY3AM"

        Strategi:
          1. Coba cari di FULL body dulu
          2. Jika tidak ketemu, strip header Relay lalu cari lagi
          3. Kalau ada angka tahun (e.g. 2025, 2026) dalam konteks
             copyright/tahun, SKIP itu (false positive umum).
        """
        # Nomor yang SANGAT sering jadi false positive
        # (tahun di footer: "© 2025 Google LLC")
        FALSE_POSITIVE_YEARS = {str(y) for y in range(2020, 2031)}

        def _search_in(text: str) -> Optional[str]:
            for pattern in OTP_PATTERNS:
                for m in re.finditer(pattern, text, re.IGNORECASE):
                    code = m.group(1).upper()
                    # Skip tahun seperti 2025, 2026 jika pattern 4-digit
                    if re.fullmatch(r'[0-9]{4}', code) and code in FALSE_POSITIVE_YEARS:
                        continue
                    # Skip jika angka ini muncul dalam konteks tahun/copyright
                    ctx_start = max(0, m.start() - 30)
                    ctx_end   = min(len(text), m.end() + 10)
                    context   = text[ctx_start:ctx_end].lower()
                    if any(kw in context for kw in
                           ["copyright", "\u00a9", "all rights", "google llc",
                            "mountain view", "amphitheatre", "94043",
                            "1600", "privacy", "terms"]):
                        continue
                    return code
            return None

        # Coba di full body
        result = _search_in(body)
        if result:
            return result

        # Strip header Relay lalu coba lagi
        stripped = RELAY_HEADER_PATTERN.sub("", body)
        if stripped != body:
            result = _search_in(stripped)
            if result:
                return result

        return None

    def _extract_otp_code(self, msg_id: str) -> Optional[str]:
        """Ambil kode OTP dari body email."""
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

            body = self._decode_body(msg["payload"])
            snippet = body[:300].replace("\n", " ").strip()
            self._log(f"   📌 Body: {snippet}", "WARNING")

        except Exception as e:
            self._log(f"   ⚠️  Gagal ambil email: {e}", "WARNING")
            return None

        otp = self._extract_otp_from_body(body)
        if otp:
            self._log(f"   ✅ OTP: '{otp}'", "WARNING")
            return otp

        self._log("   ⚠️  Tidak ada kode OTP valid di body", "WARNING")
        return None

    def _search_messages_latest(self, query: str, max_results: int = 10) -> list:
        """
        Cari pesan Gmail, return list ID diurutkan dari TERBARU.
        Gmail API secara default sudah mengembalikan newest first,
        tapi kita pastikan dengan sort by internalDate desc.
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

            # Ambil internalDate untuk setiap pesan, sort terbaru duluan
            dated = []
            for m in msg_list:
                ts = self._get_message_timestamp(m["id"])
                dated.append((ts, m["id"]))
            dated.sort(key=lambda x: x[0], reverse=True)  # newest first
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

    # ── Main polling ────────────────────────────────────────────────────
    def wait_for_otp(
        self,
        sender:          str                = "noreply-googlecloud@google.com",
        timeout:         int                = 120,
        interval:        int                = 5,
        log_callback:    Optional[Callable] = None,
        mask_email:      str                = None,
        after_timestamp: int                = 0,
    ) -> str:
        """
        Poll Gmail sampai OTP ditemukan.
        Selalu cek pesan TERBARU duluan (sort by internalDate desc).
        """
        self._log_cb = log_callback
        self._svc()

        ts_str    = (
            datetime.datetime.fromtimestamp(after_timestamp).strftime("%H:%M:%S")
            if after_timestamp else "N/A"
        )
        ts_filter = f" after:{max(0, after_timestamp - 60)}" if after_timestamp else ""

        # ── Build queries (ordered by priority) ─────────────────────────────
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
