"""
firefox_relay.py  —  Firefox Relay API v1 wrapper

Dapatkan API Key di: https://relay.firefox.com/accounts/profile/
Scroll ke bawah → bagian API Key → Copy.
Simpan key di: relay_config.json  (auto-buat oleh save_key)
"""
import json
import os
import requests


class FirefoxRelay:
    """
    Buat / hapus email mask via Firefox Relay API.
    Digunakan oleh GeminiEnterpriseProcessor agar tiap login
    menggunakan alamat email mask yang BARU sehingga tidak
    terdeteksi sebagai akun berulang oleh Google.
    """
    API_BASE = "https://relay.firefox.com/api/v1"

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.headers = {
            "Authorization": f"Token {api_key}",
            "Content-Type":  "application/json",
        }

    def create_mask(self, label: str = "gemini-veo") -> dict:
        """
        Buat email mask baru.
        Return dict berisi 'full_address' dan 'id'.
        """
        resp = requests.post(
            f"{self.API_BASE}/relayaddresses/",
            json={"enabled": True, "description": label},
            headers=self.headers,
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()

    def delete_mask(self, mask_id: int) -> bool:
        """Hapus email mask berdasarkan ID."""
        resp = requests.delete(
            f"{self.API_BASE}/relayaddresses/{mask_id}/",
            headers=self.headers,
            timeout=15,
        )
        return resp.status_code == 204

    def list_masks(self) -> list:
        """List semua email mask aktif."""
        resp = requests.get(
            f"{self.API_BASE}/relayaddresses/",
            headers=self.headers,
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()

    def test_connection(self) -> bool:
        """Uji koneksi API Key."""
        try:
            self.list_masks()
            return True
        except Exception:
            return False

    @staticmethod
    def save_key(base_dir: str, api_key: str):
        path = os.path.join(base_dir, "relay_config.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"api_key": api_key}, f, indent=2)

    @staticmethod
    def load_key(base_dir: str) -> str:
        path = os.path.join(base_dir, "relay_config.json")
        if not os.path.exists(path):
            return ""
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f).get("api_key", "")
        except Exception:
            return ""
