"""
gmail_otp.py  —  GmailOTPReader
Baca OTP dari Gmail secara otomatis via Google API.

Fix:
    - Tambah subject: 'Gemini Enterprise verification code'
    - Tambah sender: noreply-googlecloud@google.com
    - Cari OTP di INBOX + SPAM sekaligus
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

# ── Subject yang diketahui dari Gemini Enterprise ────────────────────────────
OTP_SUBJECTS = [
    "Gemini Enterprise verification code",   # ← EXACT subject yang diterima
    "verification code",
    "Your verification code",
    "Your code",
    "One-time code",
    "Sign in code",
    "Gemini verification",
    "sign in",
]

# ── Sender yang diketahui dari Gemini Enterprise ──────────────────────────
KNOWN_SENDERS = [
    "noreply-googlecloud@google.com",         # ← sender EXACT dari Gemini Enterprise
    "noreply@google.com",
    "no-reply@accounts.google.com",
    "googlecloud",                            # partial match untuk query Gmail
]

IGNORE_SUBJECTS = [
    "welcome", "newsletter", "get started", "subscription",
]


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

    def _authenticate(self):
        creds = None
        if os.path.exists(self.token_path):
            with open(self.token_path, "rb") as f:
                creds = pickle.load(f)
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                except Exception:
                    creds = None
            if not creds:
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

    def _extract_otp_code(self, msg_id: str) -> Optional[str]:
        """Ambil OTP dari body email."""
        try:
            msg  = self._svc().users().messages().get(userId="me", id=msg_id, format="full").execute()

            # Log subject untuk debug
            headers = {h["name"].lower(): h["value"] for h in msg.get("payload", {}).get("headers", [])}
            self._log(f"   📧 From   : {headers.get('from', '-')}", "WARNING")
            self._log(f"   📧 Subject: {headers.get('subject', '-')}", "WARNING")

            # Skip email yang harus diabaikan
            subj_lower = headers.get("subject", "").lower()
            for ign in IGNORE_SUBJECTS:
                if ign in subj_lower:
                    self._log(f"   ⏭️  Diabaikan (subject: {ign})", "WARNING")
                    return None

            body = self._decode_body(msg["payload"])

        except Exception as e:
            self._log(f"   ⚠️  Gagal ambil email: {e}", "WARNING")
            return None

        # Log cuplikan body untuk debug
        snippet = body[:300].replace("\n", " ").strip()
        self._log(f"   📌 Body: {snippet}", "WARNING")

        # ── Pattern OTP ─────────────────────────────────────────────────────
        for pattern in [
            r'verification\s+code[:\s\n]+([0-9]{4,8})',
            r'Your\s+(?:verification\s+)?code\s+is[:\s]+([0-9]{4,8})',
            r'OTP[:\s]+([0-9]{4,8})',
            r'code[:\s]+([0-9]{4,8})',
            r'\b([0-9]{6})\b',      # 6 digit (paling umum)
            r'\b([0-9]{4})\b',      # 4 digit fallback
        ]:
            m = re.search(pattern, body, re.IGNORECASE)
            if m:
                code = m.group(1)
                self._log(f"   ✅ OTP pattern match: '{code}'", "WARNING")
                return code

        self._log("   ⚠️  Tidak ada angka OTP di body email", "WARNING")
        return None

    def _search_messages(self, query: str, max_results: int = 10) -> list:
        try:
            result = self._svc().users().messages().list(
                userId="me", q=query, maxResults=max_results
            ).execute()
            return [m["id"] for m in result.get("messages", [])]
        except Exception:
            return []

    def mark_as_read(self, msg_id: str):
        try:
            self._svc().users().messages().modify(
                userId="me", id=msg_id, body={"removeLabelIds": ["UNREAD"]}
            ).execute()
        except Exception:
            pass

    def move_from_spam(self, msg_id: str):
        """Pindahkan email dari SPAM ke INBOX."""
        try:
            self._svc().users().messages().modify(
                userId="me",
                id=msg_id,
                body={
                    "removeLabelIds": ["SPAM"],
                    "addLabelIds":    ["INBOX"],
                }
            ).execute()
            self._log("📥 Email dipindahkan dari SPAM → INBOX", "WARNING")
        except Exception as e:
            self._log(f"⚠️  Gagal pindah dari spam: {e}", "WARNING")

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

        ts_str    = datetime.datetime.fromtimestamp(after_timestamp).strftime("%H:%M:%S") if after_timestamp else "N/A"
        ts_filter = f" after:{max(0, after_timestamp - 60)}" if after_timestamp else ""

        # ── Build queries: prioritas dari yang paling spesifik ────────────────────
        queries = []

        # ── PRIORITAS 1: Subject EXACT "Gemini Enterprise verification code" ───
        queries.append(("INBOX exact-subject",
                        f'subject:"Gemini Enterprise verification code"{ts_filter}'))
        queries.append(("SPAM exact-subject",
                        f'in:spam subject:"Gemini Enterprise verification code"{ts_filter}'))

        # ── PRIORITAS 2: Sender exact noreply-googlecloud ────────────────────
        queries.append(("INBOX googlecloud-sender",
                        f"from:noreply-googlecloud@google.com{ts_filter}"))
        queries.append(("SPAM googlecloud-sender",
                        f"in:spam from:noreply-googlecloud@google.com{ts_filter}"))

        # ── PRIORITAS 3: by mask email (semua folder) ──────────────────────
        if mask_email:
            queries.append(("INBOX+SPAM by mask",
                            f"to:{mask_email}{ts_filter}"))
            queries.append(("SPAM by mask",
                            f"in:spam to:{mask_email}{ts_filter}"))

        # ── PRIORITAS 4: Subject keywords lain ────────────────────────────
        for subj in OTP_SUBJECTS[1:]:  # skip index 0 (sudah di atas)
            queries.append((f"subj:{subj[:20]}",
                            f'subject:"{subj}"{ts_filter}'))
            queries.append((f"spam-subj:{subj[:20]}",
                            f'in:spam subject:"{subj}"{ts_filter}'))

        # ── FALLBACK: broad search di spam ────────────────────────────────
        queries.append(("fallback:spam-googlecloud",
                        f"in:spam from:googlecloud{ts_filter}"))
        queries.append(("fallback:spam-google",
                        f"in:spam from:google.com{ts_filter}"))
        if mask_email:
            queries.append(("fallback:mask-no-ts", f"to:{mask_email}"))

        self._log(
            f"📬 Polling Gmail | cutoff: {ts_str} | {len(queries)} strategi | INBOX+SPAM",
            "WARNING"
        )

        start    = time.time()
        seen_ids = set()

        while time.time() - start < timeout:
            for label, q in queries:
                ids = self._search_messages(q)
                for mid in ids:
                    if mid in seen_ids:
                        continue
                    seen_ids.add(mid)

                    # Filter timestamp
                    if after_timestamp:
                        msg_ts = self._get_message_timestamp(mid)
                        if 0 < msg_ts < (after_timestamp - 60):
                            continue

                    self._log(f"   🔎 [{label}] id={mid[:8]}...")
                    otp = self._extract_otp_code(mid)
                    if otp:
                        self.mark_as_read(mid)
                        if "spam" in label.lower() or "spam" in q.lower():
                            self.move_from_spam(mid)
                        self._log(f"✅ OTP ditemukan: {otp}", "SUCCESS")
                        return otp

            elapsed = int(time.time() - start)
            self._log(f"⏳ Polling... {elapsed}s/{timeout}s")
            time.sleep(interval)

        raise TimeoutError(
            f"❌ OTP timeout {timeout}s — email tidak ditemukan di Inbox maupun Spam."
        )
