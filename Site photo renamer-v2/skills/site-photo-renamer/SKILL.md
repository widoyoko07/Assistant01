---
name: "site-photo-renamer"
description: Ekstrak dan beri nama standar pada foto pekerjaan subcontractor dari group WhatsApp (ZIP hasil ekspor chat WA yang dibuat user secara manual, atau folder foto, dengan atau tanpa _chat.txt), menjadi foto rasio 4:3 tanpa timestamp dengan nama "yymmdd Work Location.jpg" berbahasa Inggris, siap untuk laporan proyek. Gunakan setiap kali user menyebut foto WA/WhatsApp, ekspor chat WA, foto lapangan, foto progress, foto subcon, rename foto, beri nama foto, crop 4:3, hapus timestamp foto, foto untuk laporan harian/mingguan, atau mengunggah banyak foto/ZIP dari lapangan, meskipun tidak menyebut kata skill.
---

# Site Photo Renamer

Bahasa percakapan: Indonesia, singkat, langsung ke hasil.

## 1. Tujuan

Mengubah foto mentah dari WA menjadi foto siap laporan: rasio 4:3, bersih dari timestamp, nama file standar bahasa Inggris.

Pembagian kerja:

| Dikerjakan | Oleh |
|---|---|
| Ekspor chat WA menjadi ZIP (dengan media) dan mengunggahnya | **User (manual)**; skill tidak bisa mengakses WhatsApp |
| Ekstrak ZIP, hash, tanggal, rasio, crop, penamaan, bentrok nama, log, verifikasi | `scripts/photo_tool.py` |
| Membaca isi foto: pekerjaan, lokasi, ada/tidaknya timestamp, objek utama | Claude (visual) |

Jangan menghitung nama atau crop dengan tangan. Foto laporan dipakai sebagai bukti progres, jadi nama atau tanggal salah lebih merugikan daripada foto bertanda `[CHECK]`: bila tidak yakin, tandai, jangan menebak.

## 2. Input

| Kasus | Perlakuan |
|---|---|
| ZIP ekspor chat WA (dibuat user secara manual, lihat Langkah 0) | Setelah diunggah, ZIP diekstrak otomatis oleh skrip saat scan |
| Folder foto (tanpa ZIP) | Dipindai langsung |
| Ada `_chat.txt` | Sumber tanggal prioritas 1, plus caption dan pengirim |
| Tanpa chat.txt | Tanggal dari EXIF, lalu dari nama file (`IMG-YYYYMMDD-WAxxxx`) |
| Ekspor WA tanpa media | Tidak bisa diproses (tidak ada foto); minta user mengekspor ulang dengan media |
| Video, PDF, stiker, file non-foto | Dilewati, dicatat di log |
| Duplikat persis (hash) | Dibuang, dicatat di log |
| HEIC (tanpa `pillow-heif`) | Dilaporkan sebagai dilewati, tidak dibuang diam-diam |

Prioritas tanggal: **chat.txt → EXIF → nama file**. Sumber dicatat per foto. Bila sumber saling bertentangan, foto `[CHECK]` (tanggal chat adalah waktu kirim, belum tentu waktu pengambilan; keputusan di user).

## 3. Format nama file

`yymmdd Work Location.jpg`, contoh: `260930 Rebar Installation Pump Station.jpg`

- Pekerjaan dan lokasi: bahasa Inggris, Title Case, deskriptif sesuai isi foto dan caption/chat.
- Gunakan `references/glossary.md` agar konsisten. Istilah yang belum ada: pakai terjemahan konstruksi paling jelas, lalu tanyakan di daftar pertanyaan. Tambahkan ke glosarium hanya bila user menyuruh.
- Karakter terlarang `\ / : * ? " < > |` dihapus; maksimal 120 karakter (ditangani skrip).
- Nama bentrok: nomor ` 02`, ` 03`, dst. sebelum penanda; tidak pernah menimpa.

Penanda di akhir nama, urutan `[TS]` `[CHECK]` `[PORTRAIT]`:

| Penanda | Arti | Folder |
|---|---|---|
| `[TS]` | Timestamp/overlay masih ada dan tidak aman dihilangkan | `needs-cleaning` |
| `[CHECK]` | Pekerjaan/lokasi/tanggal tidak pasti, tanggal antar sumber bertentangan, atau crop memotong objek utama | `check` |
| `[PORTRAIT]` | Masih portrait setelah koreksi EXIF | `check` |

Tidak pasti: tulis `Unidentified Work` / `Unidentified Location` + `[CHECK]`. Tanggal tidak ada: `XXXXXX` + `[CHECK]`.

## 4. Aturan foto

| Aspek | Aturan |
|---|---|
| Rasio | Wajib 4:3 landscape, center crop |
| Portrait | Dirotasi hanya bila EXIF menunjukkan salah rotasi; selain itu `[PORTRAIT]`, dilaporkan, tidak dipaksa |
| Crop memotong objek utama | `[CHECK]`, disimpan tanpa crop; jangan diputuskan diam-diam |
| Timestamp | Deteksi visual. Foto bertimestamp tidak boleh masuk `final`. Bila overlay seluruhnya di luar area crop 4:3, hilang oleh crop dan boleh masuk `final` (dicatat di log); selain itu `needs-cleaning`. Jangan inpaint tanpa persetujuan user. Detail di `references/decisions.md` |
| Kualitas | Foto yang sudah 4:3 JPEG disalin apa adanya; yang di-crop disimpan JPEG kualitas 95 |
| File asli | Tidak pernah diubah atau dihapus; hasil hanya ke folder output baru |

