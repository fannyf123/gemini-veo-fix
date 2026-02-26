"""
main.py  —  Gemini Veo Tester (CLI mode)

Cara pakai:
    1. Isi config.json:
       - mask_email     : email mask Firefox Relay yang sudah ada
       - relay_api_key  : (opsional) hanya untuk cek koneksi
    2. Isi prompts.txt (satu prompt per baris)
    3. Letakkan credentials.json (Gmail API) di root folder
    4. Jalankan: python main.py  atau  Launcher.bat
    5. Pertama kali: login Gmail OAuth via browser (sekali saja)
    6. Video tersimpan di OUTPUT_GEMINI/

Perubahan:
    - Tidak lagi membuat email mask BARU setiap run.
      Pakai mask_email yang sudah ada dari config.json.
    - OTP dicari di INBOX + SPAM otomatis.
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
        "mask_email":          "",       # ← ISI INI: email mask Firefox Relay yang sudah ada
        "relay_api_key":       "",       # opsional, tidak dipakai untuk generate
        "output_dir":          OUTPUT_DIR,
        "headless":            False,
        "max_workers":         1,
        "batch_stagger_delay": 15,
    }
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            default.update(json.load(f))
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

    # ── Validasi mask_email ─────────────────────────────────────────────────
    mask_email = cfg.get("mask_email", "").strip()
    if not mask_email:
        print("[ERROR] mask_email kosong di config.json!")
        print()
        print("  Isi field mask_email dengan email mask Firefox Relay yang sudah ada.")
        print("  Contoh:")
        print('  {"mask_email": "4ngi4l0ra@mozmail.com", ...}')
        print()
        print("  Cara lihat mask yang sudah ada:")
        print("    Buka https://relay.firefox.com/accounts/masks/")
        print()
        sys.exit(1)

    os.makedirs(cfg.get("output_dir") or OUTPUT_DIR, exist_ok=True)

    print(f"[INF] Total prompt  : {len(prompts)}")
    print(f"[INF] Max workers   : {cfg['max_workers']}")
    print(f"[INF] Headless      : {cfg['headless']}")
    print(f"[INF] Mask email    : {mask_email}")
    print(f"[INF] Output dir    : {cfg.get('output_dir') or OUTPUT_DIR}")
    print()

    done_event = threading.Event()
    results    = {}

    def on_finish(ok, msg, paths):
        results["ok"]    = ok
        results["msg"]   = msg
        results["paths"] = paths
        done_event.set()

    # ── Single prompt mode ───────────────────────────────────────────────
    if len(prompts) == 1:
        from App.gemini_enterprise import GeminiEnterpriseProcessor

        proc = GeminiEnterpriseProcessor(
            base_dir          = _ROOT,
            prompt            = prompts[0],
            mask_email        = mask_email,           # ← pakai dari config
            output_dir        = cfg.get("output_dir") or OUTPUT_DIR,
            config            = cfg,
            log_callback      = log,
            progress_callback = lambda pct, msg: print(f"[{pct:3d}%] {msg}", flush=True),
            finished_callback = lambda ok, msg, path: on_finish(ok, msg, path),
        )
        proc.start()
        done_event.wait()

    # ── Batch mode (multi prompt) ─────────────────────────────────────────
    else:
        from App.gemini_batch import GeminiBatchProcessor

        # Batch juga pakai mask yang sama (semua prompt dari akun yang sama)
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

    print()
    if results.get("ok"):
        print(f"[OK]  SELESAI: {results['msg']}")
    else:
        print(f"[ERR] GAGAL  : {results.get('msg', 'Unknown error')}")
    print()


if __name__ == "__main__":
    main()
