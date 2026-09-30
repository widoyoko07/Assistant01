---
name: "daily-mp"
description: Daily MP - rekap manpower harian semua subcontractor (SILOG, TODJO, DHJ, WKP, TPE, WME, DJK, BCP, BME) proyek Jakarta Sewerage (WWTP JSDP Pluit Zone 1) dari file TBM Posting.txt dan Attendance PDF di Google Drive, menjadi tabel jumlah pekerja per posisi (Indirect/Direct, Project Manager sampai Heavy Equipment Operator, Total Manpower) siap tempel ke Excel rekap manpower, lengkap dengan cross-check absensi dan peringatan validasi data. Gunakan setiap kali user menulis 'Daily MP' (dengan atau tanpa tanggal), rekap manpower, MP harian, TBM Posting, jumlah pekerja subcontractor/SC, cross-check absensi, atau Attendance PDF, meskipun tidak menyebut kata skill.
---

# Daily MP

Rekap manpower harian semua subcontractor (SC) per posisi, dalam format Excel rekap manpower user. Bahasa laporan: Indonesia.

## Perintah singkat

Ketik di chat:
- `Daily MP` = rekap hari ini (zona Jakarta); bila belum ada Posting hari ini, pakai tanggal terakhir yang ada dan sebutkan tanggalnya.
- `Daily MP 29 Sep` = satu hari. `Daily MP 26-29 Sep` = rentang.
- Tambahkan kata `excel` (mis. `Daily MP 29 Sep excel`) untuk langsung membuat Excel.

**Persetujuan Excel (wajib)**: tanpa kata `excel`, Claude hanya **menampilkan rekap di chat** (tabel ringkas + peringatan + cross-check), lalu bertanya satu kalimat: "Jadikan Excel?". Excel dibuat hanya setelah user menjawab ya (atau menulis `buat excel`); jangan membuat Excel sebelum disetujui. Jawaban singkat: tabel, 3-6 baris catatan terpenting, pertanyaan role baru bila ada.

Yang dikerjakan Claude otomatis: cari file `<SC> TBM <YYYYMMDD> Posting.txt` dan `Attendance.pdf` di folder Drive tiap SC (ID di bawah), simpan Posting ke `/tmp/mp`, siapkan Attendance ke `/tmp/mp_att` (lihat "Otomasi Attendance PDF"), jalankan `bash scripts/run_daily_mp.sh [tanggal]` (tampil ringkas) atau `bash scripts/run_daily_mp.sh --excel [tanggal]` (setelah disetujui), lalu `present_files` untuk Excel. Rentang: `run_daily_mp.sh [--excel] dari sampai`.

Folder Drive (ID): SILOG `1wYTPvr3lVkMQ5JTfJhb4gVbj4umzVV77`, DHJ `1R_LxelCUw9Ah-uHnNPvtF2K5NxsywXx_`, TPE `1qyWFJOL-gz-WBKBS59f1GzvKBZS3Hsy3`, WME `1jBrF1vlpOg24nS47e0Takv9hjpcxBKdF`, WKP `10U6H4n-fTji42FcABm9uF10XOKm51dbH`, TODJO `1Ak9NOyQzC_Z5M3glkMuxGAOhp7fvmxJd`, BCP `1dniJsg_TSkxtWA_Ixqx5uLOvW5xzds12` (PDF foto), DJK `19yYMOfUtcr7W0RGl_9WZqyziPJ-BbKph` (satu file `DJK MP Service DD-DD Mon YYYY.txt`, beberapa hari). **BME belum memiliki ID folder di instruksi ini.** Cari dengan `title contains '<YYYYMMDD>'` (hasil berhalaman; cari juga per SC).

## Otomasi Attendance PDF

WME, WKP, dan BCP memakai PDF sebagai sumber rincian posisi; Posting hanya dipakai untuk cross-check jumlah. SILOG, TPE, dan DHJ memakai Posting sebagai sumber utama, sedangkan PDF dipakai untuk cross-check nama bila tersedia.

### Prasyarat lokal

Jalankan dari folder `Daily mp-v10/skills/daily-mp`:

```bash
python3 -m pip install -r requirements-pdf.txt
```

