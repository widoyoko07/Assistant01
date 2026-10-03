# Skema `decisions.json`

Ditulis Claude setelah melihat pratinjau (`/tmp/spr/preview/<id>.jpg`) dan caption di `inventory.json`.
Satu entri per foto, kunci = `id` dari inventory (urutan file, bukan nama file).

```json
{
  "p001": {"work": "Rebar Installation", "location": "Pump Station"},
  "p002": {"work": "Concreting", "location": "Slab Zone 1", "timestamp": true, "ts_box": [0.02, 0.88, 0.40, 0.99]},
  "p003": {"work": "", "location": "Pipe Gallery", "unsure": true, "question": "Pekerjaan di foto ini apa?"},
  "p004": {"work": "Welding", "location": "Tank", "crop_cuts_subject": true, "note": "pekerja di tepi kiri"}
}
```

## Field

| Field | Isi | Efek |
|---|---|---|
| `work` | Pekerjaan, English, Title Case (lihat `glossary.md`) | Kosong → `Unidentified Work` + `[CHECK]` |
| `location` | Lokasi, English, Title Case | Kosong → `Unidentified Location` + `[CHECK]` |
| `unsure` | `true` bila ragu | `[CHECK]` |
| `question` | Pertanyaan untuk user | Masuk daftar pertanyaan di akhir dry-run |
| `timestamp` | `true` bila ada overlay tanggal/jam/GPS/watermark kamera | Lihat tabel timestamp di bawah |
| `ts_box` | `[x0, y0, x1, y1]`, pecahan 0-1 dari lebar/tinggi foto asli | Dipakai skrip menilai aman tidaknya crop |
| `crop_cuts_subject` | `true` bila crop tengah 4:3 memotong objek utama | `[CHECK]`, disimpan tanpa crop di `check` |
| `note` | Catatan bebas | Masuk log.csv |

Foto tanpa entri di file ini otomatis `[CHECK]`.

## Penilaian timestamp (dihitung skrip)

| Kondisi | Hasil |
|---|---|
| `timestamp` tidak diisi | Tidak ada timestamp |
| `timestamp: true`, `ts_box` seluruhnya di luar area crop 4:3 | Hilang oleh crop → boleh masuk `final`, dicatat di log |
| `timestamp: true`, `ts_box` tumpang tindih dengan area crop | `[TS]` → `needs-cleaning` |
| `timestamp: true`, tanpa `ts_box` | `[TS]` → `needs-cleaning` |

Jangan inpaint/blur tanpa persetujuan user.
