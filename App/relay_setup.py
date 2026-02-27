"""
relay_setup.py  —  Setup Firefox Relay API Key

Jalankan sekali untuk menyimpan API Key Firefox Relay:
    python App/relay_setup.py

Dapatkan API Key di:
    https://relay.firefox.com/accounts/profile/
    Scroll bawah → API Key → Copy
"""
import os
import sys

BASE_DIR     = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_FILE  = os.path.join(BASE_DIR, "relay_config.json")


def main():
    sys.path.insert(0, BASE_DIR)
    from App.firefox_relay import FirefoxRelay

    print()
    print("=" * 55)
    print("  Firefox Relay API Key Setup")
    print("=" * 55)
    print()
    print("Dapatkan API Key di:")
    print("  https://relay.firefox.com/accounts/profile/")
    print("  Scroll bawah → 'API Key' → Copy")
    print()

    existing = FirefoxRelay.load_key(BASE_DIR)
    if existing:
        print(f"[INFO] API Key sudah tersimpan: {existing[:8]}...{existing[-4:]}")
        replace = input(">>> Ganti dengan key baru? (y/n): ").strip().lower()
        if replace != "y":
            print("[INFO] Tidak diganti.")
            return

    api_key = input(">>> Masukkan Firefox Relay API Key: ").strip()
    if not api_key:
        print("[ERR] API Key kosong!")
        return

    relay = FirefoxRelay(api_key)
    print("[INFO] Menguji koneksi...")
    if relay.test_connection():
        FirefoxRelay.save_key(BASE_DIR, api_key)
        print(f"[OK]  API Key valid! Tersimpan di: {CONFIG_FILE}")
        print()
        print("[DONE] Sekarang setiap run Launcher.bat akan")
        print("       otomatis membuat email mask baru.")
    else:
        print("[ERR] API Key tidak valid atau gagal konek ke Firefox Relay!")
        print("      Periksa kembali key-nya.")


if __name__ == "__main__":
    main()
    input("\nPress any key to continue . . . ")
