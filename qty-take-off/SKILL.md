---
name: "qty-take-off"
description: Hitung quantity cable tray dan conduit dari shop drawing (SD) proyek Jakarta Sewerage (WWTP JSDP Pluit Zone 1) - file DXF/DWG (eksak dari entitas/layer) atau PDF vektor (garis ungu = tray, hijau = conduit). Output panjang tray per lebar (200W/700W), conduit horizontal dan vertikal, jumlah support, cross-check jarak support, Excel. Sumber file: lampiran chat atau Google Drive. Gunakan setiap kali user menyebut takeoff, quantity/qty/volume cable tray, cable ladder, conduit, shop drawing/SD, DWG, DXF, BoQ kelistrikan dari gambar, "berapa panjang tray/conduit", atau mengunggah file layout panel/tray/conduit (mis. RFS-020026), meskipun tidak menyebut kata skill.
---

# Qty Take-off (cable tray dan conduit dari shop drawing)

Bahasa: Indonesia, singkat. Keraguan disebut di AWAL jawaban.

## 1. Prinsip
1. Selalu jalankan skrip; jangan menghitung dari gambar secara visual atau dari ingatan. Angka di jawaban = keluaran skrip.
2. Urutan sumber (paling akurat dulu): **DXF/DWG** (panjang dari entitas CAD; hasil bergantung pada satuan dan pemetaan layer) > **PDF vektor** (ukur garis berwarna, +/-5%) > scan/raster (ditolak).
3. Dry-run dulu (tabel di chat). Excel HANYA setelah user setuju (`execute` menolak tanpa `--confirm`).
4. Conduit dan tray vertikal dari section PDF = BATAS ATAS (section dapat menampilkan jalur yang sama berulang). Dari DXF 3D = eksak; DXF 2D = tidak ada vertikal di geometri (dilaporkan).
5. Tidak ada angka dikarang: skala/satuan tidak diketahui = dilaporkan dan dilewati.

## 2. Workflow
**0. Ambil file** (tanyakan sumbernya satu kalimat bila tidak jelas):
- *Lampiran chat*: file ada di `/mnt/user-data/uploads`. Ini jalur utama, wajib untuk file besar.
- *Google Drive*: `tool_search` "Google Drive", lalu `search_files` (`title contains 'RFS-020026'`) -> `download_file_content`. Hasilnya base64 yang masuk ke konteks, jadi hanya praktis untuk file kecil (PDF/DXF beberapa MB). DWG puluhan MB: minta user melampirkan ke chat. Tidak ketemu di Drive = katakan, jangan menebak ID.

**1. Format**
| File | Perlakuan |
|---|---|
| `.dxf` | langsung `inspect`/`plan` |
| `.dwg` | skrip memprioritaskan ODA File Converter (set `ODA_BIN` atau pastikan tersedia di PATH), lalu `dwg2dxf` sebagai fallback. Konversi berlangsung di folder sementara agar DXF lama tidak terbaca sebagai keluaran baru; hasil wajib bisa dibaca oleh `ezdxf`. Jika converter tidak tersedia/gagal, laporkan dengan jelas; konversi lokal tersedia melalui `scripts/convert_local.py` / `convert_local.bat`. Jangan fallback diam-diam ke PDF. |
| `.pdf` | jalur PDF; wajib vektor (CAD plot), bukan scan |

**2. Inspect**: `python3 scripts/takeoff.py inspect <file> --out /tmp/tk`
- DXF/DWG: layer + panjang + kandidat tray/conduit, satuan (INSUNITS), 3D atau 2D, blok support, layout/xref. Minta user mengonfirmasi **pemetaan layer** (atur lewat `--config`: `layers`, `layer_widths`).
- PDF: peran sheet, skala label vs geometri grid.

**3. Plan (dry-run)**: `python3 scripts/takeoff.py plan <file> --out /tmp/tk [--config cfg.json] [--scale 3=200] [--sheets 5,14]`
PDF 30 sheet sekitar 1-2 menit; DXF hitungan detik. Tampilkan tabel apa adanya, cross-check support, peringatan.

**4. QA**: PDF = buka `overlay/sheetXX_tray.png` (merah = garis tengah) minimal 1 sheet per tank. DXF/DWG = cek satuan, pemetaan layer/lebar, XREF, paper space, duplikasi, deteksi ladder, dan apakah plan/section di model space perlu dipisah dengan `include_windows`. `inspect` menampilkan bbox per layer; `cad.py suggest FILE.dxf --out cfg.json` membuat template layer yang wajib diperiksa. Dry-run juga menampilkan run tray dan bbox untuk pengecekan visual; `Runs Tray` tersedia di Excel.

**5. Tanya satu kalimat**: "Jadikan Excel?" Tunggu jawaban.

