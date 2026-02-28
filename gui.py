"""
gui.py  —  Gemini Veo Tester (GUI mode)

Modern CustomTkinter GUI with:
  - Sidebar layout for settings
  - Live log viewer with colored tags
  - Progress bar
  - Prompts editor
  - Settings (output dir, delay, retry, headless, stealth)
  - Start / Stop controls
"""

import os
import sys
import json
import threading
import tkinter as tk
from tkinter import filedialog, messagebox

# Fallback for log coloring using standard tk Text inside CTk frame
import customtkinter as ctk

_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

CONFIG_PATH  = os.path.join(_ROOT, "config.json")
PROMPTS_PATH = os.path.join(_ROOT, "prompts.txt")
OUTPUT_DIR   = os.path.join(_ROOT, "OUTPUT_GEMINI")

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

class GeminiVeoGUI(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Gemini Veo Tester")
        self.geometry("1000x700")
        self.minsize(800, 600)

        # configure grid layout (1 row, 2 columns)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.processor = None
        self._running = False

        self._build_sidebar()
        self._build_main_area()

        self._load_config()
        self._load_prompts()

        # Handle window close
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_sidebar(self):
        self.sidebar_frame = ctk.CTkFrame(self, width=280, corner_radius=0)
        self.sidebar_frame.grid(row=0, column=0, sticky="nsew")
        self.sidebar_frame.grid_rowconfigure(8, weight=1) # Spacer

        # Title
        self.logo_label = ctk.CTkLabel(self.sidebar_frame, text="Gemini Veo Tester", font=ctk.CTkFont(size=20, weight="bold"))
        self.logo_label.grid(row=0, column=0, padx=20, pady=(20, 10))
        self.subtitle_label = ctk.CTkLabel(self.sidebar_frame, text="business.gemini.google", font=ctk.CTkFont(size=12), text_color="gray")
        self.subtitle_label.grid(row=1, column=0, padx=20, pady=(0, 20))

        # Output Dir
        self.out_label = ctk.CTkLabel(self.sidebar_frame, text="Output Directory:", anchor="w")
        self.out_label.grid(row=2, column=0, padx=20, pady=(10, 0), sticky="w")
        
        self.output_var = ctk.StringVar(value=OUTPUT_DIR)
        self.out_entry = ctk.CTkEntry(self.sidebar_frame, textvariable=self.output_var, width=240)
        self.out_entry.grid(row=3, column=0, padx=20, pady=(5, 5))
        
        self.browse_btn = ctk.CTkButton(self.sidebar_frame, text="Browse", command=self._browse_output, fg_color="transparent", border_width=1, text_color=("gray10", "#DCE4EE"))
        self.browse_btn.grid(row=4, column=0, padx=20, pady=(0, 20))

        # Settings
        self.settings_label = ctk.CTkLabel(self.sidebar_frame, text="Automation Settings:", font=ctk.CTkFont(weight="bold"), anchor="w")
        self.settings_label.grid(row=5, column=0, padx=20, pady=(10, 10), sticky="w")

        # Delay & Retry layout
        self.delay_retry_frame = ctk.CTkFrame(self.sidebar_frame, fg_color="transparent")
        self.delay_retry_frame.grid(row=6, column=0, padx=20, pady=5, sticky="ew")
        
        self.delay_var = ctk.StringVar(value="5")
        ctk.CTkLabel(self.delay_retry_frame, text="Delay (s):").pack(side="left")
        self.delay_entry = ctk.CTkEntry(self.delay_retry_frame, textvariable=self.delay_var, width=50)
        self.delay_entry.pack(side="left", padx=(5, 15))

        self.retry_var = ctk.StringVar(value="1")
        ctk.CTkLabel(self.delay_retry_frame, text="Retry:").pack(side="left")
        self.retry_entry = ctk.CTkEntry(self.delay_retry_frame, textvariable=self.retry_var, width=50)
        self.retry_entry.pack(side="left", padx=(5, 0))

        # Switches
        self.switches_frame = ctk.CTkFrame(self.sidebar_frame, fg_color="transparent")
        self.switches_frame.grid(row=7, column=0, padx=20, pady=15, sticky="ew")

        self.headless_var = ctk.BooleanVar(value=True)
        self.headless_switch = ctk.CTkSwitch(self.switches_frame, text="Headless Chrome", variable=self.headless_var)
        self.headless_switch.pack(anchor="w", pady=5)

        self.stealth_var = ctk.BooleanVar(value=True)
        self.stealth_switch = ctk.CTkSwitch(self.switches_frame, text="Stealth Mode", variable=self.stealth_var)
        self.stealth_switch.pack(anchor="w", pady=5)

        # Start / Stop buttons at bottom of sidebar
        self.start_btn = ctk.CTkButton(self.sidebar_frame, text="▶ START", fg_color="#2FA572", hover_color="#106A43", font=ctk.CTkFont(weight="bold", size=14), height=40, command=self._start)
        self.start_btn.grid(row=9, column=0, padx=20, pady=(20, 10), sticky="ew")

        self.stop_btn = ctk.CTkButton(self.sidebar_frame, text="■ STOP", fg_color="#C23B22", hover_color="#8F2515", font=ctk.CTkFont(weight="bold", size=14), height=40, state="disabled", command=self._stop)
        self.stop_btn.grid(row=10, column=0, padx=20, pady=(0, 20), sticky="ew")

    def _build_main_area(self):
        self.main_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.main_frame.grid(row=0, column=1, sticky="nsew", padx=20, pady=20)
        self.main_frame.grid_rowconfigure(2, weight=1) # Log area takes remaining space
        self.main_frame.grid_columnconfigure(0, weight=1)

        # Prompts Section
        self.prompt_header_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.prompt_header_frame.grid(row=0, column=0, sticky="ew", pady=(0, 5))
        self.prompt_header_frame.grid_columnconfigure(1, weight=1)
        
        ctk.CTkLabel(self.prompt_header_frame, text="📝 Prompts (One per line):", font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, sticky="w")
        
        self.prompt_count_var = ctk.StringVar(value="0 prompts")
        ctk.CTkLabel(self.prompt_header_frame, textvariable=self.prompt_count_var, text_color="gray").grid(row=0, column=1, sticky="e")

        self.prompts_text = ctk.CTkTextbox(self.main_frame, height=120, font=ctk.CTkFont(family="Consolas", size=12))
        self.prompts_text.grid(row=1, column=0, sticky="ew", pady=(0, 20))
        self.prompts_text.bind("<KeyRelease>", lambda e: self._update_prompt_count())

        # Progress Section
        self.progress_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.progress_frame.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        self.progress_frame.grid_columnconfigure(0, weight=1)

        self.progress_bar = ctk.CTkProgressBar(self.progress_frame, progress_color="#2FA572")
        self.progress_bar.grid(row=0, column=0, sticky="ew", pady=(0, 5))
        self.progress_bar.set(0)

        self.status_var = ctk.StringVar(value="Ready")
        self.status_label = ctk.CTkLabel(self.progress_frame, textvariable=self.status_var, font=ctk.CTkFont(size=12), text_color="gray")
        self.status_label.grid(row=1, column=0, sticky="w")

        # Log Viewer section (Using standard tk.Text for rich color tags)
        self.log_header = ctk.CTkLabel(self.main_frame, text="📋 Logs:", font=ctk.CTkFont(weight="bold"), anchor="w")
        self.log_header.grid(row=3, column=0, sticky="w", pady=(10, 5))

        # We wrap standard tk.Text inside a CTkFrame for styling
        self.log_bg = ctk.CTkFrame(self.main_frame)
        self.log_bg.grid(row=4, column=0, sticky="nsew")
        self.log_bg.grid_rowconfigure(0, weight=1)
        self.log_bg.grid_columnconfigure(0, weight=1)

        self.log_text = tk.Text(self.log_bg, bg="#1E1E1E", fg="#CCCCCC", font=("Consolas", 10), 
                                relief="flat", padx=10, pady=10, state="disabled", wrap="word", insertbackground="white")
        self.log_text.grid(row=0, column=0, sticky="nsew", padx=2, pady=2)
        
        # Scrollbar
        self.log_scroll = ctk.CTkScrollbar(self.log_bg, command=self.log_text.yview)
        self.log_scroll.grid(row=0, column=1, sticky="ns")
        self.log_text.configure(yscrollcommand=self.log_scroll.set)

        # Configure log color tags
        self.log_text.tag_configure("INFO", foreground="#CCCCCC")
        self.log_text.tag_configure("SUCCESS", foreground="#2FA572")
        self.log_text.tag_configure("WARNING", foreground="#ECA52D")
        self.log_text.tag_configure("ERROR", foreground="#E74C3C")
        self.log_text.tag_configure("SYSTEM", foreground="#3498DB")

    # ── Config load/save ──────────────────────────────────────────────────
    def _load_config(self):
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                self.output_var.set(cfg.get("output_dir", OUTPUT_DIR))
                self.delay_var.set(str(cfg.get("delay", 5)))
                self.retry_var.set(str(cfg.get("retry", 1)))
                self.headless_var.set(cfg.get("headless", True))
                self.stealth_var.set(cfg.get("stealth", True))
            except Exception:
                pass

    def _save_config(self) -> dict:
        cfg = {
            "output_dir": self.output_var.get(),
            "headless":   self.headless_var.get(),
            "delay":      int(self.delay_var.get() or 5),
            "retry":      int(self.retry_var.get() or 1),
            "stealth":    self.stealth_var.get(),
        }
        try:
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2)
        except Exception:
            pass
        return cfg

    # ── Prompts load/save ─────────────────────────────────────────────────
    def _load_prompts(self):
        if os.path.exists(PROMPTS_PATH):
            try:
                with open(PROMPTS_PATH, "r", encoding="utf-8") as f:
                    content = f.read()
                self.prompts_text.delete("1.0", "end")
                self.prompts_text.insert("1.0", content.strip())
                self._update_prompt_count()
            except Exception:
                pass

    def _save_prompts(self) -> list:
        content = self.prompts_text.get("1.0", "end").strip()
        lines = [l.strip() for l in content.splitlines() if l.strip()]
        try:
            with open(PROMPTS_PATH, "w", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")
        except Exception:
            pass
        return lines

    def _update_prompt_count(self):
        content = self.prompts_text.get("1.0", "end").strip()
        count = len([l for l in content.splitlines() if l.strip()])
        self.prompt_count_var.set(f"{count} prompt{'s' if count != 1 else ''}")

    # ── Helpers ───────────────────────────────────────────────────────────
    def _browse_output(self):
        path = filedialog.askdirectory(initialdir=self.output_var.get())
        if path:
            self.output_var.set(path)

    def _append_log(self, msg: str, level: str = "INFO"):
        """Thread-safe log append."""
        def _do():
            self.log_text.configure(state="normal")
            prefix = {"INFO": "[INF]", "SUCCESS": "[OK] ",
                      "WARNING": "[WRN]", "ERROR": "[ERR]",
                      "SYSTEM": "[SYS]"}
            tag = level if level in prefix else "INFO"
            self.log_text.insert("end", f"{prefix.get(level, '[INF]')} {msg}\n", tag)
            self.log_text.see("end")
            self.log_text.configure(state="disabled")
        self.after(0, _do)

    def _update_progress(self, pct: int, msg: str):
        """Thread-safe progress update."""
        def _do():
            self.progress_bar.set(pct / 100.0)
            self.status_var.set(msg)
        self.after(0, _do)

    def _set_running(self, running: bool):
        """Thread-safe button state update."""
        def _do():
            if running:
                self.start_btn.configure(state="disabled")
                self.stop_btn.configure(state="normal")
                self.status_var.set("Running...")
            else:
                self.start_btn.configure(state="normal")
                self.stop_btn.configure(state="disabled")
        self.after(0, _do)

    # ── Start / Stop ──────────────────────────────────────────────────────
    def _start(self):
        prompts = self._save_prompts()
        if not prompts:
            messagebox.showwarning("No Prompts", "Please add at least one prompt.")
            return

        cfg = self._save_config()
        output_dir = cfg.get("output_dir", OUTPUT_DIR)
        os.makedirs(output_dir, exist_ok=True)

        # Clear log
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")
        self.progress_bar.set(0)

        self._append_log(f"Starting with {len(prompts)} prompts", "SYSTEM")
        self._append_log(f"Output: {output_dir}", "SYSTEM")
        self._append_log(f"Headless: {cfg['headless']} | Stealth: {cfg['stealth']} | "
                         f"Delay: {cfg['delay']}s | Retry: {cfg['retry']}x", "SYSTEM")

        self._running = True
        self._set_running(True)

        from App.gemini_enterprise import GeminiEnterpriseProcessor

        self.processor = GeminiEnterpriseProcessor(
            base_dir          = _ROOT,
            prompts           = prompts,
            output_dir        = output_dir,
            config            = cfg,
            log_callback      = self._append_log,
            progress_callback = self._update_progress,
            finished_callback = self._on_finish,
        )
        self.processor.start()

    def _stop(self):
        if self.processor:
            self.processor.cancel()
            self._append_log("Cancelling...", "WARNING")

    def _on_finish(self, ok: bool, msg: str, path: str = ""):
        self._running = False
        self._set_running(False)
        if ok:
            self._append_log(f"DONE: {msg}", "SUCCESS")
            self._update_progress(100, "Completed!")
        else:
            self._append_log(f"STOPPED: {msg}", "ERROR")
            self.status_var.set("Stopped")
        self.after(0, lambda: None)  

    def _on_close(self):
        if self._running:
            if not messagebox.askyesno("Confirm Exit", "Automation is running. Stop and exit?"):
                return
            if self.processor:
                self.processor.cancel()
        self.destroy()

if __name__ == "__main__":
    app = GeminiVeoGUI()
    app.mainloop()