Untuk OCR diperlukan executable Poppler (`pdftoppm`) dan Tesseract yang ada di `PATH`. Pada Debian/Ubuntu/WSL: `sudo apt-get install poppler-utils tesseract-ocr`. Di Windows, pasang keduanya dan tambahkan folder `bin` ke `PATH`. PDF teks dapat diproses tanpa OCR; halaman hanya dirender jika lapisan teksnya gagal menghasilkan baris tabel.

### Jalur pemrosesan

1. **PDF tersedia lokal/di sandbox**: proses dengan `python3 scripts/pdf_to_att.py <file.pdf> --out /tmp/mp_att/<SC>_<YYYYMMDD>_Attendance.txt --pages-dir /tmp/mp_pages/<SC>_<YYYYMMDD>`. Parser memakai posisi teks dari `pdfplumber`, mendukung dua tabel berdampingan, lalu mencoba OCR lokal hanya pada halaman yang tidak menghasilkan baris. Format hasil tetap `Nama | Role | PT/CV`.
2. **PDF hanya dapat dibaca dari Drive**: jika konektor hanya memberikan OCR text dan PDF tidak bisa disimpan ke sandbox, susun baris `Nama | Role | PT/CV` dari hasil halaman. Jangan mengklaim pemrosesan lokal. Catat halaman sumber dan halaman yang tidak terbaca; jangan mengarang nama atau angka.
3. **Halaman kosong, nomor urut hilang, OCR confidence <60, atau tulisan tangan**: periksa gambar halaman di `--pages-dir` secara visual. Laporkan hasil PDF sebagai provisional sampai halaman bermasalah diverifikasi. Nomor urut yang hilang adalah indikasi baris terlewat, bukan bukti pasti halaman PDF hilang.

Skrip menampilkan jumlah halaman yang diproses lewat teks/OCR, halaman tanpa baris, confidence OCR rendah, dan nomor urut yang tidak muncul. Bawa semua peringatan itu ke bagian Catatan rekap; jangan hanya menyimpan file `.txt`. Tanda tangan tidak dipakai untuk menentukan hadir/tidak hadir, sehingga daftar PDF adalah roster/batas atas, bukan bukti kehadiran.

## Alur harian

1. Tentukan tanggal zona Jakarta. Cari file per SC di Drive dengan paginasi dan nama/tanggal yang sesuai; simpan Posting ke `/tmp/mp/`. Jangan mencari BME sebelum folder Drive dan sumbernya dikonfirmasi.
2. Siapkan Attendance sesuai tabel sumber per SC. Untuk PDF lokal, jalankan `pdf_to_att.py`; untuk PDF Drive-only, transkripsikan hasil baca ke file pipa. Simpan Attendance di `/tmp/mp_att/` dengan nama `<SC>_<YYYYMMDD>_Attendance.txt`.
3. Dari folder skill, jalankan satu runner berikut untuk mempertahankan mode laporan yang sama:
   - Satu hari: `bash scripts/run_daily_mp.sh [--excel] YYYY-MM-DD`
   - Tanggal terakhir yang tersedia: `bash scripts/run_daily_mp.sh [--excel]`
   - Rentang: `bash scripts/run_daily_mp.sh [--excel] YYYY-MM-DD YYYY-MM-DD`
   Tanpa `--excel`, tampilkan dulu tabel ringkas, peringatan, dan cross-check. Jangan membuat Excel sampai pengguna menulis `excel` atau menyetujui tawaran.
4. Tampilkan role baru dan data PDF yang belum terverifikasi untuk dikonfirmasi. Setelah mapping dikonfirmasi, jalankan ulang dengan `--map "Role=Posisi"`; simpan aturan persisten hanya setelah user menginstruksikan.
5. Bila diminta/disetujui, runner membuat Excel; periksa sheet `Daily MP` dan `Catatan`, lalu kirim dengan `present_files`.

Opsi lain: `--detail` (nama per posisi), `--summary` (total per hari), `--map "Role=Posisi"` (override sementara, termasuk toggle SM, mis. `--map "SM=Construction Manager"`), `--dedup-threshold 0.85`, `--dedup-scope section|category`.

