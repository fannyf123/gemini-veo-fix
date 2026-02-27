"""
_stealth_compat.py  —  Compatibility shim (tidak dipakai lagi sejak ganti ke UC)

Dibiarkan agar tidak breaking import yang mungkin masih ada di file lain.
"""

STEALTH_VERSION = "undetected-chromedriver"


def apply_stealth(page_or_driver):
    """No-op: UC sudah handle stealth secara built-in."""
    return True


def stealth_info():
    return "undetected-chromedriver (built-in stealth)"
