# Assistant01

<img width="1186" height="1766" alt="image" src="https://github.com/user-attachments/assets/1c5d57e5-9965-4026-8c49-25948f429633" />


Workflow Daily MP v10 ada **5 tahap utama** dari input Drive sampai Excel (dengan approval gate di tengah):

### 1. **Input discovery** — Cari & simpan file per SC

- Baca 8 folder Drive tiap SC (SILOG, TODJO, DHJ, WKP, TPE, WME, DJK, BCP; BME belum ada)
- Posting.txt: format `<SC> TBM <YYYYMMDD> Posting.txt` → simpan `/tmp/mp/`
- Attendance PDF: coba OCR lokal (pdf_to_att.py) atau transkrip manual → `/tmp/mp_att/<SC>_<YYYYMMDD>_Attendance.txt` (format pipa: `Nama | Role | PT/CV`)
- DJK: satu file multi-hari, parse per tanggal

### 2. **Parse & extract** — Baca teks struktur

- **Posting.txt**: format parser berbeda per SC (TODJO punya struktur khusus, DHJ punya format sama, sebagian besar pake numbered list)
- **Attendance PDF**: hasil OCR sudah normal atau pake pdfplumber (dual-table support, nomor urut bisa hilang)
- Cek: nomor urut loncat, baris tanpa nama, hari header cocok dengan tgl file, total tertulis

### 3. **Classify & validate** — Posisi + deduplikasi

- **Pemetaan posisi**: urutan → `--map` override > aturan DJK > `sc_map.json` (per SC) > aturan umum > role baru
- **Deduplikasi**:
  - Nama + posisi sama → hapus
  - Nama mirip ≥85% (kategori sama, seksi sama) → hapus; lintas seksi → hanya warning
  - Nama sama beda posisi → warning cek manual
  - Laporkan jumlah yang dihapus di Catatan
- **Role baru**: ditaruh sementara di baris sendiri, tampilkan ke user ("X orang role Baru1 di SC SILOG"), tanya user masuk posisi mana

### 4. **Cross-check & generate** — PDF vs Posting + validasi

- **Sumber rincian per SC**:
  - SILOG, TPE, DHJ: Posting.txt utama → PDF Attendance cross-check
  - WME, WKP, BCP: **PDF Attendance utama** (rincian per posisi dari roster) → Posting.txt cross-check jumlah
  - DJK: Posting saja, tidak ada PDF
  - TODJO, BME: menunggu konfirmasi
- **Cross-check matching**:
  1. Nama persis sama
  2. Ejaan mirip ≥82%
  3. Nama singkat vs lengkap (token mirip, role sama)
  4. Mirip lemah ≥70% (minta konfirmasi)
  5. Hanya PDF / hanya Posting (selisih, lihat catatan)
- **Validasi warnings** (auto ke Catatan):
  - File kosong, hari header beda, tanggal header beda nama file
  - Total di Posting ≠ total rekap ≠ total PDF (sebutkan selisih)
  - Total WME/WKP sama persis dengan hari sebelumnya (kemungkinan salinan)
  - PDF halaman tanpa baris, OCR confidence <60, nomor urut hilang

### 5. **Display ringkas + approval**

- **Chat output** (tanpa --excel):
  - Tabel ringkas: hanya kolom SC yang ada data, baris yang ada nilai
  - Catatan: peringatan, cross-check hasil, jumlah dihapus
  - Role baru: list dengan SC dan nama orang, tanya user
- **Persetujuan wajib**: display tanya "Jadikan Excel?" — tunggu user jawab sebelum membuat file
- **Jika ada role baru**: user jawab "Driver masuk Staff, Erector masuk Skilled Workers" → jalankan ulang `--map` atau tanyakan save ke `roles.json` untuk seterusnya

### Opsi & customization

| Opsi | Fungsi |
|---|---|
| `--detail` | Tampilkan nama per posisi (panjang) |
| `--summary` | Hanya total per hari (multi-hari) |
| `--map "Role=Posisi"` | Override sementara; masuk saat itu juga |
| `--dedup-threshold 0.85` | Ketatnya fuzzy match (default) |
| `--dedup-scope category` | Kembali ke matching lintas-seksi |
| `--xc` | Cross-check PDF vs Posting (SILOG, TPE, DHJ saja) |
| `--range DARI SAMPAI` | Multi-hari + ringkasan per hari |
| `--xlsx` | Buat Excel (hanya setelah user setuju) |

### File struktur v10

```
Daily mp-v10/skills/daily-mp/
├── SKILL.md                      ← Dokumentasi lengkap & aturan per SC
├── scripts/
│   ├── run_daily_mp.sh           ← Wrapper bash (opsi, tanggal, format)
│   ├── dailymp.py                ← Parser utama + klasifikasi + dedupe
│   ├── pdf_to_att.py             ← PDF → Attendance.txt (pdfplumber + OCR lokal)
│   ├── crosscheck_pdf.py         ← Cross-check PDF vs Posting
│   ├── build_scmap.py            ← Bangun sc_map.json dari Detail_SCs.xlsx
│   ├── roles.json                ← User override: role baru → posisi
│   ├── sc_map.json               ← Pemetaan per SC (besar, 400+ entri)
│   ├── sc_manual.json            ← Token manual + aturan seksi (sumber truth)
│   └── requirements-pdf.txt      ← Deps: pdfplumber, pytesseract, opencv
├── references/
│   └── Detail_SCs.xlsx           ← User source: kolom posisi per SC
└── tests/
    └── test_dailymp.py           ← Unit tests (klasifikasi, dedupe, crosscheck, PDF)
```

### Kunci perbedaan v10 dari versi lama

1. **PDF-primary per SC**: WME, WKP, BCP sekarang ambil rincian dari PDF, bukan Posting (Posting hanya untuk cross-check total)
2. **Attendance .txt terstandar**: format pipa `Nama | Role | PT/CV` supaya parsing PDF konsisten dengan manual transcription
3. **Deduplikasi scope**: lintas-seksi hanya warning, bukan auto-hapus (bisa orang berbeda)
4. **Approval gate**: user harus setuju sebelum Excel dibuat (jangan bikin file berlebihan)
5. **Role baru interactive**: tanya user posisi, terima --map, atau save ke roles.json
6. **Cross-check terintegrasi**: dalam satu perintah, bukan script terpisah
7. **Test coverage**: 9 unit test yang ada (klasifikasi 3, dedupe 4, validasi 2, crosscheck, PDF)

### Saat dijalankan: contoh alur `Daily MP 29 Sep`

```bash
1. Claude tanya: "Cari Posting + PDF untuk 2026-09-29..."
2. Jalankan: bash scripts/run_daily_mp.sh 2026-09-29
3. Output di chat:
   ✓ Tabel ringkas (8 SC, hanya kolom ada data)
   ✓ Catatan (3-6 baris warning terpenting)
   ✓ Cross-check hasil (PDF vs Posting cocok berapa, beda berapa)
   ✓ Role baru list (jika ada)
4. Tanya: "Jadikan Excel?" 
5. User: "ya" atau "buat excel"
6. Jalankan: bash scripts/run_daily_mp.sh --xlsx 2026-09-29
7. Excel ke /mnt/user-data/outputs + present_files
```