**Validasi Posting otomatis** (muncul sebagai baris ⚠ di Catatan): file kosong, hari di header tidak cocok dengan tanggalnya, tanggal header beda dengan nama file, total WME/WKP sama persis dengan hari sebelumnya, total di teks tidak ditemukan. Validasi halaman/confidence PDF berasal dari output `pdf_to_att.py`; pastikan ikut disalin ke Catatan. File Attendance tanpa baris terbaca bukan 0 orang dan tidak boleh dipakai untuk menghitung PDF-primary.

**Deduplikasi**: (1) nama dan posisi sama = hapus; (2) nama mirip >= 85% di kategori sama = hapus **hanya bila di seksi/lokasi yang sama** (default `--dedup-scope section`); mirip lintas lokasi hanya diberi peringatan karena bisa orang berbeda (contoh: Rizal di Tim Pulling Cable dan M. Rizal di Admin Building, keduanya ada di PDF); (3) nama mirip di bawah ambang dan nama sama beda posisi = peringatan cek manual. Untuk kembali ke aturan lama: `--dedup-scope category`.

**Memperbarui pemetaan**: edit `references/Detail_SCs.xlsx` (kolom TODJO/BCP/BME dst.) lalu jalankan `python3 scripts/build_scmap.py`. Keputusan manual (token SILOG, Driver SILOG = Staff, aturan seksi per SC) ada di `scripts/sc_manual.json`. **Tes**: `python3 -m unittest discover -s tests`.

## Cross-check Attendance PDF

Pencocokan bertingkat: persis, ejaan mirip, nama singkat vs lengkap (role membantu bila ambigu), token mirip pada role sama, dan mirip lemah (minta konfirmasi). Orang yang ada di PDF tetapi tercatat ABSEN di Posting dipisahkan sebagai konsisten. Daftar PDF adalah roster, jadi "hanya di PDF" berarti mungkin hadir tapi tidak tercatat, bukan pasti.

### Apa yang bisa dipakai dari PDF (contoh SILOG)

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
- Khusus SILOG: **SM = Site Manager** masuk Site Engineer (kebijakan user), **SI = Subcontractor Independen** masuk Foreman. Sebutkan di catatan.
- Selalu bandingkan tiga angka: (1) total di Posting.txt, (2) total rekap setelah hapus double, (3) total di Attendance PDF. Jika ada yang berbeda, sebutkan selisihnya.
- Petugas OWJJ (Andre, Radoin, Arif, Hanif, Faisal — semua bertag "OWJJ" di PDF) bukan bagian MP SILOG, jangan ikut dihitung.
- Tim Pulling Cable bertag "SILOG/HMG" tetap dihitung sebagai SILOG.
- Jika Posting.txt tidak ditemukan di Drive, jalankan cross-check PDF saja dan laporkan bahwa Posting tidak tersedia.
- Format Posting.txt bisa sedikit berbeda tiap hari. Jika tidak dikenali skrip, katakan apa adanya dan minta format yang benar, jangan mengarang angka.

## Sumber data per SC (aturan user)

| SC | Sumber utama | Cross-check |
|---|---|---|
| SILOG, TPE, DHJ | Posting.txt | Attendance PDF |
| WME, WKP, BCP | **Attendance PDF** (rincian per posisi) | jumlah di Posting.txt (BCP: tidak ada Posting) |
| DJK Service | Posting.txt saja | tidak ada |
| TODJO | menunggu konfirmasi kebijakan sumber dan pemetaan role | - |
| BME | belum dapat diproses otomatis: sumber dan folder Drive belum dikonfirmasi | - |

**WME dari PDF**: PDF berisi roster tercetak, yaitu staf nomor 1-31 dan pekerja nomor 1-154, jadi jumlah di PDF adalah batas atas (tanda tangan tidak terbaca OCR). Klasifikasi memakai `sc_map.json` bagian WME (Forman = Foreman, Skill Matecon/Logistic dan Checker = Skilled Workers, Survey = Surveyor, Housekeeping dan Helper = Common Labor, Driver dan Docon = Staff). Hitung per nomor baris, lalu bandingkan dengan total Indirect/Direct di Posting. Jika OCR tidak memuat semua nomor (sering melewatkan halaman), sebutkan halaman yang hilang, jangan mengarang angka, dan minta user mengunggah PDF-nya langsung. Selalu cek juga hari vs tanggal di Posting (contoh: "Friday, 26 September 2026" padahal 26 Sep 2026 hari Sabtu) dan total yang identik antar hari.

