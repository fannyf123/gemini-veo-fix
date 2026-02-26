"""
gmail_otp.py  —  GmailOTPReader
Baca OTP dari Gmail secara otomatis via Google API.
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

OTP_SUBJECTS = [
    '"Your verification code"',
    '"Your code"',
    '"One-time code"',
    '"Sign in code"',
    '"Gemini verification"',
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
        try:
            msg  = self._svc().users().messages().get(userId="me", id=msg_id, format="full").execute()
            body = self._decode_body(msg["payload"])
        except Exception:
            return None
        for pattern in [
            r'Your\s+(?:verification\s+)?code\s+is[:\s]+([0-9]{4,8})',
            r'OTP[:\s]+([0-9]{4,8})',
            r'code[:\s]+([0-9]{4,8})',
            r'\b([0-9]{6})\b',
            r'\b([0-9]{4})\b',
        ]:
            m = re.search(pattern, body, re.IGNORECASE)
            if m:
                return m.group(1)
        return None

    def _search_messages(self, query: str, max_results: int = 5) -> list:
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

    def wait_for_otp(
        self,
        sender:          str                = "google.com",
        timeout:         int                = 120,
        interval:        int                = 5,
        log_callback:    Optional[Callable] = None,
        mask_email:      str                = None,
        after_timestamp: int                = 0,
    ) -> str:
        self._log_cb = log_callback
        self._svc()

        ts_str   = datetime.datetime.fromtimestamp(after_timestamp).strftime("%H:%M:%S") if after_timestamp else "N/A"
        queries  = []
        ts_filter = f" after:{max(0, after_timestamp - 60)}" if after_timestamp else ""

        if mask_email:
            queries.append(f"to:{mask_email} is:unread{ts_filter}")
        queries.append(f"from:{sender} is:unread{ts_filter}")
        for subj in OTP_SUBJECTS:
            queries.append(f"subject:{subj} is:unread{ts_filter}")

        self._log(f"📬 Polling Gmail | cutoff: {ts_str} | {len(queries)} strategi")

        start    = time.time()
        seen_ids = set()

        while time.time() - start < timeout:
            for q in queries:
                ids = self._search_messages(q)
                for mid in ids:
                    if mid in seen_ids:
                        continue
                    seen_ids.add(mid)
                    if after_timestamp:
                        msg_ts = self._get_message_timestamp(mid)
                        if 0 < msg_ts < (after_timestamp - 60):
                            continue
                    otp = self._extract_otp_code(mid)
                    if otp:
                        self.mark_as_read(mid)
                        self._log(f"✅ OTP ditemukan: {otp}", "SUCCESS")
                        return otp
            elapsed = int(time.time() - start)
            self._log(f"⏳ Polling... {elapsed}s/{timeout}s")
            time.sleep(interval)

        raise TimeoutError(f"❌ OTP timeout {timeout}s — pastikan Firefox Relay meneruskan ke Gmail.")
