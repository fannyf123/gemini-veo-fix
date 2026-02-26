import json
import os
import requests


class FirefoxRelay:
    """
    Firefox Relay API v1 wrapper.
    Dapatkan API Key di: https://relay.firefox.com/accounts/profile/
    Scroll ke bawah -> bagian API Key -> Copy.
    """
    API_BASE = "https://relay.firefox.com/api/v1"

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.headers = {
            "Authorization": f"Token {api_key}",
            "Content-Type":  "application/json",
        }

    def create_mask(self, label: str = "gemini-veo") -> dict:
        """Buat email mask baru. Return dict dengan 'full_address' dan 'id'."""
        resp = requests.post(
            f"{self.API_BASE}/relayaddresses/",
            json={"enabled": True, "description": label},
            headers=self.headers,
            timeout=15
        )
        resp.raise_for_status()
        return resp.json()

    def delete_mask(self, mask_id: int) -> bool:
        """Hapus email mask berdasarkan ID."""
        resp = requests.delete(
            f"{self.API_BASE}/relayaddresses/{mask_id}/",
            headers=self.headers,
            timeout=15
        )
        return resp.status_code == 204

    def list_masks(self) -> list:
        """List semua email mask aktif."""
        resp = requests.get(
            f"{self.API_BASE}/relayaddresses/",
            headers=self.headers,
            timeout=15
        )
        resp.raise_for_status()
        return resp.json()

    def test_connection(self) -> bool:
        try:
            self.list_masks()
            return True
        except Exception:
            return False
