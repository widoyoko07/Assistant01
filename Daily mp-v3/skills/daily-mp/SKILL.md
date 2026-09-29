---
name: "daily-mp"
description: Daily MP - rekap manpower harian SILOG (PT Semen Indonesia Logistik) proyek Jakarta Sewerage (WWTP JSDP Pluit Zone 1), dari file TBM Posting.txt di Google Drive, menjadi tabel jumlah pekerja per posisi (Indirect/Direct, Project Manager sampai Heavy Equipment Operator, Total Manpower) siap tempel ke Excel rekap manpower. Termasuk cross-check dengan Attendance PDF. Gunakan setiap kali user menyebut Daily MP, rekap manpower, MP harian, TBM Posting, jumlah pekerja SILOG, cross-check absensi, atau Attendance PDF SILOG, meskipun tidak menyebut kata skill.
---

# Daily MP — SILOG

Rekap manpower harian SILOG per posisi, dalam format Excel rekap manpower user. Bahasa laporan: Indonesia.

## Alur kerja

1. **Tentukan tanggal** (default: hari ini). Tanyakan hanya jika benar-benar tidak jelas.
2. **Ambil data dari Google Drive** dengan `search_files` lalu `read_file_content`:
   - **Posting.txt**: cari `title contains 'SILOG TBM 20260928 Posting'` (format `YYYYMMDD`). Simpan ke `/tmp/mp/SILOG TBM 20260928 Posting.txt`.
   - **Attendance PDF** (untuk cross-check): cari `title contains 'SILOG TBM 20260928 Attendance'`. PDF ini bisa dibaca via `contentSnippet` dari `search_files` atau `read_file_content` — teks OCR sudah cukup. Simpan teksnya ke `/tmp/mp/SILOG_20260928_Attendance.txt`.
   - Untuk banyak hari, ambil semua pasangan file (Posting + Attendance) per tanggal.
3. **Rekap Posting** (langkah 1 = pengelompokan internal; langkah 2 = tabel ditampilkan):
   ```bash
   python scripts/dailymp.py --dir /tmp/mp --date 2026-09-28
   python scripts/dailymp.py --dir /tmp/mp --date 2026-09-28 --detail
   python scripts/dailymp.py --dir /tmp/mp --date 2026-09-28 --xlsx /mnt/user-data/outputs/Daily_MP_20260928.xlsx
   ```
4. **Cross-check PDF** (jalankan setelah rekap, jika Attendance PDF tersedia):
   ```bash
   python scripts/crosscheck_pdf.py /tmp/mp/SILOG_20260928_Attendance.txt
   ```
   Jika ingin cross-check nama per nama, jalankan Posting dulu dengan `--json`, lalu:
   ```bash
   python scripts/dailymp.py --dir /tmp/mp --date 2026-09-28 --json > /tmp/mp/posting.json
   python scripts/crosscheck_pdf.py /tmp/mp/SILOG_20260928_Attendance.txt /tmp/mp/posting.json
   ```
5. **Tampilkan** tabel rekap, hasil cross-check, Catatan, dan blok TSV. File Excel dikirim dengan `present_files`.

## Cross-check Attendance PDF

### Apa yang bisa dipakai dari PDF SILOG

PDF Attendance SILOG berformat tabel SMT&TBM dengan kolom: No | Nama | Posisi | PT/CV | Tanda Tangan. OCR Google Drive menghasilkan teks yang cukup terbaca. Yang bisa diekstrak dan dimanfaatkan:

| Data di PDF | Kegunaan cross-check |
|---|---|
| **Daftar nama + posisi SILOG** | Bandingkan 1-1 dengan Posting.txt: siapa ada di PDF tapi tidak di Posting (hadir tapi lupa dicatat), dan siapa ada di Posting tapi tidak di PDF (dicatat tapi tidak tanda tangan) |
| **Tag PT/CV = "SILOG" vs "OWJJ" vs "SILOG/HMG"** | Pisahkan pekerja SILOG dari petugas OWJJ (Andre FE, Radoin QC, Arif FE, Hanif FE, Faisal FE) yang muncul di PDF tapi bukan bagian MP SILOG, dan dari tim HMG (Tim Pulling Cable SILOG/HMG) |
| **Total Manpower tertulis di akhir PDF** | Bandingkan dengan total di Posting.txt dan total rekap: jika ketiga angka berbeda, ada yang perlu dicek |
| **Seksi / lokasi kerja** | PDF punya header seksi (ERN, LPS, Admin Building, ERS, BRS, Pipe Gallery, Workshop, Common Area, Warehouse, Team Scaffolder, Team QC, Team Lifting, Tim Pulling Cable). Cocokkan dengan seksi di Posting.txt |

### Keterbatasan PDF

