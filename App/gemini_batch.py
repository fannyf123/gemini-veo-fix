"""
gemini_batch.py

Wrapper untuk batch processing:
- Load prompts dari file .txt
- Jalankan GeminiEnterpriseProcessor
- Callback untuk UI update
"""
import os
from typing import Callable, Optional

from App.gemini_enterprise import GeminiEnterpriseProcessor


def load_prompts(filepath: str) -> list:
    """Load prompts dari file txt, satu prompt per baris, skip baris kosong."""
    prompts = []
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    prompts.append(line)
    except Exception as e:
        raise IOError(f"Cannot read prompts file: {e}")
    return prompts


def run_batch(
    base_dir:          str,
    prompts_file:      str,
    output_dir:        str,
    config:            dict,
    log_callback:      Optional[Callable] = None,
    progress_callback: Optional[Callable] = None,
    finished_callback: Optional[Callable] = None,
) -> GeminiEnterpriseProcessor:
    """
    Load prompts dan jalankan processor.
    Return thread object (sudah di-start).
    """
    prompts = load_prompts(prompts_file)
    if log_callback:
        log_callback(f"Loaded {len(prompts)} prompts from file")

    proc = GeminiEnterpriseProcessor(
        base_dir          = base_dir,
        prompts           = prompts,
        output_dir        = output_dir,
        config            = config,
        log_callback      = log_callback,
        progress_callback = progress_callback,
        finished_callback = finished_callback,
    )
    proc.start()
    return proc
