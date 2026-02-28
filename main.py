"""
main.py  —  Gemini Veo Tester (CLI mode)

Cara pakai:
    1. Isi prompts.txt (satu prompt per baris)
    2. Jalankan: python main.py  atau  Launcher.bat
    3. Program otomatis:
       - Buat temp email via mailticking.com
       - Register akun Gemini Business baru
       - Generate video untuk setiap prompt
       - Auto switch akun jika rate limit
    4. Video tersimpan di OUTPUT_GEMINI/
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
        "output_dir": OUTPUT_DIR,
        "headless":   False,
        "delay":      5,
        "retry":      1,
    }
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            for old_key in [
                "relay_api_key", "mask_email", "fixed_mask_email",
                "max_workers", "batch_stagger_delay",
                "gmail_credentials", "token_path",
            ]:
                data.pop(old_key, None)
            default.update(data)
        except json.JSONDecodeError:
            print("[WRN] config.json tidak valid, pakai default.")
    return default


def load_prompts() -> list:
    if not os.path.exists(PROMPTS_PATH):
        print(f"[ERR] prompts.txt tidak ditemukan di: {PROMPTS_PATH}")
        sys.exit(1)
    with open(PROMPTS_PATH, "r", encoding="utf-8") as f:
        lines = [l.strip() for l in f if l.strip()]
    if not lines:
        print("[ERR] prompts.txt kosong!")
        sys.exit(1)
    return lines


def log(msg: str, level: str = "INFO"):
    prefix = {
        "INFO":    "[INF]",
        "SUCCESS": "[OK] ",
        "WARNING": "[WRN]",
        "ERROR":   "[ERR]",
    }
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

    output_dir = cfg.get("output_dir") or OUTPUT_DIR
    os.makedirs(output_dir, exist_ok=True)

    print(f"[INF] Total prompts : {len(prompts)}")
    print(f"[INF] Output dir    : {output_dir}")
    print(f"[INF] Headless      : {cfg['headless']}")
    print(f"[INF] Delay         : {cfg['delay']}s")
    print(f"[INF] Retry         : {cfg['retry']}x")
    print(f"[INF] Email source  : mailticking.com (auto)")
    print()

    done_event = threading.Event()
    results    = {}

    def on_finish(ok: bool, msg: str, path: str = ""):
        results["ok"]   = ok
        results["msg"]  = msg
        results["path"] = path
        done_event.set()

    from App.gemini_enterprise import GeminiEnterpriseProcessor

    proc = GeminiEnterpriseProcessor(
        base_dir          = _ROOT,
        prompts           = prompts,
        output_dir        = output_dir,
        config            = cfg,
        log_callback      = log,
        progress_callback = lambda pct, msg: print(f"[{pct:3d}%] {msg}", flush=True),
        finished_callback = on_finish,
    )
    proc.start()

    done_event.wait()

    print()
    if results.get("ok"):
        print(f"[OK]  SELESAI: {results['msg']}")
    else:
        print(f"[ERR] GAGAL  : {results.get('msg', 'Unknown error')}")
    print()


if __name__ == "__main__":
    main()
