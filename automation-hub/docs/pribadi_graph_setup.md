# Setup Microsoft Graph untuk bot keuangan pribadi (akun OneDrive pribadi)

Gratis. Dilakukan sekali.

## 1. Daftarkan aplikasi di Entra
1. Buka https://entra.microsoft.com dan login dengan akun Microsoft pribadi yang punya OneDrive itu.
   (Kalau diminta membuat direktori/tenant, terima yang gratis.)
2. **App registrations -> New registration**.
   - Name: `Bot Keuangan`
   - Supported account types: **Personal Microsoft accounts only**
     (bila tidak ada, pilih "Accounts in any organizational directory and personal Microsoft accounts")
   - Redirect URI: kosongkan. **Register**.
3. Di halaman aplikasi, salin **Application (client) ID**.
4. **Authentication -> Advanced settings -> Allow public client flows = Yes -> Save**.
5. **API permissions -> Add a permission -> Microsoft Graph -> Delegated**: `Files.ReadWrite` dan `offline_access`. Tidak perlu admin consent.

## 2. Isi .env
```
MS_CLIENT_ID=<client id tadi>
```
Token tidak disimpan di Git: `data/07_pribadi/token.json` ada di folder `data/` yang di-ignore.

## 3. Siapkan file uji
Di OneDrive, **salin** `Doku Keluarga.final1.xlsx` menjadi `Doku Keluarga TEST.xlsx` (folder Documents).
`config.yaml` bagian `pribadi.onedrive_path` sudah menunjuk ke file uji. Tutup file itu di Excel desktop saat uji.

## 4. Login dan uji
```
python -m automation_hub.pribadi.graph login     # ikuti instruksi: buka link, masukkan kode
python -m automation_hub.pribadi.graph doctor    # tambah 1 baris uji, baca balik, hapus
```
`doctor` melaporkan apakah kolom rumus (Income/(Expense), Month, Year, Category, Category Type) terisi otomatis.

## 5. Pindah ke file asli
Setelah `doctor` lulus, ganti `pribadi.onedrive_path` di `config.yaml` ke file asli, lalu jalankan ulang bot.
Bot mengirim antrean ke Excel otomatis; bila gagal (offline, file terkunci), antrean tetap dan dicoba lagi.
