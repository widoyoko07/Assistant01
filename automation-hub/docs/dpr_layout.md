# Tata letak DPR final (hasil pembacaan file 5 Okt 2026, hanya dibaca, tidak diubah)

Dasar untuk M5 (mengisi blok SUB ME). Tidak ada data asli di sini, hanya struktur.

## Sheet
| Sheet | Isi |
|---|---|
| `DPR ` (spasi di belakang) | Sampul/transmittal. `AA15` = tanggal laporan, `AA16` = tanggal terbit, `AA14` = nomor minggu, `P8` = rumus array nomor DPR |
| `<d> <Bln>` (mis. `5 Oct`) | Laporan harian. `A11` = `'DPR '!AA15`. Area cetak `A1:AW199` |
| `Photo` | Dokumentasi foto, minggu/tanggal ditarik dari `DPR ` |
| `P` | Pembantu: keterangan foto (judul foto per sel) |

Sheet `ME` dan `MP Daily (2)` ada di sebagian file lain (belum diperiksa).

## Sheet harian
- Header kolom di baris 14-15. B=SUBCONT., C=WORK CATEGORY, D=WORK DESCRIPTION, E-F=QTY/UNIT, G/H/I=START/FINISH/TOTAL jam.
- Manpower `J`..`AI` (urut): Project Manager, Deputy PM, Construction Manager, Deputy CM, Site Engineer, HSE Manager, HSE Engineer, Survey Manager, Surveyor, QS, Engineering, QA/QC, Administration, M/E Dept (Jakarta), M/E Dept (Overseas), Supervisor, Foreman, Rebarman, Carpenter, Stone Masonry, Scaffolder, Skilled Workers, Common Labor, Security, Staff, Heavy Equipment Operator. `AJ` = total.
- Equipment `AK`..`AW` (Total Station, Waterpass, Excavator, Survey Equipment, Dump Truck, ..., Crane 55 Ton `AR`, Roughter Crane 50 Ton `AS`, ...). Untuk SUB ME nilainya konstan per SC (Total Station, Waterpass, Survey Equipment = 1, ditambah satu jenis crane bila ada).
- `AX` = total manpower SC (nilai angka, bukan rumus; cocok dengan jumlah `J:AI`). `BN` = kunci SC huruf kecil, `BP` = `SUM(N,R,U,AH)`.

## Blok
- SUB CIVIL: baris 31 (judul + subtotal `=SUM(J32:J144)`), isi 32-144.
- **SUB ME: baris 145 (judul + subtotal `=SUM(J146:J182)`), isi 146-185.** `AJ145` menjumlah sampai baris 185.
- Total keseluruhan baris 187: `=SUM(J17:J186,-J31,-J145)`. MATERIAL SUPPLY mulai baris 188.

## Blok per SC di SUB ME
- Satu SC = satu blok baris. Kolom manpower, total, jam, kategori, dan equipment adalah **sel gabungan vertikal** sepanjang blok; nilainya di baris pertama blok.
- Tinggi blok berbeda per hari dan per SC (2 sampai 7 baris). Contoh: SILOG 4 baris, TPE dan WME 6 baris, WKP 7 baris.
- Satu butir kerja = satu baris di kolom D, diawali "- ". Baris kosong sengaja disisakan antar blok.
- Ada dua blok DJK (satu terpisah di bawah dengan kategori "Warehouse ..."). Nama SC di kolom B: Tohoma, DJK, DHJ, WKP, TPE, WME, SILOG.
- Jam: SC lembur 08.00-21.00 / 12, SC lain 08.00-17.00 / 8.

## Dampak ke M5
1. Work Description di DPR **ringkas dan dikurasi** (sekitar 4-6 butir per SC), sedangkan Posting SC berisi puluhan butir. Isi hasil penggabungan perlu diringkas dulu.
2. Mengubah jumlah baris blok berarti memindahkan sel gabungan dan rumus di bawahnya. Pendekatan aman: salin sheet hari sebelumnya, ubah nilai, dan sesuaikan tinggi blok dengan edit XML (bukan openpyxl load+save, karena logo dan gambar bisa hilang).
3. Rumus di luar blok (subtotal, total baris 187, sheet ringkasan) harus tetap utuh dan dicek ulang setelah isi.