**6. Execute**: `python3 scripts/takeoff.py execute <file> --out /tmp/tk --confirm`, `recalc.py` skill xlsx (error 0), `present_files` `Takeoff_Tray_Conduit.xlsx`. Skrip mengikat dry-run ke hash sumber, konfigurasi, dan opsi batch. Jika tidak cocok, jalankan plan lagi; gunakan folder output baru untuk checkpoint batch yang berbeda atau lama.

**Detail per sheet (PDF vektor)**: `python3 scripts/sheetdetail.py plan <pdf> --out /tmp/sd [--sheets 3,7] [--budget 240]`; OCR tersimpan di cache, jadi ulangi perintah jika belum selesai. Setelah hasil dry-run disetujui, `python3 scripts/sheetdetail.py execute <pdf> --out /tmp/sd --confirm` menghasilkan `Detail_per_Sheet.xlsx`.
- Skala memakai label `SCALE - 1:N` per view dan dibandingkan dengan grid; konflik dilaporkan dan hasil tetap provisional.
- Tray diambil dari callout OCR `CABLE TRAY nnn(W)`, bukan legenda A-K. Plan dihitung horizontal; section vertikal sebagai batas atas dan belum didedup.
- Conduit dikelompokkan menurut ukuran, jenis, dan orientasi vektor. Penempatan label ke rute terdekat selalu provisional; periksa overlay conduit.
- Ukuran conduit valid (G-Type): 16, 22, 28, 36, 42, 54, 70, 82, 92, 104 mm. Label >104 mm = kabel pada tray/ladder, bukan conduit (dikeluarkan dari hitungan, dicatat di `cables_in_tray`); ukuran <=104 yang tidak ada di daftar = dugaan salah baca OCR, dikeluarkan dan dilaporkan.
- Support dan elevasi diperiksa silang. OCR memerlukan Tesseract yang tersedia di PATH.

**Mode batch (PDF gabungan banyak set, mis. 599 halaman)**: otomatis aktif bila halaman > 40 (atau `--batch`).
- `python3 scripts/takeoff.py plan <pdf> --out /tmp/big --budget 200` lalu ulangi perintah yang sama sampai muncul tabel (checkpoint `pages.jsonl` dengan metadata `run.json`, aman bila terhenti). Perkiraan 2-4 detik per halaman berwarna; 599 halaman sekitar 25 menit. Jalankan di background (`setsid nohup`) bila perlu dan pantau jumlah baris `pages.jsonl`. File, konfigurasi, atau opsi berbeda ditolak; gunakan folder output baru untuk run baru.
- Set gambar dikelompokkan dari halaman DRAWING INDEX. Judul sama yang muncul berkali-kali = DUPLIKAT revisi; default hanya set terakhir dihitung, WAJIB konfirmasi revisi ke user.
- Setiap set diberi status keandalan (cek support OK / gagal / tanpa cek / conduit kosong / halaman tidak terukur). Set tidak andal jangan dilaporkan sebagai angka final.
- `execute --confirm` menulis `Rekap_Tray_Conduit_per_Area.xlsx`: baris = area, kolom = lebar tray (700, 600, 500, lalu lebar lain yang terukur) + conduit (total horizontal, vertikal batas atas). Kolom conduit 16/22/28 = "belum diukur" (garis hijau tidak membedakan diameter; rincian ukuran dan jenis dari label ada di `scripts/conduit.py`). Kolom Hitung (Y/N) di sheet Detail Set mengatur revisi yang dihitung.

**Conduit per ukuran dan jenis (PDF batch)**: dijalankan SETELAH plan batch tray/conduit selesai (butuh `pages.jsonl` + `plan.json` di folder batch). Label conduit ("42mmØ / SIGNAL / EL-...") adalah garis vektor, bukan teks PDF, sehingga dibaca dengan OCR (perlu Tesseract + `pytesseract`).
- `python3 scripts/conduit.py plan <pdf> --plan-dir /tmp/big --out /tmp/cond --budget 240` lalu ulangi perintah yang sama sampai tabel muncul (checkpoint `conduit_labels.jsonl`; sekitar 12-15 detik per halaman berconduit, jalankan di background bila perlu). Uji cepat: `--pages 28,490`.
- Dry-run menampilkan total per ukuran x jenis (jumlah label / meter estimasi) dan ringkasan per set. Tanya "Jadikan Excel?" lalu `python3 scripts/conduit.py execute <pdf> --plan-dir /tmp/big --out /tmp/cond --confirm` -> `Rekap_Conduit_per_Area.xlsx` (baris = area, kolom = ukuran x Power/Signal/Control; blok jumlah label, meter horizontal, meter vertikal batas atas). Jalankan `recalc.py` skill xlsx (error 0), lalu `present_files`.
- Metode HARUS disebut: jumlah label = hasil OCR (bisa terlewat; ukuran di luar daftar umum atau confidence <30 ditandai untuk cek visual); meter per kategori = ESTIMASI proporsional (panjang conduit hijau di halaman dibagi menurut jumlah label di halaman itu), bukan penelusuran leader per label. Label plan dan section bisa menghitung conduit yang sama dua kali; vertikal = batas atas. Panjang tanpa label terbaca dilaporkan terpisah ("Tanpa label").

