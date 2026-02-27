"""
main.py  —  Gemini Veo Tester (CLI mode)

Cara pakai:
    1. Isi config.json:
       - relay_api_key  : API key Firefox Relay (wajib)
         Dapatkan di: https://relay.firefox.com/accounts/profile/
    2. Isi prompts.txt (satu prompt per baris)
    3. Letakkan credentials.json (Gmail API) di root folder
    4. Jalankan: python main.py  atau  Launcher.bat
    5. Pertama kali: login Gmail OAuth via browser (sekali saja)
    6. Video tersimpan di OUTPUT_GEMINI/

Beda dengan versi lama:
    - TIDAK PERLU isi mask_email manual di config.json
    - Mask email BARU otomatis dibuat tiap run via Firefox Relay API
    - Mask lama dihapus otomatis setelah run selesai
"""

import os
import sys
import json
import threading

_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

CONFIG_PATH  = os.path.join(_ROOT, "config.json")
PROMPTS_PATH = os.path.join(_ROOT, "prompts.txt")
OUTPUT_DIR   = os.path.join(_ROOT, "OUTPUT_GEMINI")


def load_config() -> dict:
    default = {
        "relay_api_key":       "",       # ← WAJIB: API key Firefox Relay
        "output_dir":          OUTPUT_DIR,
        "headless":            False,
        "max_workers":         1,
        "batch_stagger_delay": 15,
    }
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            # Migrasi: jika masih ada mask_email statis, abaikan saja
            data.pop("mask_email", None)
            default.update(data)
    return default


def load_prompts() -> list:
    if not os.path.exists(PROMPTS_PATH):
        print(f"[ERROR] prompts.txt tidak ditemukan di: {PROMPTS_PATH}")
        sys.exit(1)
    with open(PROMPTS_PATH, "r", encoding="utf-8") as f:
        lines = [l.strip() for l in f if l.strip()]
    if not lines:
        print("[ERROR] prompts.txt kosong!")
        sys.exit(1)
    return lines


def log(msg: str, level: str = "INFO"):
    prefix = {"INFO": "[INF]", "SUCCESS": "[OK] ", "WARNING": "[WRN]", "ERROR": "[ERR]"}
    print(f"{prefix.get(level, '[INF]')} {msg}", flush=True)


def main():
    print()
    print("  ============================================")
    print("    Gemini Veo Tester")
    print("    business.gemini.google automation")
    print("  ============================================")
    print()

    cfg     = load_config()
    prompts = load_prompts()

    # ── Validasi relay_api_key ────────────────────────────────────────────────
    relay_api_key = cfg.get("relay_api_key", "").strip()
    if not relay_api_key:
        print()
        print("[ERROR] relay_api_key kosong di config.json!")
        print()
        print("  Dapatkan API Key di:")
        print("    https://relay.firefox.com/accounts/profile/")
        print("    Scroll bawah → 'API Key' → Copy")
        print()
        print("  Lalu isi di config.json:")
        print('  {"relay_api_key": "PASTE_KEY_DI_SINI", ...}')
        print()
        sys.exit(1)

    # ── Test koneksi Relay + generate mask baru ─────────────────────────────
    from App.firefox_relay import FirefoxRelay
    relay = FirefoxRelay(relay_api_key)

    log("Menguji koneksi Firefox Relay...")
    if not relay.test_connection():
        print()
        print("[ERROR] Firefox Relay API Key tidak valid atau gagal konek!")
        print("        Periksa kembali key-nya di: https://relay.firefox.com/accounts/profile/")
        sys.exit(1)
    log("Firefox Relay OK", "SUCCESS")

    # Generate fresh email mask
    log("Membuat email mask baru...")
    import time
    try:
        mask_result = relay.create_mask(label=f"gemini-veo-{int(time.time())}")
        mask_email  = mask_result.get("full_address", "")
        mask_id     = mask_result.get("id")
        if not mask_email:
            raise ValueError("full_address kosong dari response Relay")
        log(f"Mask baru: {mask_email} (id={mask_id})", "SUCCESS")
    except Exception as e:
        print(f"[ERROR] Gagal buat mask baru: {e}")
        sys.exit(1)

    os.makedirs(cfg.get("output_dir") or OUTPUT_DIR, exist_ok=True)

    print()
    print(f"[INF] Total prompt  : {len(prompts)}")
    print(f"[INF] Max workers   : {cfg['max_workers']}")
    print(f"[INF] Headless      : {cfg['headless']}")
    print(f"[INF] Mask email    : {mask_email}  (fresh, auto-delete setelah selesai)")
    print(f"[INF] Output dir    : {cfg.get('output_dir') or OUTPUT_DIR}")
    print()

    done_event = threading.Event()
    results    = {}

    def on_finish(ok, msg, path):
        results["ok"]   = ok
        results["msg"]  = msg
        results["path"] = path
        done_event.set()

    # ── Single prompt mode ─────────────────────────────────────────────
    if len(prompts) == 1:
        from App.gemini_enterprise import GeminiEnterpriseProcessor

        proc = GeminiEnterpriseProcessor(
            base_dir          = _ROOT,
            prompt            = prompts[0],
            mask_email        = mask_email,       # ← mask baru, bukan dari config
            output_dir        = cfg.get("output_dir") or OUTPUT_DIR,
            config            = cfg,
            log_callback      = log,
            progress_callback = lambda pct, msg: print(f"[{pct:3d}%] {msg}", flush=True),
            finished_callback = lambda ok, msg, path: on_finish(ok, msg, path),
        )
        proc.start()
        done_event.wait()

    # ── Batch mode (multi prompt) ───────────────────────────────────────
    else:
        from App.gemini_batch import GeminiBatchProcessor

        # Simpan mask_email ke config agar batch processor bisa pakai
        cfg["fixed_mask_email"] = mask_email

        batch = GeminiBatchProcessor(
            base_dir          = _ROOT,
            prompts           = prompts,
            config            = cfg,
            log_callback      = log,
            progress_callback = lambda pct, msg: print(f"[{pct:3d}%] {msg}", flush=True),
            finished_callback = lambda ok, msg, paths: on_finish(ok, msg, paths),
        )
        batch.start()
        done_event.wait()

    # ── Cleanup mask setelah selesai ──────────────────────────────────────
    if mask_id:
        try:
            ok_del = relay.delete_mask(mask_id)
            if ok_del:
                log(f"🗑️  Mask {mask_email} dihapus (cleanup)", "SUCCESS")
            else:
                log(f"⚠️  Gagal hapus mask {mask_id} (lakukan manual)", "WARNING")
        except Exception as e:
            log(f"⚠️  Error hapus mask: {e}", "WARNING")

    print()
    if results.get("ok"):
        print(f"[OK]  SELESAI: {results['msg']}")
    else:
        print(f"[ERR] GAGAL  : {results.get('msg', 'Unknown error')}")
    print()


if __name__ == "__main__":
    main()
