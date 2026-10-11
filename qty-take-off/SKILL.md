---
name: "qty-take-off"
description: Hitung quantity cable tray dan conduit dari shop drawing (SD) proyek Jakarta Sewerage (WWTP JSDP Pluit Zone 1) - file DXF/DWG (eksak dari entitas/layer) atau PDF vektor (garis ungu = tray, hijau = conduit). Output panjang tray per lebar (200W/700W), conduit horizontal dan vertikal, jumlah support, cross-check jarak support, Excel. Sumber file: lampiran chat atau Google Drive. Gunakan setiap kali user menyebut takeoff, quantity/qty/volume cable tray, cable ladder, conduit, shop drawing/SD, DWG, DXF, BoQ kelistrikan dari gambar, "berapa panjang tray/conduit", atau mengunggah file layout panel/tray/conduit (mis. RFS-020026), meskipun tidak menyebut kata skill.
---

# Qty Take-off (cable tray dan conduit dari shop drawing)

Bahasa: Indonesia, singkat. Keraguan disebut di AWAL jawaban.

## 1. Prinsip
1. Selalu jalankan skrip; jangan menghitung dari gambar secara visual atau dari ingatan. Angka di jawaban = keluaran skrip.
2. Urutan sumber (paling akurat dulu): **DXF/DWG** (panjang eksak dari entitas) > **PDF vektor** (ukur garis berwarna, +/-5%) > scan/raster (ditolak).
3. Dry-run dulu (tabel di chat). Excel HANYA setelah user setuju (`execute` menolak tanpa `--confirm`).
4. Conduit vertikal dari section PDF = BATAS ATAS (section menampilkan conduit yang sama). Dari DXF 3D = eksak; DXF 2D = tidak ada vertikal di geometri (dilaporkan).
5. Tidak ada angka dikarang: skala/satuan tidak diketahui = dilaporkan dan dilewati.

## 2. Workflow
**0. Ambil file** (tanyakan sumbernya satu kalimat bila tidak jelas):
- *Lampiran chat*: file ada di `/mnt/user-data/uploads`. Ini jalur utama, wajib untuk file besar.
- *Google Drive*: `tool_search` "Google Drive", lalu `search_files` (`title contains 'RFS-020026'`) -> `download_file_content`. Hasilnya base64 yang masuk ke konteks, jadi hanya praktis untuk file kecil (PDF/DXF beberapa MB). DWG puluhan MB: minta user melampirkan ke chat. Tidak ketemu di Drive = katakan, jangan menebak ID.

**1. Format**
| File | Perlakuan |
|---|---|
| `.dxf` | langsung `inspect`/`plan` |
| `.dwg` | skrip mencoba konversi (`dwg2dxf` atau `ODAFileConverter`, bila ada). Gagal = skrip mengeluarkan instruksi; sampaikan ke user: ekspor **SAVEAS DXF (2013/2018)** atau **PLOT ke PDF vektor**, lalu unggah ulang. Jangan mencoba build converter dari source (15+ menit, hasil pada DWG besar tetap gagal). |
| `.pdf` | jalur PDF; wajib vektor (CAD plot), bukan scan |

**2. Inspect**: `python3 scripts/takeoff.py inspect <file> --out /tmp/tk`
- DXF/DWG: layer + panjang + kandidat tray/conduit, satuan (INSUNITS), 3D atau 2D, blok support, layout/xref. Minta user mengonfirmasi **pemetaan layer** (atur lewat `--config`: `layers`, `layer_widths`).
- PDF: peran sheet, skala label vs geometri grid.

**3. Plan (dry-run)**: `python3 scripts/takeoff.py plan <file> --out /tmp/tk [--config cfg.json] [--scale 3=200] [--sheets 5,14]`
PDF 30 sheet sekitar 1-2 menit; DXF hitungan detik. Tampilkan tabel apa adanya, cross-check support, peringatan.

