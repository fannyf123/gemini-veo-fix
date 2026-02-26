"""
gemini_batch.py  —  GeminiBatchProcessor
Jalankan banyak prompt generate video Gemini secara paralel.
Setiap worker pakai email mask baru dari Firefox Relay.
"""

import threading
import time
from typing import List, Callable, Optional

from App.gemini_enterprise import GeminiEnterpriseProcessor
from App.firefox_relay import FirefoxRelay

GEMINI_MAX_WORKERS = 3


class GeminiBatchProcessor(threading.Thread):

    def __init__(
        self,
        base_dir:          str,
        prompts:           List[str],
        config:            dict,
        log_callback:      Optional[Callable] = None,
        progress_callback: Optional[Callable] = None,
        finished_callback: Optional[Callable] = None,
    ):
        super().__init__(daemon=True)
        self.base_dir    = base_dir
        self.prompts     = prompts
        self.config      = config
        self.log_cb      = log_callback
        self.progress_cb = progress_callback
        self.finished_cb = finished_callback
        self._cancelled  = False
        self._workers    = []
        self._lock       = threading.Lock()
        self._results    = {}

    def _log(self, msg, level="INFO"):
        if self.log_cb: self.log_cb(msg, level)

    def _progress(self, pct, msg):
        if self.progress_cb: self.progress_cb(pct, msg)

    def cancel(self):
        self._cancelled = True
        for w in self._workers: w.cancel()

    def run(self):
        relay_key  = self.config.get("relay_api_key", "")
        output_dir = self.config.get("output_dir", "")
        stagger    = self.config.get("batch_stagger_delay", 15)
        max_w      = min(self.config.get("max_workers", GEMINI_MAX_WORKERS), GEMINI_MAX_WORKERS)
        relay      = FirefoxRelay(relay_key)
        total      = len(self.prompts)
        done       = [0]
        threads    = []
        semaphore  = threading.Semaphore(max_w)

        self._log("-" * 52)
        self._log(f"GEMINI BATCH START — {total} prompt(s) | max {max_w} worker", "SUCCESS")
        self._log("-" * 52)

        def run_single(idx, prompt):
            with semaphore:
                if self._cancelled: return
                try:
                    mask_data  = relay.create_mask(label=f"gemini-{idx+1}")
                    mask_email = mask_data["full_address"]
                    mask_id    = mask_data["id"]
                    self._log(f"[Worker {idx+1}] 📧 Mask: {mask_email}")
                except Exception as e:
                    self._log(f"[Worker {idx+1}] ❌ Gagal buat mask: {e}", "ERROR")
                    with self._lock: self._results[idx] = None
                    return

                def wlog(msg, level="INFO"):  self.log_cb(f"[W{idx+1}] {msg}", level)
                def wdone(ok, msg, path):
                    with self._lock:
                        self._results[idx] = path if ok else None
                        done[0] += 1
                    self.log_cb(f"[W{idx+1}] {'✅' if ok else '❌'} {msg}", "SUCCESS" if ok else "ERROR")
                    pct = int((done[0] / total) * 100)
                    self._progress(pct, f"{done[0]}/{total} video selesai")
                    # Hapus mask setelah selesai
                    try: relay.delete_mask(mask_id)
                    except: pass
                    if done[0] == total: self._finalize()

                proc = GeminiEnterpriseProcessor(
                    base_dir=self.base_dir, prompt=prompt,
                    mask_email=mask_email, output_dir=output_dir,
                    config=self.config, log_callback=wlog,
                    finished_callback=wdone,
                )
                with self._lock: self._workers.append(proc)
                proc.start()
                proc.join()

        for i, prompt in enumerate(self.prompts):
            if self._cancelled: break
            t = threading.Thread(target=run_single, args=(i, prompt), daemon=True)
            threads.append(t); t.start()
            if i < total - 1:
                self._log(f"⏳ Stagger {stagger}s...")
                time.sleep(stagger)

        for t in threads: t.join()

    def _finalize(self):
        ok_list = [p for p in self._results.values() if p]
        fail    = [i+1 for i, p in self._results.items() if not p]
        self._log("-" * 52)
        self._log(f"DONE — ✅ {len(ok_list)} berhasil | ❌ {len(fail)} gagal",
                  "SUCCESS" if not fail else "WARNING")
        for p in ok_list: self._log(f"   → {p}")
        self._log("-" * 52)
        if self.finished_cb:
            self.finished_cb(bool(ok_list), f"{len(ok_list)}/{len(self._results)} berhasil", ";".join(ok_list))
