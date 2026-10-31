"""K1: logika bot keuangan pribadi tanpa jaringan (pesan -> entri -> antrean)."""
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from ..common.money import UNCATEGORIZED, parse_entry

TZ = ZoneInfo("Asia/Jakarta")
HELP = ("Kirim: <keterangan> <nominal>, mis. 'bensin 50rb'. Awali '+' untuk pemasukan.\n"
        "/undo = batalkan entri terakhir yang belum masuk Excel.")


def rupiah(n):
    return "Rp" + f"{n:,}".replace(",", ".")


def make_entry(text, unix_ts, sender_id, categories):
    """Entri dari satu pesan, atau None bila nominal tidak terbaca.
    Tanggal memakai waktu pesan Telegram, bukan waktu diproses (penting saat bot baru menyala)."""
    parsed = parse_entry(text, categories)
    if not parsed["ok"]:
        return None
    ts = datetime.fromtimestamp(unix_ts, TZ)
    return {
        "ts": ts.isoformat(timespec="seconds"),
        "date": ts.date().isoformat(),
        "type": parsed["type"],
        "category": parsed["category"],
        "amount": parsed["amount"],
        "note": text.strip(),
        "sender": sender_id,
    }


def confirmation(e):
    cat = e["category"]
    warn = "\n(kategori belum dikenali; isi manual di Excel)" if cat == UNCATEGORIZED else ""
    return f"Tercatat {e['date']}: {e['type']} {rupiah(e['amount'])} [{cat}] - {e['note']}{warn}"


class Queue:
    """Antrean entri yang belum ditulis ke Excel (jsonl). Entri hilang hanya bila sudah terkirim."""

    def __init__(self, path):
        self.path = Path(path)

    def all(self):
        if not self.path.exists():
            return []
        return [json.loads(x) for x in self.path.read_text(encoding="utf-8").splitlines() if x.strip()]

    def _write(self, rows):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")

    def add(self, entry):
        rows = self.all()
        rows.append(entry)
        self._write(rows)

    def undo(self, sender):
        rows = self.all()
        for i in range(len(rows) - 1, -1, -1):
            if rows[i]["sender"] == sender:
                gone = rows.pop(i)
                self._write(rows)
                return gone
        return None

    def clear(self, sent_count):
        self._write(self.all()[sent_count:])


def handle_message(text, unix_ts, sender_id, categories, queue):
    """Balasan teks untuk satu pesan; menambah/menghapus antrean."""
    t = text.strip()
    if t.startswith("/undo"):
        gone = queue.undo(sender_id)
        return f"Dibatalkan: {gone['note']} ({rupiah(gone['amount'])})" if gone else \
            "Tidak ada entri tertunda untuk dibatalkan (yang sudah masuk Excel hapus manual)."
    if t.startswith("/"):
        return HELP
    entry = make_entry(t, unix_ts, sender_id, categories)
    if entry is None:
        return "Nominal tidak terbaca, tidak dicatat.\n" + HELP
    queue.add(entry)
    return confirmation(entry)
