import sys
import os
import json
import datetime
import threading

_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QLineEdit, QSpinBox, QCheckBox,
    QTextEdit, QFileDialog, QProgressBar, QFrame, QScrollArea, QSizePolicy,
    QStackedWidget, QToolButton, QFormLayout, QMessageBox
)
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QFont, QTextCursor
import qtawesome as qta

from App.gemini_enterprise import GeminiEnterpriseProcessor

CONFIG_PATH = os.path.join(_PROJECT_ROOT, "config.json")
APP_NAME    = "Gemini Veo Tester"
APP_VER     = "3.0.0"

# ══════════════════════════════════════════════════════════════════════════════
#  COLOUR SYSTEM  —  GitHub-style palette
# ══════════════════════════════════════════════════════════════════════════════
THEMES = {
    "dark": {
        "bg":         "#0d1117",   "sidebar":    "#161b22",
        "surface":    "#161b22",   "surface2":   "#21262d",
        "input":      "#0d1117",   "border":     "#30363d",
        "primary":    "#1f6feb",   "primary_h":  "#58a6ff",
        "accent":     "#58a6ff",   "accent2":    "#3fb950",
        "text":       "#e6edf3",   "text_dim":   "#c9d1d9",
        "text_muted": "#8b949e",   "success":    "#3fb950",
        "warning":    "#e3b341",   "error":      "#f85149",
        "log_bg":     "#010409",
    },
    "light": {
        "bg":         "#ffffff",   "sidebar":    "#f6f8fa",
        "surface":    "#ffffff",   "surface2":   "#f6f8fa",
        "input":      "#f6f8fa",   "border":     "#d0d7de",
        "primary":    "#0969da",   "primary_h":  "#0550ae",
        "accent":     "#0969da",   "accent2":    "#1a7f37",
        "text":       "#1f2328",   "text_dim":   "#24292f",
        "text_muted": "#636c76",   "success":    "#1a7f37",
        "warning":    "#9a6700",   "error":      "#cf222e",
        "log_bg":     "#f6f8fa",
    },
}

C = dict(THEMES["dark"])