- OCR tidak sempurna: nama bisa terpotong atau salah eja (contoh: "Atia roma", "Binu hunthas", "Hoyhan Muamar"). Script crosscheck_pdf.py sudah menangani ini dengan fuzzy matching 82%.
- Nomor urut di PDF kadang mengacau parsing (dua kolom paralel). Nama yang tidak terbaca dilaporkan sebagai "tidak cocok" dan perlu dicek manual.
- PDF tidak bisa membedakan "hadir tapi belum tanda tangan" vs "tidak hadir". Hanya Posting.txt yang punya keterangan ABSEN/SAKIT.
- Tim Pulling Cable bertag "SILOG/HMG" — ini subkontrak gabungan. Script tetap menghitung mereka sebagai SILOG.

### Cara membaca hasil cross-check

- **Ada di PDF, tidak di Posting** → kemungkinan hadir di lapangan tapi lupa dicantumkan di TBM. Tanyakan ke site: apakah benar hadir? Jika ya, minta dikoreksi di Posting besok.
- **Ada di Posting, tidak di PDF** → kemungkinan dicatat di TBM tapi tidak tanda tangan di lembar absensi. Bisa juga sudah pulang sebelum TBM, atau nama berbeda di kedua dokumen.
- **Nama mirip tapi ejaan beda** → ditandai di tabel fuzzy. Perlu konfirmasi apakah orang yang sama atau berbeda.

## Role baru: WAJIB tanya user

Jika output memuat bagian **PERLU KONFIRMASI**, itu berarti ada role/seksi yang belum ada di aturan (contoh: Driver, Erector, Civil, 5R HSE, 5R GA, Night Shift, Hole Watcher).
- Jangan menebak. Tampilkan tabel apa adanya (role baru sementara di baris sendiri), lalu **beri tahu user dan tanyakan** masuk posisi mana untuk tiap role, menyebut subcontractor dan jumlah orangnya.
- Setelah user menjawab, jalankan ulang dengan `--map "Driver=Staff" --map "Erector=Skilled Workers"` (nama posisi harus persis seperti di tabel).
- Memori Claude user tidak aktif, jadi jawaban tidak tersimpan sendiri. Tawarkan menambahkannya ke `scripts/roles.json` (`"role_map": {"driver": "Staff"}`) lalu kemas ulang skill agar berlaku seterusnya.

## Aturan penting

- **Tidak hadir dikeluarkan**: baris bertanda ABSEN, SAKIT, IZIN, CUTI, seksi "Off" (DJK), dan daftar "tidak berangkat" (TODJO).
- **Double dihapus otomatis**: nama dan posisi sama, atau ejaan nama mirip (85% ke atas) di posisi yang sama. Nama persis sama tapi posisi beda hanya ditandai (mungkin orang berbeda). Semua yang dihapus disebut di Catatan.
- **SM = Site Manager**, sengaja masuk Site Engineer (kebijakan user). **SI = Subcontractor Independen**, masuk Foreman. Sebutkan di catatan.
- Selalu bandingkan tiga angka: (1) total di Posting.txt, (2) total rekap setelah hapus double, (3) total di Attendance PDF. Jika ada yang berbeda, sebutkan selisihnya.
- Petugas OWJJ (Andre, Radoin, Arif, Hanif, Faisal — semua bertag "OWJJ" di PDF) bukan bagian MP SILOG, jangan ikut dihitung.
- Tim Pulling Cable bertag "SILOG/HMG" tetap dihitung sebagai SILOG.
- Jika Posting.txt tidak ditemukan di Drive, jalankan cross-check PDF saja dan laporkan bahwa Posting tidak tersedia.
- Format Posting.txt bisa sedikit berbeda tiap hari. Jika tidak dikenali skrip, katakan apa adanya dan minta format yang benar, jangan mengarang angka.

## Pemetaan posisi

| Posisi | Termasuk |
|---|---|
| Project Manager / Deputy PM / Construction Manager / Deputy CM | PM / DPM / CM / DCM |
| Site Engineer | SM, SE, Engineer, PC, PPC, Rigging Eng |
| HSE Engineer | semua HSE (koordinator dan tiap lokasi). HSE Manager hanya bila tertulis "HSE Manager" |
| Surveyor | Surveyor, Team Surveyor (SPV Survey masuk Supervisor) |
| QA/QC Department | QC, QA, anggota Team QC |
| Administration Department | Admin, DOCON |
| Staff | Matecon / Matkon (material control) |
| Supervisor | semua SPV |
| Foreman | Foreman, Foremen, FM (termasuk FM_MW), SI |
| Scaffolder | Inspector Scaffolding, Scaffolder, anggota Team Scaffolder tanpa role |
| Skilled Workers | Teknisi, Rigger, Welder, Skill, Helper, Fitter, FT, MW, MEP, crew (f)/(h) TODJO |
| Common Labor | Helper/anggota lokasi Warehouse |
| Heavy Equipment Operator | Operator Crane, Operator TMC |

Posisi Deputy PM, HSE Manager, Survey Manager, QS, Engineering Department, Rebarman, Carpenter, Stone Masonry, Security hanya terisi bila role itu tertulis di data.

## Otomatisasi berkala

Jadwalkan task harian: "Ambil SILOG TBM Posting dan Attendance PDF untuk hari ini dari Google Drive, jalankan skill daily-mp, tampilkan tabel rekap dan hasil cross-check, tanyakan role baru bila ada."