**4. QA**: PDF = buka `overlay/sheetXX_tray.png` (merah = garis tengah) minimal 1 sheet per tank. DXF = cek peringatan (garis ganda dibuang, ladder rel/2, satuan, 2D).

**5. Tanya satu kalimat**: "Jadikan Excel?" Tunggu jawaban.

**6. Execute**: `python3 scripts/takeoff.py execute <file> --out /tmp/tk --confirm`, `recalc.py` skill xlsx (error 0), `present_files` `Takeoff_Tray_Conduit.xlsx`.

**Mode batch (PDF gabungan banyak set, mis. 599 halaman)**: otomatis aktif bila halaman > 40 (atau `--batch`).
- `python3 scripts/takeoff.py plan <pdf> --out /tmp/big --budget 200` lalu ulangi perintah yang sama sampai muncul tabel (checkpoint `pages.jsonl`, aman bila terhenti). Perkiraan 2-4 detik per halaman berwarna; 599 halaman sekitar 25 menit. Jalankan di background (`setsid nohup`) bila perlu dan pantau jumlah baris `pages.jsonl`.
- Set gambar dikelompokkan dari halaman DRAWING INDEX. Judul sama yang muncul berkali-kali = DUPLIKAT revisi; default hanya set terakhir dihitung, WAJIB konfirmasi revisi ke user.
- Setiap set diberi status keandalan (cek support OK / gagal / tanpa cek / conduit kosong / halaman tidak terukur). Set tidak andal jangan dilaporkan sebagai angka final.
- `execute --confirm` menulis `Rekap_Tray_Conduit_per_Area.xlsx`: baris = area, kolom = lebar tray (700, 600, 500, lalu lebar lain yang terukur) + conduit (total horizontal, vertikal batas atas). Kolom conduit 16/22/28 = "belum diukur" (garis hijau tidak membedakan diameter). Kolom Hitung (Y/N) di sheet Detail Set mengatur revisi yang dihitung.

## 3. Aturan baca hasil
- **PDF**: tray hanya dari sheet plan; conduit horizontal dari plan, vertikal dari section (batas atas). Skala dicek terhadap geometri grid; label bertentangan dengan >=6 garis grid = pakai geometri + peringatan (RFS-020026.06: sheet 3 dan 4 berlabel 1:120, geometri 1:200). Override `--scale SHEET=N`.
- **DXF/DWG**: panjang dari LINE/POLYLINE/ARC/SPLINE + isi blok (rekursif). Garis berkoordinat sama dibuang (duplikat CAD). Lebar tray dari angka di nama layer (mis. `E-TRAY-700`) atau `layer_widths`; tanpa lebar = kelas `tanpa-lebar` + peringatan. Gambar ladder (banyak segmen pendek) = rel/2, wajib dikonfirmasi. `INSUNITS=0` = asumsi `assume_units` + peringatan.
- **Support**: PDF = qty dari sheet detail (`SUH-xx QTY n EA`); DXF = jumlah INSERT blok `SUH-..`. Huruf kode ke lebar: `support_letter_width_mm`. Cross-check panjang tray / qty support harus 1.0-3.0 m; di luar = peringatan (rute hilang atau qty salah).
- Status gambar bukan IFC/Approved atau ada komentar reviewer (mis. detail clamp/aksesori belum ada) = sebutkan; angka bisa berubah di revisi.

## 4. Batas yang harus disebut ke user
- Aksesori (clamp, elbow, flexible, splice, cover), fitting tray, dan conduit per diameter belum dihitung.
- Conduit vertikal dari PDF belum didedup; solusi bersih = DXF 3D atau hitung per cable tag/equipment (`references/saran-optimasi.md`).
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
| `scripts/config.default.json` | warna, lebar tray, parameter ukur, deret grid, layer |
| `tests/` | tes sintetis PDF dan DXF + regresi PDF asli |
| `references/saran-optimasi.md` | temuan uji, saran optimasi, checklist QA |
| `references/snippet-project-instruction.md` | teks untuk Project Instructions |
