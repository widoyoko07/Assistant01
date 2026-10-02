# Format schema.json dan records.json

## schema.json

```json
{
  "sheet": "Nota Material",
  "number_locale": "id",
  "dedupe_key": ["tanggal", "uraian"],
  "totals": ["jumlah"],
  "no_meta": false,
  "columns": [
    {"key": "tanggal", "header": "Tanggal", "type": "date", "required": true},
    {"key": "uraian",  "header": "Uraian",  "type": "text", "required": true, "width": 32},
    {"key": "qty",     "header": "Qty",     "type": "integer", "min": 0},
    {"key": "harga",   "header": "Harga Satuan", "type": "number", "format": "#,##0"},
    {"key": "status",  "header": "Status", "type": "enum", "enum": ["Hadir", "Izin", "Sakit"]},
    {"key": "kode",    "header": "Kode", "type": "text", "pattern": "[A-Z]{2}-\\d{4}"}
  ]
}
```

| Kunci | Arti |
|---|---|
| `type` | `text` (default), `integer`, `number`, `date`, `enum` |
| `required` | kosong = ditandai |
| `min` / `max` | rentang angka; di luar rentang = ditandai |
| `enum` | daftar nilai sah; ejaan mirip (>= 85%) dikoreksi dan ditandai, yang lain hanya ditandai |
| `pattern` | regex (fullmatch) untuk teks |
| `format` | format angka/tanggal Excel; default `#,##0` (integer), `#,##0.00` (number), `dd-mmm-yyyy` (date) |
| `number_locale` | `id` (1.234,5), `en` (1,234.5), `auto` (tebak; `1.234` dibaca ribuan) |
| `dedupe_key` | kombinasi kolom penentu duplikat; duplikat ditandai, tidak dihapus |
| `totals` | kolom yang diberi baris Total berumus SUM (jalankan recalc.py) |
| `no_meta` | true = tanpa kolom Sumber/Status (mode tambah ke template selalu tanpa) |
| `header` | harus sama dengan teks header di Excel user bila memakai `--append-to` |

## records.json

```json
[
  {"tanggal": "28/09/2026", "uraian": "Semen 50kg", "qty": "120", "harga": "68.500",
   "_source": "nota_scan.pdf", "_page": 1, "_conf": 93,
   "_flags": {"qty": "buram, terbaca 120 atau 128"}}
]
```

`_source`, `_page`: asal baris. `_conf`: keyakinan OCR baris (0-100), di bawah `--conf-threshold` (default 75) baris ditandai.
`_flags`: sel yang Anda ragukan, `{key: alasan}`. Nilai tak terbaca = `null`, jangan ditebak.

## Contoh skema cepat

- **Daftar hadir**: `no` integer, `nama` text required, `jabatan` text, `perusahaan` text, `hadir` enum. Kontrol: `--control no=<jumlah orang tertulis>` bila ada kolom `no`, atau jumlah baris.
- **Nota/faktur**: `tanggal` date, `uraian` text, `qty` integer, `harga` number, `jumlah` number (totals). `--control jumlah=<total di nota>`.
- **Formulir 1 halaman satu record**: satu objek per halaman; kolom = isian formulir; `_page` = nomor halaman.