## Pemetaan posisi per SC

Sumber tunggal: `scripts/sc_map.json`, dibuat dari sheet "Pemetaan Posisi" di `references/Detail_SCs.xlsx` (buatan user). Urutan prioritas klasifikasi: `--map`/`roles.json` > aturan DJK > `sc_map.json` (per SC) > aturan umum kolom "Nama Lain" > role baru (tanya user).

Ringkasan yang membedakan antar SC:
- **SILOG**: SM (Site Manager) dan PC/PPC/Rigging Eng masuk Site Engineer. Admin, DOCON, Matecon masuk **Staff** (baris Administration Department selalu 0). Foreman = Foreman/Foremen/FM/SI/Mandor. Driver = Staff. Helper = Skilled Workers, kecuali lokasi Warehouse = Common Labor.
- **TPE**: FM ELEC/FT/MW = Foreman; FM Scaffolder dan Scaffolder = Scaffolder; Helper Mech, Helper Scaff, Hole Watcher, Warehouse = Common Labor; HRD, SDCC, Driver, Admin = Staff; OPR Crane/TMC = Heavy Equipment Operator.
- **DHJ**: PM = Construction Manager; Erector, Civil, Welder = Skilled Workers; Helper = Common Labor; Helper/Inspector Scaffolder = Scaffolder.
- **WME**: Site Manager = Construction Manager; Planning/Piping/Lifting Eng = Site Engineer; Housekeeping, Helper = Common Labor; SPV HR/GA, SPV Finance, Driver, Docon, Matecon = Staff (tetapi SPV lain = Supervisor).
- **WKP**: SM = Construction Manager; Warehouse dan ADM Project = Staff; ADM QC dan QC Field = QA/QC.
- **DJK Service**: kode mengklasifikasikan SPV/Supervisor sebagai Supervisor, seksi yang memuat Warehouse sebagai Land 2, dan semua data DJK lainnya sebagai Land 1. Instruksi sumber menyebut Team Electrical, Team 5R HSE, dan Night Shift untuk Land 1; pastikan default Land 1 untuk semua data lain memang keputusan yang dimaksud.
- **TODJO, BCP, BME**: belum ada pemetaan di file, memakai aturan umum "Nama Lain" (SM = Construction Manager, Helper/Driver/Housekeeping = Common Labor).

### Konfirmasi aturan yang belum final

Pemetaan umum yang berjalan di skrip tidak otomatis berarti keputusan owner sudah dikonfirmasi. Tandai hasil berikut sebagai provisional sampai aturan disepakati:
- **TODJO**: parser khusus membaca bagian `Man Power`, `Crew`, dan `Tidak Berangkat`, tetapi role memakai pemetaan umum. Konfirmasi kategori role pada bagian Crew dan apakah fallback umum boleh dipakai.
- **BCP**: sumber utama PDF, belum ada map khusus; role yang dikenali memakai pemetaan umum, role lain muncul sebagai role baru. PDF tulisan tangan memerlukan verifikasi visual. Konfirmasi apakah pemetaan umum boleh dipakai.
- **BME**: belum ada ID folder Drive, kebijakan sumber, atau map khusus. Jangan mengambil data atau menganggap total sebagai final sebelum ketiganya dikonfirmasi.
- **DJK**: konfirmasi apakah semua entri non-SPV selain Warehouse memang masuk Land 1.
- **WME**: instruksi menyebut roster staf 1-31 dan pekerja 1-154, tetapi skrip belum memvalidasi rentang itu terpisah dan signature tidak menentukan kehadiran. Konfirmasi apakah jumlah roster tersebut berlaku untuk setiap PDF dan apakah yang dibutuhkan roster atau hanya yang tanda tangan.

Untuk mengubah pemetaan: minta user memperbarui `Detail_SCs.xlsx`, lalu bangun ulang `sc_map.json` dari sheet "Pemetaan Posisi" (satu token per role, huruf kecil, pisah koma) atau edit langsung `sc_map.json`.

**Keputusan user**: Driver SILOG masuk Staff (di `sc_manual.json`). TODJO, BCP, dan BME menunggu pemetaan dari user; sementara memakai aturan umum.

## Otomatisasi berkala

Jadwalkan task harian (hari kerja): "Daily MP" (Claude mengikuti bagian Perintah singkat).
