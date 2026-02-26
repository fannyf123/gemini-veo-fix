# 🎬 Gemini Veo Tester

**Otomasi generate video via [business.gemini.google](https://business.gemini.google) menggunakan Playwright + Firefox Relay OTP**

> ⚠️ Repo ini untuk keperluan **testing / eksperimen pribadi**.

---

## ✨ Cara Kerja

```
1. Firefox Relay  → buat email mask sementara
2. Playwright     → buka auth.business.gemini.google/login
3. Input email mask → request OTP
4. Gmail API      → baca OTP otomatis
5. Submit OTP     → masuk dashboard Gemini Enterprise
6. Klik "+" → "Create videos with Veo"
7. Input prompt dari prompts.txt
8. Polling → tunggu video selesai di-generate
9. Download → simpan ke OUTPUT_GEMINI/
```

---

## 📦 Requirements

- Python **3.10+**
- Firefox Relay API Key → [relay.firefox.com](https://relay.firefox.com)
- Gmail + Google API `credentials.json`

---

## 🚀 Setup & Jalankan

### 1. Clone repo
```bash
git clone https://github.com/fannyf123/gemini-veo-tester.git
cd gemini-veo-tester
```

### 2. Install dependencies
```bash
pip install -r requirements.txt
playwright install chromium
```

### 3. Setup Gmail OAuth
Letakkan `credentials.json` (Gmail API) di root folder.

### 4. Isi config.json
```json
{
  "relay_api_key": "ISI_API_KEY_FIREFOX_RELAY",
  "output_dir": "",
  "headless": false,
  "max_workers": 1,
  "batch_stagger_delay": 15
}
```
> Set `headless: false` dulu saat testing agar bisa melihat browser secara langsung.

### 5. Isi prompts.txt
```
A cinematic aerial shot of rice fields in Bali at golden hour
A futuristic city at night with neon lights, rain, slow motion
```
Satu prompt per baris.

### 6. Jalankan
```bash
# Windows
Launcher.bat

# Linux / macOS
bash Launcher.sh

# Atau langsung
python main.py
```

---

## 📁 Struktur Proyek

```
gemini-veo-tester/
├── App/
│   ├── __init__.py
│   ├── firefox_relay.py       # Firefox Relay API wrapper
│   ├── gmail_otp.py           # Gmail OTP reader
│   ├── gemini_enterprise.py   # Core: Playwright automation
│   └── gemini_batch.py        # Batch multi-prompt processor
├── main.py                    # Entry point (CLI)
├── config.json                # Konfigurasi
├── prompts.txt                # Daftar prompt video
├── credentials.json           # (tidak di-commit) Gmail API
├── requirements.txt
├── Launcher.bat
└── Launcher.sh
```

---

## ⚙️ Config

| Key | Default | Keterangan |
|---|---|---|
| `relay_api_key` | — | Firefox Relay API key |
| `output_dir` | `OUTPUT_GEMINI/` | Folder simpan video |
| `headless` | `false` | `false` = browser terlihat (recommended saat debug) |
| `max_workers` | `1` | Jumlah prompt paralel |
| `batch_stagger_delay` | `15` | Jeda (detik) antar worker |

---

## ⚠️ Disclaimer

Repo ini dibuat untuk **eksperimen / riset pribadi**. Gunakan dengan bijak dan sesuai Terms of Service platform terkait.