def build_stylesheet(c: dict) -> str:
    return f"""
* {{ font-family: 'Inter', 'Segoe UI', sans-serif; outline: none; }}
QMainWindow {{ background: {c['bg']}; }}
QWidget#MainContent {{ background: {c['bg']}; }}
QWidget#Sidebar {{
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
        stop:0 {c['sidebar']}, stop:1 {c['bg']});
    border-right: 1px solid {c['border']};
}}

/* Typography */
QLabel {{ color: {c['text_dim']}; font-size: 10pt; font-weight: 600; }}
QLabel#PageTitle {{ color: {c['text']}; font-size: 21pt; font-weight: 900; letter-spacing: -0.5px; }}
QLabel#SectionTitle {{ color: {c['text']}; font-size: 12pt; font-weight: 800; }}
QLabel#SubLabel {{ color: {c['text_muted']}; font-size: 9pt; font-weight: 600; }}
QLabel#HintLabel {{ color: {c['text_muted']}; font-size: 8pt; font-style: italic; font-weight: 500; }}
QLabel#BadgeLabel {{ background: {c['primary']}30; color: {c['primary_h']}; font-size: 9pt; font-weight: 900; padding: 5px 14px; border-radius: 20px; border: 1px solid {c['primary']}50; }}

/* Cards */
QFrame#Card {{ background: {c['surface']}; border: 1px solid {c['border']}; border-radius: 6px; }}
QFrame#AccentCard {{ background: {c['surface']}; border: 1px solid {c['border']}; border-left: 4px solid {c['primary']}; border-radius: 6px; }}
QFrame#SuccessCard {{ background: {c['surface']}; border: 1px solid {c['border']}; border-left: 4px solid {c['success']}; border-radius: 6px; }}
QFrame#WarnCard {{ background: {c['surface']}; border: 1px solid {c['border']}; border-left: 4px solid {c['warning']}; border-radius: 6px; }}

/* Buttons */
QPushButton {{ background: {c['surface2']}; border: 1px solid {c['border']}; border-radius: 6px; padding: 8px 18px; font-weight: 700; font-size: 10pt; color: {c['text']}; }}
QPushButton:hover  {{ background: {c['border']}; border-color: {c['primary']}; color: {c['text']}; }}
QPushButton:pressed{{ background: {c['bg']}; }}
QPushButton#PrimaryBtn {{ background: {c['primary']}; border: 1px solid {c['primary']}; color: #ffffff; font-size: 11pt; font-weight: 700; padding: 12px 28px; border-radius: 6px; }}
QPushButton#PrimaryBtn:hover {{ background: {c['primary_h']}; border-color: {c['primary_h']}; }}
QPushButton#DangerBtn {{ background: {c['error']}18; border: 1px solid {c['error']}80; color: {c['error']}; font-weight: 700; border-radius: 6px; }}
QPushButton#DangerBtn:hover {{ background: {c['error']}; color: #ffffff; }}
QPushButton#WarnBtn {{ background: {c['warning']}18; border: 1px solid {c['warning']}80; color: {c['warning']}; font-weight: 700; border-radius: 6px; }}
QPushButton#WarnBtn:hover {{ background: {c['warning']}; color: #0d1117; }}
QPushButton#GhostBtn {{ background: transparent; border: 1px solid {c['border']}; color: {c['text_dim']}; font-weight: 600; border-radius: 6px; }}
QPushButton#GhostBtn:hover {{ border-color: {c['primary']}; color: {c['primary_h']}; background: {c['primary']}10; }}

/* Sidebar Nav */
QToolButton#NavBtn {{ background: transparent; border: none; border-radius: 6px; padding: 12px 16px; font-size: 10pt; font-weight: 600; text-align: left; color: {c['text_muted']}; }}
QToolButton#NavBtn:hover {{ background: {c['surface2']}; color: {c['text']}; }}
QToolButton#NavBtn:checked {{ background: {c['primary']}1A; color: {c['primary_h']}; font-weight: 700; border-left: 3px solid {c['primary']}; }}

/* Inputs */
QLineEdit, QSpinBox, QTextEdit {{ background: {c['input']}; border: 1px solid {c['border']}; border-radius: 6px; padding: 9px 14px; min-height: 22px; color: {c['text']}; font-weight: 600; font-size: 10pt; }}
QLineEdit:focus, QSpinBox:focus, QTextEdit:focus {{ border: 1px solid {c['primary']}; outline: 2px solid {c['primary']}40; background: {c['surface']}; }}
QLineEdit::placeholder {{ color: {c['text_muted']}; font-weight: 400; }}

/* Checkbox */
QCheckBox {{ color: {c['text_dim']}; spacing: 10px; font-weight: 600; font-size: 10pt; }}
QCheckBox::indicator {{ width: 18px; height: 18px; border: 1px solid {c['border']}; border-radius: 4px; background: {c['input']}; }}
QCheckBox::indicator:hover {{ border-color: {c['primary']}; }}
QCheckBox::indicator:checked {{ background: {c['primary']}; border-color: {c['primary']}; }}

/* Progress Bar */
QProgressBar {{ background: {c['surface2']}; border: 1px solid {c['border']}; border-radius: 6px; min-height: 10px; color: transparent; }}
QProgressBar::chunk {{ background: {c['primary']}; border-radius: 5px; }}

/* Scrollbar */
QScrollBar:vertical {{ background: transparent; width: 8px; }}
QScrollBar::handle:vertical {{ background: {c['border']}; border-radius: 4px; min-height: 40px; }}
QScrollBar::handle:vertical:hover {{ background: {c['text_muted']}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
"""

