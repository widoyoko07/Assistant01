---
name: doc-to-excel
description: Input data dari screenshot, foto, PDF teks, PDF scan, atau hasil OCR ke Excel (.xlsx), baik membuat file baru maupun menambah baris ke Excel/template yang sudah ada. Lampiran bisa dikirim lewat chat atau berada di Google Drive. Hasilnya tervalidasi (angka format Indonesia, tanggal, daftar pilihan, duplikat), setiap baris bisa dilacak ke file dan halaman sumber, dan sel yang diragukan ditandai kuning plus sheet "Perlu Verifikasi", bukan ditebak. Gunakan setiap kali user meminta memindahkan, menginput, merekap, mengetik ulang, atau mengekstrak data/tabel dari gambar, screenshot, foto, scan, nota, faktur, absensi, formulir, laporan PDF, atau dokumen lampiran ke Excel/spreadsheet, termasuk bila user hanya menulis "input data dari PDF ini", "rekap dari screenshot", "OCR ke Excel", atau "masukkan ke Excel", meskipun tidak menyebut kata skill.
---

# Doc to Excel

Memindahkan data dari dokumen visual (screenshot, foto, PDF teks, PDF scan) ke Excel dengan akurasi yang bisa dipertanggungjawabkan. Bahasa kerja: Indonesia, kecuali user memakai bahasa lain.

## Prinsip

1. **Jangan menebak.** Nilai yang tidak terbaca dikosongkan dan ditandai, bukan diisi perkiraan. Salah angka yang tampak rapi lebih berbahaya daripada sel kosong yang jelas ditandai.
2. **Setiap baris bisa dilacak**: file sumber dan halaman ikut tercatat (kolom Sumber, sheet Log).
3. **OCR itu kandidat, bukan kebenaran.** Tesseract bagus untuk volume, mata (vision) Claude bagus untuk verifikasi. Gabungkan: OCR untuk massa data, lihat gambar untuk halaman/angka yang meragukan.
4. **Angka kontrol dulu.** Bila dokumen punya total, nomor urut, atau "jumlah orang", cocokkan dengan hasil input. Selisih = ada baris terlewat atau salah baca.

## Alur

### 1. Ambil file

- **Lampiran chat**: file ada di `/mnt/user-data/uploads/`. Gambar sudah terlihat langsung oleh Claude; isi PDF tidak otomatis ada di konteks, jadi tetap ekstrak lewat skrip. Salinan gambar di disk bisa sudah diperkecil klien (maks 2000 px).
- **Google Drive**: cari dengan `search_files`, baca teksnya dengan `read_file_content` (Drive menyertakan teks OCR untuk PDF dan gambar). Batasannya: hasilnya teks saja, tidak bisa dirender ulang untuk dilihat, dan `download_file_content` mengembalikan base64 ke konteks (tidak ke sandbox) sehingga tidak praktis untuk file besar. Karena itu hasil dari jalur Drive-saja diberi label **provisional** di ringkasan. Untuk scan/tulisan tangan/angka penting, minta user melampirkan file langsung di chat. Jangan mengarang file ID; selalu dari hasil pencarian atau dari user.
- Banyak file sekaligus: kerjakan semuanya dalam satu workbook, kolom Sumber membedakan asalnya.

### 2. Inventaris

```bash
python3 scripts/extract.py --inventory /mnt/user-data/uploads
```
Hasilnya per file: PDF teks / PDF scan / campuran / gambar, jumlah halaman, dan peringatan resolusi rendah. Ini menentukan jalur di langkah 3 (satu panggilan, lalu langsung bekerja).

### 3. Tentukan skema kolom

Urutan prioritas sumber kolom: (a) Excel/template milik user (ikuti header persis, gunakan mode tambah), (b) kolom yang disebut user, (c) header yang tertulis di dokumen. Bila (c), tulis usulan skema dalam satu kalimat di ringkasan akhir dan lanjutkan bekerja; jangan berhenti untuk bertanya kecuali benar-benar buntu (mis. ada dua template dan tidak jelas mana yang dipakai). Format `schema.json` ada di `references/schema.md` (tipe `text|integer|number|date|enum`, `required`, `pattern`, `dedupe_key`, `totals`).

### 4. Ekstrak

```bash
python3 scripts/extract.py <file|folder> --out-dir /tmp/doc2x
```
Hasil: `<nama>.txt` (baris dipisah ` | `, untuk dibaca), `<nama>.json` (sel, keyakinan, halaman), dan PNG halaman OCR. PDF teks dibaca dari lapisan teksnya (keyakinan 100); halaman tanpa teks dan gambar dibaca dengan OCR. Ketahui batasannya: sel yang berdempetan bisa tergabung (mis. "Harga Satuan Jumlah"), jadi petakan kolom dari baris data, bukan dari header saja.

**Wajib lihat gambarnya (`view` pada PNG, atau gambar lampiran langsung) bila**: keyakinan halaman < 75, tulisan tangan, foto miring/bayangan, centang atau tanda tangan menentukan isi, angka berisiko tinggi (nominal, jumlah orang), atau kolom bergeser. Foto dengan pencahayaan tidak rata: ulangi dengan `--no-threshold`.

