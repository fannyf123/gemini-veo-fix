"""
_stealth_compat.py  —  Wrapper kompatibel untuk playwright-stealth v1 DAN v2

v1 (<=1.x): from playwright_stealth import stealth_sync  -> apply ke Page
v2 (>=2.x): from playwright_stealth import Stealth       -> apply ke Context

Usage:
    from App._stealth_compat import apply_stealth, STEALTH_VERSION
    apply_stealth(page_or_context)   # otomatis deteksi versi
"""

STEALTH_VERSION = None
_stealth_v1 = None
_stealth_v2 = None

try:
    # Coba v2 dulu (Stealth class)
    from playwright_stealth import Stealth as _StealthV2
    _stealth_v2   = _StealthV2()
    STEALTH_VERSION = 2
except (ImportError, AttributeError):
    pass

if STEALTH_VERSION is None:
    try:
        # Fallback v1 (stealth_sync)
        from playwright_stealth import stealth_sync as _stealth_v1_fn
        _stealth_v1   = _stealth_v1_fn
        STEALTH_VERSION = 1
    except (ImportError, AttributeError):
        pass


def apply_stealth(page) -> bool:
    """
    Terapkan stealth ke page.
    Return True jika berhasil, False jika playwright-stealth tidak tersedia.
    """
    if STEALTH_VERSION == 2 and _stealth_v2 is not None:
        try:
            # v2: apply ke context agar berlaku untuk semua page
            ctx = page.context
            _stealth_v2.apply_stealth_sync(ctx)
            return True
        except Exception:
            try:
                # Fallback: apply langsung ke page via init script
                for script in _stealth_v2.script_payload:
                    page.add_init_script(script)
                return True
            except Exception:
                return False

    elif STEALTH_VERSION == 1 and _stealth_v1 is not None:
        try:
            _stealth_v1(page)
            return True
        except Exception:
            return False

    return False


def stealth_info() -> str:
    if STEALTH_VERSION == 2:
        return "playwright-stealth v2 (Stealth class)"
    elif STEALTH_VERSION == 1:
        return "playwright-stealth v1 (stealth_sync)"
    else:
        return "TIDAK TERSEDIA"
