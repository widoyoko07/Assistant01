# Saran optimasi dan pencegahan bug

## Temuan uji DWG (RFS-020026_06.dwg, AutoCAD 2018, 54 MB)
- Converter terbuka gagal: LibreDWG 0.13.3 (build native) dan libredwg-web (WASM) tidak bisa membaca daftar section file ini; ODA File Converter diblokir jaringan sandbox. Build converter dari source memakan 15+ menit.
- Dampak: skill versi awal tidak punya jalur DWG/DXF sama sekali. Sekarang ada jalur CAD (`cad.py`), tervalidasi dengan DXF sintetis, dan kegagalan konversi menghasilkan instruksi ekspor yang jelas (DXF 2013/2018 atau PDF vektor).
- Drive: pencarian `RFS-020026` kosong; `download_file_content` mengembalikan base64 ke konteks sehingga hanya praktis untuk file kecil.
- Yang BELUM teruji: skrip CAD pada DXF asli proyek (nama layer, satuan, ladder atau centerline). Setelah user mengunggah DXF, jalankan `inspect` dulu, konfirmasi pemetaan layer, baru hitung.

## Sudah diterapkan di skill
1. Skala dicek dua arah (label vs geometri grid). Kasus nyata: label 1:120 padahal geometri 1:200 (selisih 67% pada panjang).
2. Penutup celah ladder dalam mm nyata, bukan titik tetap (tray 700W di 1:100 gagal bila memakai titik tetap; ditemukan lewat tes sintetis).
3. Parameter conduit dipilih di tengah plateau stabil: closing 0.5-1.5 pt memberi 22 m, >=2 pt memberi 15.3 m pada sheet yang sama.
4. Tray hanya dari plan; section tidak ikut (anti hitung ganda).
5. Gerbang persetujuan: execute menolak tanpa --confirm; PDF raster ditolak; skala tak diketahui = dilewati.
6. Cross-check independen: panjang tray / qty support di sheet detail (1.7 m untuk 700W, 2.2 m untuk 200W pada RFS-020026.06).
7. Overlay PNG per sheet untuk cek visual garis tengah.

## Saran lanjutan (urut prioritas)
1. **Dedup conduit vertikal**: baca callout "28mm POWER EL+6825" + cable tag, hitung per equipment dari plan (jumlah titik drop x selisih elevasi). Ini menghilangkan batas atas 211 m.
2. **Fitting tray**: deteksi tikungan/tee dari percabangan skeleton, hitung per tipe dan lebar.
3. **Sheet kembar**: bandingkan North 1 vs North 2; bila satu sisi tak punya conduit, laporkan otomatis (sudah ada pada RFS-020026.06: sheet 12 dan 13 kosong).
4. **Tombol revisi**: simpan hasil per revisi (Rev 0/1/2) dan tampilkan selisih; berguna untuk variasi dan klaim.
5. **Standarisasi CAD**: minta drafter memakai layer `E-TRAY-<lebar>` dan `E-CONDUIT-<dia>`, tray sebagai centerline (bukan ladder), blok support bernama `SUH-..`, INSUNITS terisi. Dengan itu hasil DXF eksak tanpa konfirmasi tambahan.
6. **Waste dan satuan**: tambahkan faktor waste per material di config dan kolom batang (3 m) per tipe.
7. **Keamanan data**: simpan hasil di folder baru per revisi; jangan menimpa takeoff lama.

## Checklist QA sebelum angka dipakai
- [ ] Revisi dan status gambar dicatat (IFC / Code 2 / draft).
- [ ] Peran semua sheet berwarna dikonfirmasi.
- [ ] Skala tiap sheet terverifikasi geometri, atau ditandai belum.
- [ ] Overlay tray mengikuti rute (minimal 1 sheet per tank).
- [ ] Spacing support dalam 1.0-3.0 m.
- [ ] Total tray dibandingkan dengan BoQ kontrak/estimasi awal; selisih >10% diselidiki.
- [ ] Waste ditambahkan hanya di lembar pengadaan, bukan di takeoff mentah.
