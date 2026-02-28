# 🎬 Gemini Veo Auto Generator

Otomasi **generate video AI** menggunakan [Gemini Business (Veo)](https://business.gemini.google/) dengan akun temp email dari [mailticking.com](https://mailticking.com). Auto-switch akun saat rate limit.

---

## 📁 Struktur Repo

```
gemini-veo-tester/
├── App/
│   ├── __init__.py
│   ├── _stealth_compat.py       # Selenium stealth helper
│   ├── gemini_enterprise.py     # Core: otomasi Gemini Business + Veo
│   └── mailticking.py           # Core: temp email + OTP via mailticking.com
├── Launcher.bat                 # Windows: jalankan app
├── Launcher.sh                  # Linux/Mac: jalankan app
├── main.py                      # Entry point GUI
├── diagnose.py                  # Cek environment (Chrome, ChromeDriver, deps)
├── prompts.txt                  # Daftar prompt video (1 prompt per baris)
├── config.default.json          # Template konfigurasi
├── requirements.txt             # Dependencies Python
└── OUTPUT_GEMINI/               # Folder output video (dibuat otomatis)
```

---

## ⚙️ Requirements

- **Python** 3.9+
- **Google Chrome** (versi terbaru)
- **ChromeDriver** (auto-download jika tidak ada)
- Koneksi internet aktif

### Install dependencies:
```bash
pip install -r requirements.txt
```

`requirements.txt` berisi:
```
selenium
selenium-stealth
beautifulsoup4
lxml
```

---

## 🚀 Cara Pakai

### Windows
```
Double-click Launcher.bat
```

### Linux / Mac
```bash
bash Launcher.sh
```

### Manual
```bash
python main.py
```

---

## 📝 Setup Prompts

Edit file `prompts.txt` — satu prompt per baris:
```
A golden sunset over a mountain lake with reflections
A futuristic city at night with flying cars
A close-up of a butterfly landing on a flower in slow motion
```

---

## ⚙️ Konfigurasi

Salin `config.default.json` → `config.json`, lalu edit:
```json
{
  "delay": 5,
  "retry": 1,
  "headless": false
}
```

| Key | Default | Keterangan |
|---|---|---|
| `delay` | `5` | Jeda (detik) antar prompt |
| `retry` | `1` | Jumlah retry jika error |
| `headless` | `false` | Jalankan tanpa tampilan browser |

---

## 🔄 Alur Otomasi (25 Step)

```
Step 1  → Buka Chrome profil baru (temp profile)
Step 2  → Buka mailticking.com - tunggu halaman load penuh
Step 3  → Uncheck semua checkbox KECUALI id="type3" (abc@googlemail.com)
Step 4  → Klik tombol Activate (a.activeBtn)
Step 5  → Tunggu halaman reload → email aktif tersimpan
Step 6  → Buka business.gemini.google di tab baru
Step 7  → Input email ke input#email-input
Step 8  → Klik 'Continue with email' (button#log-in-button)
Step 9  → Tunggu halaman OTP load
Step 10 → Kembali ke tab mailticking
Step 11 → Reload halaman mailticking untuk cek inbox
Step 12 → Klik link 'Gemini Enterprise verification code'
          (a[href*='/mail/view/'] rel="nofollow")
Step 13 → Tunggu & baca kode OTP dari span.verification-code
Step 14 → Kembali ke tab Gemini - input OTP ke input.J6L5wc
Step 15 → Klik tombol Verify (.YUhpIc-RLmnJb)
Step 16 → Tunggu form nama - input ke input[formcontrolname="fullName"]
Step 17 → Klik 'Agree & get started' (span.mdc-button__label)
Step 18 → Tunggu h1.title 'Signing you in...' hilang
Step 19 → Tutup popup awal (span.touch = "I'll do this later")
Step 20 → Klik tools button (md-icon: page_info)
Step 21 → Pilih 'Create videos with Veo' (div[slot='headline'])
Step 22 → Input prompt ke div.ProseMirror editor
Step 23 → Tekan Enter untuk generate
Step 24 → Tunggu div.thinking-message hilang → tunggu video render
Step 25 → Download video → simpan ke OUTPUT_GEMINI/
```

### Rate Limit Auto-Switch
Jika `div.thinking-message` hilang dalam < 5 detik → terdeteksi **rate limit** → otomatis buat akun baru dan lanjut dari prompt yang gagal.

---

## 🔍 Diagnosa & Troubleshoot

Jalankan diagnose untuk cek environment:
```bash
python diagnose.py
```

Output screenshot debug tersimpan di folder `DEBUG/` secara otomatis saat error.

### Masalah Umum

| Masalah | Solusi |
|---|---|
| ChromeDriver tidak cocok | Jalankan `diagnose.py` — auto-download driver yang sesuai |
| Email tidak masuk di mailticking | Tunggu lebih lama atau cek koneksi internet |
| OTP tidak terbaca | Screenshot debug ada di folder `DEBUG/` |
| Video tidak ter-download | Cek folder `OUTPUT_GEMINI/` — mungkin masih `.crdownload` |

---

## 📌 Catatan Teknis

- **OTP Input** (`input.J6L5wc`) menggunakan opacity:0 — script menggunakan JavaScript `dispatchEvent` agar Angular membaca nilai input
- **ProseMirror editor** di-clear dengan `Ctrl+A → Delete` sebelum input prompt baru
- **ChromeDriver** auto-download dari [Chrome for Testing API](https://googlechromelabs.github.io/chrome-for-testing/) jika versi tidak cocok
- Semua file video output dinamai: `ReenzAuto_G-Business_{nomor}_{timestamp}.mp4`

---

## 📄 License

Private — for personal use only.