# ══════════════════════════════════════════════════════════════════════════════
#  WIDGETS
# ══════════════════════════════════════════════════════════════════════════════
class LogViewer(QTextEdit):
    def __init__(self):
        super().__init__()
        self.setReadOnly(True)
        self.document().setMaximumBlockCount(8000)
        self.refresh_theme()

    def refresh_theme(self):
        self.setStyleSheet(f"""
            QTextEdit {{ background: {C['log_bg']}; border: 1px solid {C['border']}; border-radius: 6px; font-family: 'Consolas', monospace; font-size: 10pt; padding: 20px; color: {C['text']}; line-height: 1.6; }}
        """)

    def append_log(self, msg, level="INFO"):
        lvl = level.upper()
        if "error" in msg.lower() or "failed" in msg.lower(): lvl = "ERROR"
        elif "warning" in msg.lower(): lvl = "WARNING"
        elif "success" in msg.lower() or "ok" in msg.lower(): lvl = "SUCCESS"

        colours = {
            "ERROR":   (C['error'],   f"{C['error']}12"),
            "WARNING": (C['warning'], f"{C['warning']}10"),
            "SUCCESS": (C['success'], f"{C['success']}10"),
            "SYSTEM":  (C['primary'], f"{C['primary']}10"),
            "INFO":    (C['text'],    None),
        }
        text_color, bg_color = colours.get(lvl, (C['text'], None))

        ts      = datetime.datetime.now().strftime("%H:%M:%S")
        ts_html = f'<span style="color:{C["text_muted"]};font-weight:600;">[{ts}]</span>'

        badge_styles = {
            "ERROR":   f'background:{C["error"]}35;color:{C["error"]};',
            "WARNING": f'background:{C["warning"]}35;color:{C["warning"]};',
            "SUCCESS": f'background:{C["success"]}35;color:{C["success"]};',
            "SYSTEM":  f'background:{C["primary"]}30;color:{C["primary"]};',
            "INFO":    f'background:{C["accent"]}30;color:{C["accent"]};',
        }
        badge_labels = {"ERROR":" ERR ","WARNING":" WRN ","SUCCESS":" OK ","SYSTEM":" SYS ","INFO":" INF "}
        bs  = badge_styles.get(lvl, badge_styles["INFO"])
        bl  = badge_labels.get(lvl, " INF ")
        badge = f'<span style="{bs}padding:1px 7px;border-radius:4px;font-size:8pt;font-weight:700;">{bl}</span>'

        row_style = f"background:{bg_color};border-radius:4px;padding:2px 6px;" if bg_color else "padding:2px 6px;"
        html = (f'<div style="{row_style}margin-bottom:2px;">'
                f'{ts_html} {badge} '
                f'<span style="color:{text_color};font-weight:500;">{msg}</span>'
                f'</div>')
        self.append(html)
        self.moveCursor(QTextCursor.End)


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN WINDOW
# ══════════════════════════════════════════════════════════════════════════════
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} v{APP_VER}")
        self.resize(1100, 750)
        self.config   = self._load_config()
        self._theme   = self.config.get("theme", "dark")
        self._apply_theme(self._theme)
        self.processor= None
        self._running = False
        self._setup_ui()
        self._load_settings_to_ui()

    def _load_config(self):
        d = {"output_dir":"","headless":True,"delay":5,"retry":1,"max_workers":1,"stealth":True,"theme":"dark"}
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH) as f: d.update(json.load(f))
            except: pass
        return d

    def _apply_theme(self, name):
        global C
        C.update(THEMES.get(name, THEMES["dark"]))
        self._theme = name; self.config["theme"] = name

    def _setup_ui(self):
        root = QWidget(); self.setCentralWidget(root)
        hl = QHBoxLayout(root); hl.setContentsMargins(0,0,0,0); hl.setSpacing(0)
        hl.addWidget(self._build_sidebar())
        self.stack = QStackedWidget(); self.stack.setObjectName("MainContent")
        self.stack.addWidget(self._build_dashboard())   # 0
        self.stack.addWidget(self._build_settings())    # 1
        self.stack.addWidget(self._build_logs())        # 2
        hl.addWidget(self.stack)
        self.nav_queue.setChecked(True)
        self._refresh_all()

    def _build_sidebar(self):
        sb = QWidget(); sb.setObjectName("Sidebar"); sb.setFixedWidth(260)
        ly = QVBoxLayout(sb); ly.setContentsMargins(16, 32, 16, 24); ly.setSpacing(4)

        brand = QFrame(); brand.setObjectName("Card")
        brand.setStyleSheet(f"QFrame#Card {{ background: {C['surface2']}; border: 1px solid {C['border']}; border-radius: 6px; }}")
        bly = QVBoxLayout(brand); bly.setContentsMargins(16, 12, 16, 12)
        self.lbl_app = QLabel("Gemini Veo")
        self.lbl_ver = QLabel(f"business.gemini.google · v{APP_VER}"); self.lbl_ver.setObjectName("SubLabel")
        bly.addWidget(self.lbl_app); bly.addWidget(self.lbl_ver)
        ly.addWidget(brand); ly.addSpacing(20)

        self.nav_queue    = self._nav_btn("Dashboard",   "fa5s.layer-group", 0)
        self.nav_settings = self._nav_btn("Settings",    "fa5s.sliders-h",  1)
        self.nav_logs     = self._nav_btn("System Logs", "fa5s.terminal",   2)
        for b in [self.nav_queue, self.nav_settings, self.nav_logs]: ly.addWidget(b)
        ly.addStretch()

        self.btn_theme = QPushButton(); self.btn_theme.setObjectName("GhostBtn")
        self.btn_theme.setMinimumHeight(38); self.btn_theme.clicked.connect(self._toggle_theme)
        ly.addWidget(self.btn_theme); ly.addSpacing(12)

        sr = QHBoxLayout(); sr.setSpacing(8)
        self.dot_status = QLabel("●")
        self.lbl_status = QLabel("SYSTEM IDLE"); self.lbl_status.setObjectName("SubLabel")
        sr.addWidget(self.dot_status); sr.addWidget(self.lbl_status); sr.addStretch()
        ly.addLayout(sr)
        return sb

    def _nav_btn(self, text, icon, page):
        b = QToolButton(); b.setText(f"  {text}")
        b.setIconSize(QSize(18, 18)); b.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        b.setCheckable(True); b.setAutoExclusive(True)
        b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        b.setObjectName("NavBtn"); b.setMinimumHeight(44)
        b.clicked.connect(lambda _, i=page: self.stack.setCurrentIndex(i))
        b.clicked.connect(self._refresh_nav_icons)
        return b

    def _build_dashboard(self):
        page = QWidget(); ly = QVBoxLayout(page)
        ly.setContentsMargins(40, 40, 40, 40); ly.setSpacing(20)

        hdr = QHBoxLayout()
        vb  = QVBoxLayout()
        t = QLabel("Automation Queue"); t.setObjectName("PageTitle")
        s = QLabel("Enter your prompts to generate videos in Gemini."); s.setObjectName("SubLabel")
        vb.addWidget(t); vb.addWidget(s); hdr.addLayout(vb); hdr.addStretch()
        self.badge_count = QLabel("0 PROMPTS QUEUED"); self.badge_count.setObjectName("BadgeLabel")
        hdr.addWidget(self.badge_count, alignment=Qt.AlignVCenter)
        ly.addLayout(hdr)

        self.prompts_text = QTextEdit()
        self.prompts_text.textChanged.connect(self._update_badge)
        
        try:
            with open(os.path.join(_PROJECT_ROOT, "prompts.txt"), "r", encoding="utf-8") as f:
                self.prompts_text.setPlainText(f.read().strip())
        except Exception:
            pass
            
        ly.addWidget(self.prompts_text, stretch=1)

        ctrl = QHBoxLayout(); ctrl.setSpacing(10)
        b_add = QPushButton("  Import TXT"); b_add.setObjectName("GhostBtn")
        b_add.setIcon(qta.icon("fa5s.file-import", color=C['accent'])); b_add.setMinimumHeight(40)
        b_add.clicked.connect(self._import_txt)
        b_clr = QPushButton("  Clear All"); b_clr.setObjectName("DangerBtn")
        b_clr.setIcon(qta.icon("fa5s.trash", color=C['error'])); b_clr.setMinimumHeight(40)
        b_clr.clicked.connect(lambda: self.prompts_text.clear())
        ctrl.addWidget(b_add); ctrl.addWidget(b_clr); ctrl.addStretch()

        self.btn_start = QPushButton("  START AUTOMATION"); self.btn_start.setObjectName("PrimaryBtn")
        self.btn_start.setIcon(qta.icon("fa5s.rocket", color="#FFF")); self.btn_start.setMinimumSize(220, 48)
        self.btn_start.clicked.connect(self._start)
        self.btn_cancel = QPushButton("  FORCE STOP"); self.btn_cancel.setObjectName("DangerBtn")
        self.btn_cancel.setIcon(qta.icon("fa5s.stop", color=C['error'])); self.btn_cancel.setMinimumSize(150, 48)
        self.btn_cancel.hide(); self.btn_cancel.clicked.connect(self._cancel)
        ctrl.addWidget(self.btn_start); ctrl.addWidget(self.btn_cancel)
        ly.addLayout(ctrl)

        self.prog_card = QFrame(); self.prog_card.setObjectName("AccentCard"); self.prog_card.hide()
        pl = QVBoxLayout(self.prog_card); pl.setContentsMargins(20, 16, 20, 16); pl.setSpacing(8)
        ph = QHBoxLayout()
        self.prog_lbl = QLabel("Initializing engine...")
        self.prog_lbl.setStyleSheet(f"color:{C['text']}; font-weight:600; font-size:11pt;")
        ph.addWidget(self.prog_lbl); ph.addStretch()
        self.prog_pct = QLabel("0%")
        self.prog_pct.setStyleSheet(f"color:{C['primary_h']}; font-weight:700; font-size:12pt;")
        ph.addWidget(self.prog_pct); pl.addLayout(ph)
        self.pbar = QProgressBar(); pl.addWidget(self.pbar)
        ly.addWidget(self.prog_card)
        return page

    def _build_settings(self):
        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        content = QWidget(); ly = QVBoxLayout(content)
        ly.setContentsMargins(40, 40, 40, 40); ly.setSpacing(24)

        t = QLabel("Automation Config"); t.setObjectName("PageTitle"); ly.addWidget(t)
        s = QLabel("Settings are saved automatically."); s.setObjectName("SubLabel"); ly.addWidget(s)

        def section(label, icon_name, card_type="AccentCard"):
            f = QFrame(); f.setObjectName(card_type)
            fl = QVBoxLayout(f); fl.setContentsMargins(24, 20, 24, 20); fl.setSpacing(16)
            hh = QHBoxLayout(); hh.setSpacing(10)
            ic = QLabel(); ic.setPixmap(qta.icon(icon_name, color=C['primary']).pixmap(20, 20))
            tl = QLabel(label); tl.setObjectName("SectionTitle")
            hh.addWidget(ic); hh.addWidget(tl); hh.addStretch(); fl.addLayout(hh)
            sep = QFrame(); sep.setFrameShape(QFrame.HLine)
            sep.setStyleSheet(f"background:{C['border']}; max-height:1px;")
            fl.addWidget(sep)
            form = QFormLayout(); form.setSpacing(14); form.setLabelAlignment(Qt.AlignRight)
            fl.addLayout(form)
            return f, form

        def row_label(text, hint=""):
            w = QWidget(); ly2 = QVBoxLayout(w); ly2.setContentsMargins(0, 0, 12, 0); ly2.setSpacing(2)
            l = QLabel(text); l.setStyleSheet(f"color:{C['text']};font-weight:600;font-size:10pt;")
            ly2.addWidget(l)
            if hint: h = QLabel(hint); h.setObjectName("HintLabel"); ly2.addWidget(h)
            return w

        g1, f1 = section("Output", "fa5s.folder", "SuccessCard")
        self.i_out = QLineEdit(); self.i_out.setPlaceholderText("Output Directory")
        b_brw = QPushButton(); b_brw.setObjectName("GhostBtn")
        b_brw.setIcon(qta.icon("fa5s.folder-open", color=C['accent'])); b_brw.setFixedSize(40, 40)
        b_brw.clicked.connect(self._browse_output)
        out_row = QHBoxLayout(); out_row.addWidget(self.i_out); out_row.addWidget(b_brw)
        f1.addRow(row_label("Save Locations", "Where generated MP4s are downloaded"), out_row)
        ly.addWidget(g1)

        g2, f2 = section("Engine & Concurrency", "fa5s.microchip", "WarnCard")
        self.s_work = QSpinBox(); self.s_work.setRange(1, 10); self.s_work.setMinimumHeight(40)
        self.s_delay = QSpinBox(); self.s_delay.setRange(0, 60); self.s_delay.setSuffix(" sec"); self.s_delay.setMinimumHeight(40)
        self.s_retry = QSpinBox(); self.s_retry.setRange(0, 10); self.s_retry.setMinimumHeight(40)
        self.chk_h = QCheckBox("Headless Chrome  (run silently in background)")
        self.chk_s = QCheckBox("Stealth Mode  (avoid bot detection)")
        
        f2.addRow(row_label("Max Concurrent Workers", "Number of Chrome instances running at once"), self.s_work)
        f2.addRow(row_label("Action Delay", "Pauses between operations"), self.s_delay)
        f2.addRow(row_label("Prompt Retries", "Retries if prompt generation fails"), self.s_retry)
        f2.addRow("", self.chk_h); f2.addRow("", self.chk_s)
        ly.addWidget(g2)

        btn_sv = QPushButton("  SAVE ALL SETTINGS"); btn_sv.setObjectName("PrimaryBtn")
        btn_sv.setIcon(qta.icon("fa5s.save", color="#FFF")); btn_sv.setMinimumHeight(52)
        btn_sv.clicked.connect(self._save_config); ly.addWidget(btn_sv)
        ly.addStretch()
        scroll.setWidget(content); return scroll

    def _build_logs(self):
        page = QWidget(); ly = QVBoxLayout(page)
        ly.setContentsMargins(40, 40, 40, 40); ly.setSpacing(20)

        self.log_viewer = LogViewer()

        hdr = QHBoxLayout()
        t = QLabel("System Logs"); t.setObjectName("PageTitle")
        hdr.addWidget(t); hdr.addStretch()
        b_clr = QPushButton("  Clear"); b_clr.setObjectName("DangerBtn")
        b_clr.setIcon(qta.icon("fa5s.eraser", color=C['error']))
        b_clr.clicked.connect(lambda: self.log_viewer.clear())
        hdr.addWidget(b_clr); ly.addLayout(hdr)

        leg = QHBoxLayout(); leg.setSpacing(20)
        for label, col in [("INFO", C['accent']), ("SUCCESS", C['success']), ("WARNING", C['warning']), ("ERROR", C['error'])]:
            d = QLabel(f"●  {label}")
            d.setStyleSheet(f"color:{col}; font-size:9pt; font-weight:700;")
            leg.addWidget(d)
        leg.addStretch(); ly.addLayout(leg)
        ly.addWidget(self.log_viewer)
        return page

    def _toggle_theme(self):
        new = "light" if self._theme == "dark" else "dark"
        self._apply_theme(new)
        QApplication.instance().setStyleSheet(build_stylesheet(C))
        self._refresh_all()
        self._save_config(silent=True)

    def _refresh_all(self):
        self.lbl_app.setStyleSheet(f"font-size:22pt; font-weight:700; color:{C['primary_h']};")
        self.lbl_ver.setStyleSheet(f"font-size:8pt; font-weight:400; color:{C['text_muted']};")
        ico = "fa5s.sun" if self._theme == "dark" else "fa5s.moon"
        lbl = "  Light Mode" if self._theme == "dark" else "  Dark Mode"
        self.btn_theme.setIcon(qta.icon(ico, color=C['accent'])); self.btn_theme.setText(lbl)
        self.badge_count.setStyleSheet(f"background:{C['primary']}20; color:{C['primary_h']}; font-weight:700; font-size:9pt; padding:4px 14px; border-radius:20px; border:1px solid {C['primary']}40;")
        if hasattr(self, "log_viewer"): self.log_viewer.refresh_theme()
        self._refresh_nav_icons()
        self._set_running(self._running)

    def _refresh_nav_icons(self):
        for btn, icon in [(self.nav_queue,"fa5s.layer-group"), (self.nav_settings,"fa5s.sliders-h"), (self.nav_logs,"fa5s.terminal")]:
            btn.setIcon(qta.icon(icon, color=C['primary_h'] if btn.isChecked() else C['text_muted']))

    def _get_prompts(self):
        return [l.strip() for l in self.prompts_text.toPlainText().splitlines() if l.strip()]

    def _update_badge(self):
        n = len(self._get_prompts())
        self.badge_count.setText(f"{n} PROMPT{'S' if n != 1 else ''} QUEUED")

    def _import_txt(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select Prompts File", "", "Text Files (*.txt);;All Files (*.*)")
        if path:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    self.prompts_text.setPlainText(f.read().strip())
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to read file:\n{e}")

    def _browse_output(self):
        d = QFileDialog.getExistingDirectory(self, "Output Folder")
        if d: self.i_out.setText(d)

    def _load_settings_to_ui(self):
        c = self.config
        self.i_out.setText(c.get("output_dir", ""))
        self.s_work.setValue(c.get("max_workers", 1))
        self.s_delay.setValue(c.get("delay", 5))
        self.s_retry.setValue(c.get("retry", 1))
        self.chk_h.setChecked(c.get("headless", True))
        self.chk_s.setChecked(c.get("stealth", True))

    def _save_config(self, silent=False):
        self.config.update({
            "output_dir":  self.i_out.text().strip(),
            "max_workers": self.s_work.value(),
            "delay":       self.s_delay.value(),
            "retry":       self.s_retry.value(),
            "headless":    self.chk_h.isChecked(),
            "stealth":     self.chk_s.isChecked(),
            "theme":       self._theme,
        })
        try:
            with open(CONFIG_PATH, "w", encoding="utf-8") as f: json.dump(self.config, f, indent=2)
            prompts = self._get_prompts()
            if prompts:
                with open(os.path.join(_PROJECT_ROOT, "prompts.txt"), "w", encoding="utf-8") as f:
                    f.write("\n".join(prompts) + "\n")
            if not silent: self._log("All settings saved.", "SUCCESS")
        except Exception as e:
            self._log(f"Cannot save config: {e}", "ERROR")

    def _log(self, m, l="INFO"):
        if hasattr(self, "log_viewer"): self.log_viewer.append_log(m, l)

    def _set_running(self, r):
        self._running = r
        self.btn_start.setVisible(not r); self.btn_cancel.setVisible(r)
        self.prog_card.setVisible(r)
        color = C['success'] if r else C['text_muted']
        self.dot_status.setStyleSheet(f"color:{color}; font-size:14pt;")
        self.lbl_status.setText("PROCESSING" if r else "SYSTEM IDLE")
        self.lbl_status.setStyleSheet(f"color:{color}; font-size:8pt; font-weight:700; letter-spacing:1px;")

    def _on_progress(self, pct, msg):
        self.pbar.setValue(pct)
        self.prog_lbl.setText(msg)
        self.prog_pct.setText(f"{pct}%")

    def _on_finished(self, ok, msg, path=""):
        self._set_running(False)
        self.prog_lbl.setText("Automation completed." if ok else "Stopped or failed.")
        self.prog_pct.setText("100%" if ok else "--")
        self._log(f"{'DONE: ' if ok else 'STOPPED: '}{msg}", "SUCCESS" if ok else "ERROR")
        if path:
            self._log(f"Output saved to: {path}", "INFO")

    def _start(self):
        prompts = self._get_prompts()
        if not prompts:
            return self._log("Queue is empty. Please add prompts.", "WARNING")
        
        self._save_config(silent=True)
        self._set_running(True)
        self.log_viewer.clear()
        
        cfg = dict(self.config)
        out_root = cfg.get("output_dir", "").strip() or os.path.join(_PROJECT_ROOT, "OUTPUT_GEMINI")

        self.nav_logs.click()
        self._log("-" * 52, "SYSTEM")
        self._log(f"AUTOMATION STARTING  —  {len(prompts)} prompt(s)", "SUCCESS")
        self._log(f"Workers: {cfg['max_workers']}  |  Headless: {cfg['headless']}  |  Stealth: {cfg['stealth']}", "SYSTEM")
        self._log("-" * 52, "SYSTEM")

        self.processor = GeminiEnterpriseProcessor(
            base_dir=_PROJECT_ROOT,
            prompts=prompts,
            output_dir=out_root,
            config=cfg,
        )
        self.processor.log_signal.connect(self._log)
        self.processor.progress_signal.connect(self._on_progress)
        self.processor.finished_signal.connect(self._on_finished)
        self.processor.start()

    def _cancel(self):
        if self.processor: self.processor.cancel()
        self._log("Force stop requested — terminating workers...", "ERROR")

    def closeEvent(self, e):
        if self._running:
            if QMessageBox.question(self, "Running", "Automation is active. Force quit?") != QMessageBox.Yes:
                e.ignore(); return
            self._cancel()
        e.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    try: font = QFont("Segoe UI", 10); font.setStyleHint(QFont.SansSerif); app.setFont(font)
    except: pass
    app.setStyleSheet(build_stylesheet(C))
    w = MainWindow()
    w.show()
    sys.exit(app.exec())

