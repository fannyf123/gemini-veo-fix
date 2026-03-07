# Gemini Veo Auto Generator

Otomatis generate video AI menggunakan **Gemini Veo** (business.gemini.google) — cukup double-click, langsung jalan.

---

## Cara Pakai (Pemula)

### Langkah 1 — Download

1. Klik tombol hijau **`< > Code`** di halaman ini
2. Pilih **Download ZIP**
3. Extract ZIP ke folder manapun (misal: `C:\GeminiVeo`)

### Langkah 2 — Install Python (sekali saja)

> Kalau sudah punya Python 3.9+, lewati langkah ini.

1. Buka: https://www.python.org/downloads/
2. Klik **Download Python** (versi terbaru)
3. Jalankan installer
4. ⚠️ **WAJIB centang** `Add Python to PATH` sebelum klik Install
5. Selesai

### Langkah 3 — Isi Prompt Video

Buka file **`prompts.txt`** dengan Notepad, ketik prompt video kamu (satu prompt per baris).

Contoh isi `prompts.txt`:
```
A golden sunset over a mountain lake with reflections in 4K
A futuristic city at night with flying cars and neon lights
A close-up of a butterfly landing on a flower in slow motion
```

### Langkah 4 — Jalankan

Double-click file **`Launcher.bat`**

Launcher akan otomatis:
- Install semua dependencies yang dibutuhkan
- Buat config.json jika belum ada
- Buat prompts.txt contoh jika belum ada
- Menjalankan aplikasi GUI

> Saat pertama kali jalan, proses install bisa memakan waktu 1-3 menit. Selanjutnya langsung jalan.

---

## Struktur File

```
GeminiVeo/
|-- Launcher.bat         <- Double-click ini untuk mulai
|-- gui.py               <- Antarmuka aplikasi (jangan diedit)
|-- prompts.txt          <- Daftar prompt video kamu (edit ini)
|-- config.json          <- Pengaturan (opsional)
|-- requirements.txt     <- List dependencies Python (jangan diedit)
|-- App/
    |-- gemini_enterprise.py   <- Logika utama
    |-- mailticking.py         <- Modul email temp
    |-- js_constants.py        <- JS Shadow DOM selectors
    |-- chrome_utils.py        <- Chrome/driver setup
    |-- browser_helpers.py     <- Selenium helpers
    |-- account_manager.py     <- Registrasi akun & OTP
    |-- video_generator.py     <- Generate & download video
```

---

## Pengaturan (config.json)

Buka file `config.json` dengan Notepad untuk mengubah pengaturan:

| Setting | Default | Keterangan |
|---|---|---|
| `delay` | `5` | Jeda antar video (detik) |
| `retry` | `2` | Berapa kali coba ulang jika gagal |
| `headless` | `false` | `true` = browser tidak tampil |
| `max_workers` | `1` | Jumlah akun paralel |

---

## Hasil Video

Semua video yang berhasil di-generate tersimpan di folder:
```
OUTPUT_GEMINI\
```

---

## Troubleshooting

### Launcher error / tidak bisa jalan
- Pastikan Python sudah terinstall dan ada di PATH
- Klik kanan `Launcher.bat` → **Run as Administrator**
- Pastikan antivirus tidak memblokir file `.bat`

### Aplikasi berhenti dengan error
- Cek folder `DEBUG\` untuk screenshot error
- Jalankan diagnosa: buka CMD di folder ini, ketik `python diagnose.py`

### Browser tidak ditemukan
- Pastikan Google Chrome terinstall
- Download di: https://www.google.com/chrome/

### Video tidak ter-download
- Pastikan tidak ada VPN yang memblokir Google
- Coba set `headless: false` di config.json agar browser terlihat

---

## Requirements

- Windows 10/11 (64-bit)
- Python 3.9 atau lebih baru
- Google Chrome (terbaru)
- Koneksi internet
