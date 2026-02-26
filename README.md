# 🎬 Gemini Veo Tester

**Otomasi generate video via [business.gemini.google](https://business.gemini.google) menggunakan Playwright + OTP Gmail**

> ⚠️ Repo ini untuk keperluan **testing / eksperimen pribadi**.

---

## ✨ Cara Kerja

```
1. Playwright     → buka auth.business.gemini.google/login
2. Input email mask (dari config.json) → request OTP
3. Gmail API      → baca OTP otomatis (cari di Inbox + Spam)
4. Submit OTP     → masuk dashboard Gemini Enterprise
5. Klik "+" → "Create videos with Veo"
6. Input prompt dari prompts.txt
7. Polling → tunggu video selesai di-generate
8. Download → simpan ke OUTPUT_GEMINI/
```

---

## 📦 Requirements

- Python **3.10+**
- **Google Chrome** terinstall (wajib, untuk bypass bot-detection)
- Gmail + Google API `credentials.json`
- Email mask Firefox Relay yang sudah ada

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

### 4. Isi `config.json`
```json
{
  "mask_email":  "namaemailkamu@mozmail.com",
  "relay_api_key": "",
  "output_dir":  "",
  "headless":    false,
  "max_workers": 1
}
```
> Isi `mask_email` dengan email mask yang sudah ada di [relay.firefox.com/accounts/masks](https://relay.firefox.com/accounts/masks/).
> `relay_api_key` tidak wajib diisi.

### 5. Isi `prompts.txt`
```
A cinematic aerial shot of rice fields in Bali at golden hour
A futuristic city at night with neon lights, rain, slow motion
```
Satu prompt per baris.

### 6. Jalankan
```bash
Launcher.bat        # Windows
bash Launcher.sh    # Linux/macOS
python main.py      # Manual
```

---

## ⚠️ Catatan Penting

### OTP Masuk Spam?
**Normal.** Kode sudah otomatis mencari OTP di folder **Inbox DAN Spam** sekaligus.
Email dari Google via Firefox Relay sering masuk spam.
Jika ditemukan di spam, email otomatis dipindahkan ke Inbox.

### Google Mendeteksi Bot?
Pastikan **Google Chrome** sudah terinstall. Kode memprioritaskan Chrome asli dibanding Chromium untuk menghindari bot-detection.
```bash
# Cek Chrome tersedia untuk Playwright:
python -c "from playwright.sync_api import sync_playwright; p=sync_playwright().start(); b=p.chromium.launch(channel='chrome'); print('Chrome OK'); b.close(); p.stop()"
```

---

## 📁 Struktur Proyek

```
gemini-veo-tester/
├── App/
│   ├── __init__.py
│   ├── firefox_relay.py       # Firefox Relay API wrapper (opsional)
│   ├── gmail_otp.py           # Gmail OTP reader (cari di Inbox+Spam)
│   ├── gemini_enterprise.py   # Core: Playwright automation + anti-bot
│   └── gemini_batch.py        # Batch multi-prompt processor
├── main.py                    # Entry point (CLI)
├── config.json                # Konfigurasi (isi mask_email)
├── prompts.txt                # Daftar prompt video
├── credentials.json           # (tidak di-commit) Gmail API
├── requirements.txt
├── Launcher.bat
└── Launcher.sh
```

---

## ⚙️ Config

| Key | Keterangan |
|---|---|
| `mask_email` | **Wajib.** Email mask mozmail.com yang sudah ada |
| `relay_api_key` | Tidak wajib (tidak dipakai untuk generate) |
| `output_dir` | Folder simpan video (kosong = pakai `OUTPUT_GEMINI/`) |
| `headless` | `false` = browser terlihat (recommended saat debug) |
| `max_workers` | Jumlah prompt paralel (default: 1) |
| `batch_stagger_delay` | Jeda detik antar worker batch |