### 5. Susun `records.json`

Satu objek per baris data, kunci = `key` kolom skema. Tambahkan `_source`, `_page`, dan `_flags` untuk sel ragu: `{"qty": "buram, terbaca 20 atau 28"}`. Aturan:
- Salin nilai apa adanya dari dokumen (mis. `"8.220.000"`, `"28/09/2026"`); konversi tipe dilakukan skrip.
- Buang header yang berulang di tiap halaman, judul, dan baris subtotal/total. Total dokumen dipakai sebagai `--control`, bukan sebagai data.
- Baris yang terpotong ke dua baris (uraian panjang) disatukan. Nomor urut yang loncat = indikasi baris terlewat, periksa.
- Koreksi salah baca OCR hanya bila Anda melihat gambarnya dan yakin; catat di `_flags` apa yang diubah.
- Kolom yang kosong di dokumen dibiarkan kosong (`null`).

### 6. Bangun Excel

Baru:
```bash
python3 scripts/build_excel.py --schema schema.json --records records.json \
  --out /mnt/user-data/outputs/<nama>.xlsx --extract-json /tmp/doc2x/*.json --control jumlah=21336000
```
Tambah ke Excel yang sudah ada (bekerja pada salinan, file asli tidak diubah):
```bash
python3 scripts/build_excel.py ... --append-to /mnt/user-data/uploads/rekap.xlsx --sheet "Rekap" --header-row 3
```
Kolom dipasangkan lewat teks header; gaya baris sebelumnya ditiru. Bila di bawah data ada baris Total, skrip berhenti dan meminta `--start-row` supaya tidak menimpa. Kolom skema tanpa header padanan dilaporkan di Log.

Isi workbook: sheet data (sel ragu kuning + komentar alasan, kolom Sumber dan Status OK/CEK), **Perlu Verifikasi** (daftar sel bermasalah beserta alasan dan sumbernya), **Log** (metode per file, peringatan ekstraksi, hasil cek kontrol). Skrip menandai otomatis: kolom wajib kosong, angka/tanggal tak terbaca (termasuk huruf di dalam angka seperti `1O`), di luar rentang, tidak ada di daftar pilihan, tidak cocok pola, keyakinan OCR rendah, dan duplikat (tidak dihapus).

Jika skema memakai `totals` (rumus SUM), jalankan `python3 /mnt/skills/public/xlsx/scripts/recalc.py <file.xlsx>` sampai `total_errors` 0.

### 7. Periksa sebelum menyerahkan

- Jumlah baris vs nomor urut/total di dokumen (`--control` sudah menghitung; baca barisnya di sheet Log).
- Ambil 5 baris acak, bandingkan dengan gambar sumber, terutama nominal dan tanggal.
- Buka sheet Perlu Verifikasi: tiap entri harus Anda selesaikan (lihat gambar) atau biarkan ditandai.

Lalu `present_files` untuk file Excel. Ringkasan singkat: jumlah baris, dari mana (metode: teks/OCR/Drive), berapa yang ditandai dan apa saja yang paling perlu dicek user, serta asumsi skema. Bila ada yang provisional, katakan terus terang.

## Jebakan OCR yang sering terjadi

| Salah baca | Contoh | Cara menangani |
|---|---|---|
| Huruf mirip angka | `O`↔`0`, `l`/`I`↔`1`, `S`↔`5`, `B`↔`8`, `Z`↔`2` | Angka berisi huruf ditolak skrip dan ditandai; cek gambar |
| Titik vs koma | `68.500` (ribuan) vs `68,5` | Skema `number_locale`: `id` (default), `en`, `auto` |
| Kolom bergeser/menyatu | header tergabung, sel kosong menggeser isi | Petakan dari baris data, cek visual |
| Nama terpotong atau salah eja | `Binu` vs `Ibnu` | Jangan "memperbaiki" tanpa melihat gambar; tandai |
| Centang, tanda tangan, coretan | kehadiran, persetujuan | OCR tidak membacanya; lihat gambar atau tandai |
| Tanggal ambigu | `03/04/2026` | Dibaca hari/bulan/tahun (kebiasaan Indonesia); tandai bila konteks menunjukkan lain |

## Catatan lingkungan

Kebutuhan: `pdfplumber`, `pytesseract`, `opencv-python-headless`, `openpyxl` (di sandbox claude.ai sudah ada), serta Poppler (`pdftoppm`) dan Tesseract. Bahasa OCR: `eng+ind` dipakai otomatis bila paket `ind` terpasang, kalau tidak `eng` saja (cukup untuk angka dan nama). Jika modul/aplikasi OCR tidak ada, katakan terus terang dan baca halaman secara visual; jangan mengklaim pemrosesan OCR.

Untuk absensi manpower proyek Jakarta Sewerage (SILOG, WME, WKP, dll.), gunakan skill `daily-mp`, bukan skill ini.