## 3. Aturan baca hasil
- **PDF**: tray total dari plan ditambah tray vertikal dari section (batas atas, belum didedup); conduit horizontal dari plan, vertikal dari section (batas atas). Lebar dipilih dari callout tray dan legenda/support bila tersedia; pembagian panjang per lebar tetap estimasi geometri raster dan total panjang keseluruhan lebih dapat dipercaya. Skala dicek terhadap geometri grid; label bertentangan dengan >=6 garis grid = pakai geometri + peringatan (RFS-020026.06: sheet 3 dan 4 berlabel 1:120, geometri 1:200). Override `--scale SHEET=N`.
- **DXF/DWG**: panjang dari LINE/POLYLINE/ARC/SPLINE + isi blok (rekursif). Garis koordinat sama dibuang per jenis material. Tray berlebar terpetakan juga diperiksa untuk pasangan rel sejajar dengan jarak sesuai lebar; pasangan dihitung sebagai satu centerline dan dicatat dalam warning/trace hasil. Segmen ladder pendek dikecualikan hanya saat pola ladder terdeteksi. Geometri gagal dibaca, tipe entitas belum didukung, XREF/paper space, dan layer magenta/hijau belum dipetakan ditandai untuk pemeriksaan; jangan anggap hasil lengkap sebelum dicek. Lebar tray dari angka di nama layer (mis. `E-TRAY-500`) atau `layer_widths`; tanpa lebar = kelas `tanpa-lebar` + peringatan. `INSUNITS=0` = asumsi `assume_units` + peringatan.
- **Support**: PDF = qty dari sheet detail (`SUH-xx QTY n EA`); DXF = jumlah INSERT blok `SUH-..`. Huruf kode ke lebar: `support_letter_width_mm`. Cross-check panjang tray / qty support harus 1.0-3.0 m; di luar = peringatan (rute hilang atau qty salah).
- Status gambar bukan IFC/Approved atau ada komentar reviewer (mis. detail clamp/aksesori belum ada) = sebutkan; angka bisa berubah di revisi.

## 4. Batas yang harus disebut ke user
- Warna garis di gambar bervariasi sedikit (mis. hijau `(0,1,0)` dan `(0,1,0.1)`, magenta `(1,0,0.97)` dan `(1,0.14,1)`); `color_tol` default 0.16 untuk menangkap semuanya. Bila PDF baru terbaca kosong atau jauh lebih kecil, survei warna dulu sebelum menyimpulkan.
- Aksesori (clamp, elbow, flexible, splice, cover), fitting tray, dan conduit per diameter belum dihitung.
- Tray/conduit vertikal dari PDF belum didedup; tray dari section dilaporkan sebagai batas atas. Solusi bersih = DXF 3D atau hitung per cable tag/equipment (`references/saran-optimasi.md`).
- Sheet/tank kembar bisa tidak lengkap (RFS-020026.06: North 2 EL+1000 dan EL+5600 tanpa conduit); bandingkan dan laporkan.

## 5. Tes dan pemeliharaan
- `python3 -m unittest discover -s tests` (PDF dan DXF sintetis berpanjang diketahui). Regresi PDF asli: `SD_TAKEOFF_PDF=<pdf> python3 -m unittest discover -s tests` (sekitar 90 detik).
- Jalankan perintah panjang di background atau per bagian (batas 300 detik per perintah).
- Jangan ubah skrip/config tanpa diminta; setelah ubah, jalankan tes.
- Parameter di `scripts/config.default.json`: `close_mm`, `tray_widths_mm`, `spacing_range_m`, `grid_gaps_mm` (PDF); `assume_units`, `layers`, `layer_widths`, `rung_factor`, `support_letter_width_mm` (CAD).

## File
| File | Isi |
|---|---|
| `scripts/takeoff.py` | inspect, plan, execute (PDF dan dispatch CAD) |
| `scripts/batch.py` | mode batch PDF gabungan, set, duplikat, rekap per area |
| `scripts/cad.py` | konversi DWG->DXF, scan, ukur entitas DXF |
| `scripts/conduit.py` | conduit per ukuran x jenis: OCR label, alokasi proporsional, Excel rekap per area |
| `scripts/setup_converter.sh` | coba pasang `dwg2dxf` (LibreDWG) di sandbox Linux |
| `scripts/convert_local.py`, `convert_local.bat` | konversi DWG->DXF di laptop user via ODA File Converter (batch folder) |
| `scripts/config.default.json` | warna, lebar tray, parameter ukur, deret grid, layer |
| `tests/` | tes sintetis PDF dan DXF + regresi PDF asli |
| `references/saran-optimasi.md` | temuan uji, saran optimasi, checklist QA |
| `references/snippet-project-instruction.md` | teks untuk Project Instructions |
