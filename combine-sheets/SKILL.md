---
name: "combine-sheets"
description: Gabungkan sheet laporan harian (mis. "1 Jun", "2 Jun", dst.) dari banyak file Excel (satu file per hari, 30/31 file, ratusan MB) menjadi SATU file Excel, lengkap dengan logo, gambar, shape, format, dan merge cell, tanpa membuka Excel (pengganti macro VBA GabungSheetDanBreakLink yang membuat Excel crash). Gunakan setiap kali user menyebut gabung sheet, combine sheet, merge banyak Excel jadi satu, Combined Report, Daily Progress Report/DPR sebulan, atau mengunggah banyak file Excel harian untuk digabung, meskipun tidak menyebut kata skill.
---

# Combine Sheets (gabung sheet dari banyak Excel)

Bahasa: Indonesia, singkat. Keraguan disebut di AWAL jawaban.

## 1. Prinsip
1. Selalu jalankan skrip `scripts/combine_sheets.py`; jangan menggabung dengan tangan atau lewat openpyxl biasa (gambar dan shape hilang, memori boros).
2. Dry-run (`scan`) dulu, tampilkan tabel. File hasil dibuat HANYA setelah user setuju (`build` menolak tanpa `--confirm`).
3. Skrip bekerja di level XML: satu file sumber dibuka per giliran, foto di sheet lain tidak pernah dimuat. 3 file (31 MB) selesai sekitar 5 detik dengan memori puncak sekitar 80 MB; 30 file kira-kira 1 menit. Hasil 30 sheet biasanya kurang dari 2 MB.
4. Angka di jawaban = keluaran skrip. Jangan mengarang.

## 2. Aturan (keputusan user)
| Hal | Perlakuan |
|---|---|
| Sheet yang diambil | Nama sheet memuat kata kunci bulan (huruf besar/kecil diabaikan), seperti VBA lama. Sheet lain (DPR, Photo, P) tidak ikut |
| Urutan | Menurut angka tanggal di nama sheet (1 Jun, 2 Jun, ...) |
| Rumus | Rumus yang hanya merujuk sel di sheet yang sama dipertahankan. Rumus ke sheet lain, file lain, atau nama terdefinisi dijadikan nilai (mis. `='DPR '!P8`) |
| Hyperlink ke sheet/file lain | Dihapus, teks tetap. Link web tetap |
| Defined names | Dibuang (3.000+ nama sampah). Print area dan print titles sheet yang diambil tetap |
| Link eksternal | Tidak dibawa |
| Logo, gambar, shape, gambar kamera Excel | Ikut persis (gambar kembar dipakai bersama sehingga file kecil) |
| Nama sheet kembar | Diberi akhiran nomor file, mis. `1 Jun (1002)`, dicatat di laporan |
| Sheet Index | Selalu di depan: link ke tiap sheet, file asal, jumlah rumus utuh/jadi nilai, gambar, shape, catatan |
| File bermasalah | Rusak/berpassword/tidak terbaca dilaporkan; file tanpa sheet cocok dilaporkan |
| Tidak dibawa (dilaporkan bila ada) | conditional formatting, tabel Excel, chart, extLst, kontrol form |
| Hasil | `Combined_Report_<Kata Kunci>_<yyyymmdd_hhmmss>.xlsx`; Excel menghitung ulang rumus saat dibuka |

## 3. Workflow
**0. Ambil file.** Konektor Drive memasukkan isi file ke chat sebagai base64, tidak praktis untuk file 6-14 MB. Jalur utama: user melampirkan file Excel langsung ke chat (bukan ZIP), dibagi beberapa pesan bila banyak; semuanya terkumpul di `/mnt/user-data/uploads`. Folder Drive hanya dipakai untuk melihat daftar/nama file dan mencocokkan jumlah dengan yang sudah diunggah (mis. 30 file untuk 30 hari). Bila jumlah terunggah kurang dari jumlah hari, katakan di awal.

**1. Scan (dry-run)** dari folder skill:
```bash
python3 scripts/combine_sheets.py scan --input /mnt/user-data/uploads --keyword jun
```
Tampilkan tabel apa adanya + peringatan (nama kembar, sheet tanpa angka tanggal, sheet tersembunyi, file bermasalah). Cek apakah jumlah sheet cocok dengan jumlah hari bulan itu; selisih disebut.

**2. Tanya satu kalimat:** "Gabungkan?" dan tunggu jawaban.

**3. Build** (setelah setuju):
```bash
python3 scripts/combine_sheets.py build --input /mnt/user-data/uploads --keyword jun --out /mnt/user-data/outputs/Combined_Report_Jun_<yyyymmdd_hhmmss>.xlsx --confirm
```
Skrip menolak menimpa file yang sudah ada. Verifikasi otomatis berjalan di akhir: untuk tiap sheet dibandingkan sel (nilai dan gaya), lebar kolom/tinggi baris, merge, page setup, gambar, shape, dan VML dengan sumbernya; jumlah rumus yang dijadikan nilai harus sama dengan laporan. Status GAGAL = katakan di awal jawaban dan jangan menyatakan selesai.

**4. Cek visual (disarankan untuk run pertama atau bila ada peringatan gambar):** render hasil ke PDF dengan LibreOffice (`run_soffice` dari skill xlsx), bandingkan 1 halaman dengan file asli.

**5. Serahkan** file `.xlsx` lewat `present_files` (jangan serahkan `.report.json`), disertai ringkasan: jumlah file/sheet, rumus jadi nilai, nama kembar, file bermasalah, hasil verifikasi, dan batas di bawah.

## 4. Batas yang harus disebut
- Rumus yang dijadikan nilai memakai nilai terakhir yang tersimpan di file sumber.
- Gambar "kamera" Excel (mis. legenda cuaca) menjadi gambar tetap; tidak lagi mengikuti sel.
- Conditional formatting, tabel Excel, dan chart tidak dibawa; skrip melaporkannya bila ada di sheet yang diambil.
- Tes visual memakai LibreOffice; tampilan di Excel bisa berbeda sedikit.
- Gaya dari file berbeda digabung per signature (font/fill/border/format angka/alignment); bila template berubah di tengah bulan, hasil tetap benar tetapi indeks gaya bertambah.

## 5. Tes dan pemeliharaan
- `python3 -m unittest discover -s tests` (file Excel sintetis: urutan, nama kembar, file rusak, gaya beda antar file, rumus, verifikasi mendeteksi perubahan).
- Jangan ubah skrip tanpa diminta; setelah ubah, jalankan tes dan ulangi uji pada file contoh asli.
- Dependensi: `lxml`; tes memakai `openpyxl`.

## File
| File | Isi |
|---|---|
| `scripts/combine_sheets.py` | scan, build, verify |
| `tests/test_combine.py` | tes sintetis |
