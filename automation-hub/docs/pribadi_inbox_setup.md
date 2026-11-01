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