## 5. Mode jalan

| Mode | Perilaku |
|---|---|
| **DRY-RUN** (default) | Hanya tabel pratinjau; tidak ada foto dibuat |
| **EXECUTE** | Hanya setelah user mengonfirmasi tabel pratinjau; skrip menolak tanpa `--confirm` |

Opsi: filter rentang tanggal (`--from/--to`), filter pengirim (`--sender`), batas per run (`--limit N`).

## 6. Output

```
output/final/            foto 4:3, bersih, nama sesuai
output/needs-cleaning/   foto bertimestamp [TS]
output/check/            foto [CHECK] / [PORTRAIT]
output/log.csv           nama asli, nama baru, folder, tanggal, sumber tanggal, keputusan, catatan
```

Prioritas folder bila ada beberapa penanda: `needs-cleaning` > `check` > `final`. Akhir kerja: ringkasan total foto, berhasil, `[TS]`, `[CHECK]`, dilewati.

## 7. Workflow

Folder kerja `/tmp/spr`; unggahan user di `/mnt/user-data/uploads`. Jalankan dari folder skill.

0. **Persiapan (manual, oleh user)**: ekspor chat group WA beserta media, lalu unggah ZIP-nya ke chat. Claude tidak bisa mengekspor dari WhatsApp; bila user belum punya ZIP, pandu langkah di bawah dan tunggu unggahan, jangan lanjut tanpa file.
   - **Android**: buka group → menu ⋮ → *Lainnya* → *Ekspor chat* → pilih **Sertakan media**.
   - **iPhone**: buka group → nama group → *Ekspor Chat* → **Lampirkan Media**.
   - Hasilnya satu ZIP berisi `_chat.txt` dan foto-foto; unggah ke chat Claude.
   - Group ramai: ekspor per periode/batch karena WA membatasi jumlah pesan yang ikut diekspor bersama media. ZIP terlalu besar untuk diunggah: bagi menjadi beberapa ZIP, proses bertahap (`--from/--to` atau `--limit`).
   - Ekspor **tanpa media** tidak berguna: fotonya tidak ikut. Minta ekspor ulang.
1. **Scan** (ekstrak ZIP otomatis, validasi input, tanggal, duplikat)
   ```bash
   python3 scripts/photo_tool.py scan <folder-atau-zip> --work /tmp/spr [--chat <_chat.txt>] [--from YYYY-MM-DD --to YYYY-MM-DD] [--sender "nama"] [--limit N]
   ```
   Pratinjau 1024 px di `/tmp/spr/preview/<id>.jpg`, metadata di `inventory.json`. Bila ZIP tidak berisi `_chat.txt`, katakan bahwa tanggal hanya dari EXIF/nama file dan caption/pengirim tidak tersedia.
2. **Analisis isi foto**: lihat tiap pratinjau (`view`, bertahap ~10 foto) bersama caption/pengirim, lalu tulis `/tmp/spr/decisions.json` sesuai `references/decisions.md`. Kosongkan `work`/`location` bila tidak pasti dan isi `question`.
3. **Dry-run**
   ```bash
   python3 scripts/photo_tool.py plan --work /tmp/spr
   ```
   Tampilkan tabel apa adanya (nama lama | nama baru | tanggal & sumber | rasio | timestamp | status) dan hitungan per folder. Semua pertanyaan ambigu dalam **satu daftar di akhir**, tanpa berhenti per foto. Tanya "Lanjut EXECUTE?" dan tunggu. Koreksi user: ubah `decisions.json`, jalankan `plan` ulang.
4. **Execute** (setelah konfirmasi)
   ```bash
   python3 scripts/photo_tool.py execute --work /tmp/spr --out /mnt/user-data/outputs/output --confirm --zip
   ```
5. **Verifikasi akhir** (otomatis): semua `final` rasio 4:3, nama sesuai pola, tidak ada `[TS]` di `final`, input = output + dilewati. Bila GAGAL, katakan di awal jawaban dan jangan menyatakan selesai.
6. **Serahkan** `output.zip` dengan `present_files` (folder tidak bisa dibagikan) beserta ringkasan.

Titik keterlibatan user: **langkah 0** (menyiapkan dan mengunggah ZIP) dan **konfirmasi dry-run** (langkah 3).

## 8. Aturan anti-error

- Jangan menebak tanggal, pekerjaan, atau lokasi; tandai `[CHECK]`.
- Ambiguitas dikumpulkan dalam satu daftar di akhir dry-run.
- Jangan menimpa atau menghapus file asli; skrip menolak menulis ke folder output yang sudah berisi hasil (pakai `--out` baru).
- Jujur tentang metode: timestamp dinilai visual dari pratinjau, bukan OCR; overlay samar ditandai `[CHECK]` dan disebutkan.
- Jangan mengklaim bisa mengambil foto langsung dari WhatsApp; semua input datang dari unggahan user.
- Folder/ZIP sangat besar: sarankan `--limit` dan proses bertahap.

## File dalam skill

| File | Isi |
|---|---|
| `scripts/photo_tool.py` | scan, plan, execute, verifikasi |
| `references/decisions.md` | Skema `decisions.json` dan aturan penilaian timestamp |
| `references/glossary.md` | Glosarium Indonesia → English (milik user, bisa ditambah) |
