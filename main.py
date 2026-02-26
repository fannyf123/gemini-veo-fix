"""
main.py  —  Gemini Veo Tester (CLI mode)

Cara pakai:
    1. Isi config.json dengan relay_api_key
    2. Isi prompts.txt (satu prompt per baris)
    3. Jalankan: python main.py
    4. Pertama kali: login Gmail OAuth via browser
    5. Video tersimpan di OUTPUT_GEMINI/
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
        "relay_api_key":       "",
        "output_dir":          OUTPUT_DIR,
        "headless":            False,     # False dulu untuk debug visual
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
        print("Buat file prompts.txt dan isi satu prompt per baris.")
        sys.exit(1)
    with open(PROMPTS_PATH, "r", encoding="utf-8") as f:
        lines = [l.strip() for l in f.readlines() if l.strip()]
    if not lines:
        print("[ERROR] prompts.txt kosong!")
        sys.exit(1)
    return lines


def log(msg: str, level: str = "INFO"):
    prefix = {"INFO": "[INF]", "SUCCESS": "[OK] ", "WARNING": "[WRN]", "ERROR": "[ERR]"}
    print(f"{prefix.get(level, '[INF]')} {msg}")


def main():
    print()
    print("  ============================================")
    print("    Gemini Veo Tester")
    print("    business.gemini.google automation")
    print("  ============================================")
    print()

    cfg     = load_config()
    prompts = load_prompts()

    if not cfg.get("relay_api_key"):
        print("[ERROR] relay_api_key kosong di config.json!")
        print("Isi dulu: https://relay.firefox.com/accounts/profile/")
        sys.exit(1)

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print(f"[INF] Total prompt  : {len(prompts)}")
    print(f"[INF] Max workers   : {cfg['max_workers']}")
    print(f"[INF] Headless      : {cfg['headless']}")
    print(f"[INF] Output dir    : {cfg['output_dir']}")
    print()

    done_event = threading.Event()
    results    = {}

    def on_finish(ok, msg, paths):
        results["ok"]    = ok
        results["msg"]   = msg
        results["paths"] = paths
        done_event.set()

    if len(prompts) == 1:
        # Single mode
        from App.gemini_enterprise import GeminiEnterpriseProcessor
        from App.firefox_relay import FirefoxRelay

        relay      = FirefoxRelay(cfg["relay_api_key"])
        mask_data  = relay.create_mask(label="gemini-tester")
        mask_email = mask_data["full_address"]
        mask_id    = mask_data["id"]
        log(f"Mask email: {mask_email}")

        proc = GeminiEnterpriseProcessor(
            base_dir          = _ROOT,
            prompt            = prompts[0],
            mask_email        = mask_email,
            output_dir        = cfg["output_dir"],
            config            = cfg,
            log_callback      = log,
            progress_callback = lambda pct, msg: print(f"[{pct:3d}%] {msg}"),
            finished_callback = lambda ok, msg, path: on_finish(ok, msg, path),
        )
        proc.start()
        done_event.wait()

        try: relay.delete_mask(mask_id)
        except: pass

    else:
        # Batch mode
        from App.gemini_batch import GeminiBatchProcessor

        batch = GeminiBatchProcessor(
            base_dir          = _ROOT,
            prompts           = prompts,
            config            = cfg,
            log_callback      = log,
            progress_callback = lambda pct, msg: print(f"[{pct:3d}%] {msg}"),
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
