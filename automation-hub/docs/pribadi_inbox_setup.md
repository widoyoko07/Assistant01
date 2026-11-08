# K3c: transaksi ke Excel lewat file inbox (tanpa Azure)

Alur: Telegram -> bot (laptop) -> `Inbox Transaksi.tsv` di OneDrive -> makro `TarikInbox` -> tabel `_transaction`.
Bot hanya menulis saat laptop menyala dan OneDrive sinkron. Pesan yang tertunda diambil saat bot hidup lagi.

## 1. Bot
`.env` berisi `INBOX_PATH=/mnt/c/Users/<nama>/OneDrive/Documents/Inbox Transaksi.tsv` (jalur WSL).
Jalankan ulang bot; setiap pesan yang tercatat langsung ditambahkan ke file itu.

## 2. Makro (sekali, di Excel desktop)
1. Buat Personal Macro Workbook bila belum ada: View -> Macros -> Record Macro, "Store macro in: Personal Macro Workbook", OK, lalu Stop Recording.
2. Alt+F11 -> klik kanan modul di `VBAProject (PERSONAL.XLSB)` -> Import File -> `docs/pribadi_inbox_macro.bas`.
3. Tambah tombol: File -> Options -> Quick Access Toolbar -> Choose commands from: Macros -> `TarikInbox` -> Add.
4. Alt+F11 -> Tools -> References: pastikan tidak ada "MISSING". Simpan, tutup Excel, pilih Save saat ditanya soal PERSONAL.XLSB.

## 3. Uji di salinan (JANGAN file asli dulu)
1. Buka `Doku Keluarga TEST.xlsx`, aktifkan Macros bila diminta.
2. Kirim `cash parkir 5rb` ke bot, tunggu ~30 detik hingga baris muncul di Inbox.
3. Klik tombol `TarikInbox`. Baris baru harus muncul di akhir tabel 04.record dengan Month, Year, Category, Category Type terisi.
4. Klik lagi: harus "0 transaksi baru" (tidak ada baris ganda).
5. Cek kolom B (subtotal berjalan) dan format tanggal pada baris baru.

## Catatan
- Makro membuat sheet tersembunyi `inbox_log` berisi ID yang sudah ditarik. Jangan dihapus, atau semua inbox ditarik ulang.
- Makro belum diuji di Excel Anda; hasil uji bagian 3 menentukan perlu tidaknya penyesuaian.

## K9: BBM motor dan token listrik (makro versi baru)
Bot kini menulis dua file inbox tambahan di folder yang sama: `Inbox BBM.tsv` (ke tabel `_bbmmotor`, sheet `BBM`) dan
`Inbox Listrik.tsv` (ke tabel `_listrik`, sheet `Listrik`). Makro lama hanya menarik `_transaction`, jadi **makro harus diganti**:

1. Alt+F11 -> buka modul `TarikInbox` di `VBAProject (PERSONAL.XLSB)` -> pilih semua (Ctrl+A) -> hapus.
2. Salin seluruh isi `docs/pribadi_inbox_macro.bas`, **kecuali baris pertama** (`Attribute VB_Name = ...`), tempel ke modul itu. Simpan.
3. Uji dulu di salinan: tutup file asli, buka salinannya (File -> Save As, mis. `Doku Keluarga TEST2.xlsx`; harus memuat tabel `_bbmmotor` dan
   `_listrik`). Kirim ke bot: `jago BP 92 Supra 40rb 3.05L km<km sekarang>` dan `meter 95,3`, lalu klik `TarikInbox`. Harus muncul:
   1 baris di `_transaction`, 1 di `_bbmmotor`, 1 di `_listrik` (kolom rumus Selisih/kWH/Jam ikut terisi). Klik lagi: 0 baris baru.
4. Bila lolos, tidak ada langkah lain: file asli ikut ditarik otomatis (saat dibuka dan tiap 5 menit).
- Tabel yang tidak ada di sebuah file, atau file inbox yang belum ada, dilewati tanpa pesan.
- Format pesan ada di `/bantuan`.
