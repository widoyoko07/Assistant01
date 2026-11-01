"""K1: logika bot keuangan pribadi tanpa jaringan (pesan -> entri -> antrean)."""
import json
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from ..common.money import UNCATEGORIZED, parse_amount, parse_entry, strip_amount
from .classify import classify
from .dates import FutureDate, extract_date

TZ = ZoneInfo("Asia/Jakarta")
HELP = ("Kirim: <akun> <keterangan> <nominal>, mis. 'cash bensin 50rb'. Awali '+' untuk pemasukan.\n"
        "Pindah kas: 'pindah kas BSI ke cash 100rb'.\n"
        "Tanggal mundur di awal/akhir pesan: 'kemarin cash parkir 5rb', 'kamis ...', '29/10 ...', 'tgl 29 ...', '2 hari lalu ...'.\n"
        "/terakhir [n] = tampilkan n entri terakhir (bawaan 3).\n"
        "/undo = batalkan entri terakhir yang belum masuk Excel.")


def rupiah(n):
    return "Rp" + f"{n:,}".replace(",", ".")


def find_account(text, accounts):
    """(akun, teks tanpa nama akun). Akun di awal pesan (setelah tanda +/-) didahulukan, baru di mana saja;
    nama terpanjang dicoba dulu ('Jago ART' sebelum 'JAGO')."""
    ordered = sorted(accounts or [], key=len, reverse=True)
    head = re.match(r"^([+-]?\s*)(.*)$", text.strip(), re.DOTALL)
    for acc in ordered:
        m = re.match(rf"{re.escape(acc)}(?!\w)\s*(.*)$", head.group(2), re.IGNORECASE | re.DOTALL)
        if m:
            return acc, (head.group(1) + m.group(1)).strip()
    for acc in ordered:
        m = re.search(rf"(?<!\w){re.escape(acc)}(?!\w)", text, re.IGNORECASE)
        if m:
            rest = (text[:m.start()] + " " + text[m.end():]).strip()
            return acc, re.sub(r"\s+", " ", rest)
    return None, text


def make_entry(text, unix_ts, sender_id, categories, accounts=None, lexicon=None, on_date=None):
    """Entri dari satu pesan, atau None bila nominal tidak terbaca.
    Tanggal memakai waktu pesan Telegram, bukan waktu diproses (penting saat bot baru menyala)."""
    account, text = find_account(text, accounts)
    parsed = parse_entry(text, categories)
    if not parsed["ok"]:
        return None
    ts = datetime.fromtimestamp(unix_ts, TZ)
    return {
        "ts": ts.isoformat(timespec="seconds"),
        "date": (on_date or ts.date()).isoformat(),
        "type": parsed["type"],
        "category": classify(text, categories, lexicon) if lexicon else parsed["category"],
        "account": account,
        "amount": parsed["amount"],
        "note": strip_amount(re.sub(r"^[+-]\s*", "", text.strip())),  # tanda +/- dan nominal bukan bagian deskripsi
        "sender": sender_id,
    }


def confirmation(e):
    cat = e["category"]
    warn = "\n(kategori belum dikenali; isi manual di Excel)" if cat == UNCATEGORIZED else ""
    acc = f"{e['account']} " if e.get("account") else ""
    return f"Tercatat {e['date']}: {acc}{e['type']} {rupiah(e['amount'])} [{cat}] - {e['note']}{warn}"


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

    @property
    def history(self):
        return self.path.with_name("history.jsonl")  # arsip semua entri, tidak dikosongkan saat sync

    def add(self, entry):
        rows = self.all()
        rows.append(entry)
        self._write(rows)
        with open(self.history, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def last(self, n):
        if not self.history.exists():  # entri lama sebelum arsip ada: isi dari antrean
            if not self.path.exists():
                return []
            self.history.write_text(self.path.read_text(encoding="utf-8"), encoding="utf-8")
        rows = [json.loads(x) for x in self.history.read_text(encoding="utf-8").splitlines() if x.strip()]
        return rows[-n:]

    def undo(self, sender):
        rows = self.all()
        for i in range(len(rows) - 1, -1, -1):
            if rows[i]["sender"] == sender:
                gone = rows.pop(i)
                self._write(rows)
                if self.history.exists():  # buang entri yang sama dari arsip
                    h = [x for x in self.history.read_text(encoding="utf-8").splitlines() if x.strip()]
                    for j in range(len(h) - 1, -1, -1):
                        if json.loads(h[j]) == gone:
                            del h[j]
                            break
                    self.history.write_text("".join(x + "\n" for x in h), encoding="utf-8")
                return gone
        return None

    def clear(self, sent_count):
        self._write(self.all()[sent_count:])


_TRANSFER = re.compile(r"^pindah kas\s+(.+?)\s+ke\s+(.+?)\s+(\S.*)$", re.IGNORECASE)


def make_transfer(text, unix_ts, sender_id, accounts, on_date=None):
    """'pindah kas BSI ke cash 100rb' -> dua entri (keluar dari asal, masuk ke tujuan), atau None."""
    m = _TRANSFER.match(text.strip().lstrip("+-").strip())
    if not m or not accounts:
        return None
    names = {a.lower(): a for a in accounts}
    src, dst = names.get(m.group(1).lower()), names.get(m.group(2).lower())
    amount = parse_amount(m.group(3))
    if not (src and dst and amount) or src == dst:
        return None
    ts = datetime.fromtimestamp(unix_ts, TZ)
    base = {"ts": ts.isoformat(timespec="seconds"), "date": (on_date or ts.date()).isoformat(), "category": "Pindah Kas",
            "amount": amount, "note": "Pindah kas", "sender": sender_id}
    return [dict(base, type="pengeluaran", account=src), dict(base, type="pemasukan", account=dst)]


def handle_message(text, unix_ts, sender_id, categories, queue, accounts=None, lexicon=None):
    """Balasan teks untuk satu pesan; menambah/menghapus antrean."""
    t = text.strip()
    if t.startswith("/undo"):
        gone = queue.undo(sender_id)
        return f"Dibatalkan: {gone['note']} ({rupiah(gone['amount'])})" if gone else \
            "Tidak ada entri tertunda untuk dibatalkan (yang sudah masuk Excel hapus manual)."
    m = re.match(r"^(?:/terakhir|(\d+)\s+terakhir)\s*(\d+)?$", t, re.IGNORECASE)
    if m:
        n = min(int(m.group(1) or m.group(2) or 3), 20)
        rows = queue.last(n)
        if not rows:
            return "Belum ada entri."
        return "\n".join(f"{e['date']} {e['type']} {rupiah(e['amount'])} [{e['category']}] {e['note']}" for e in rows)
    if t.startswith("/"):
        return HELP
    try:
        on_date, t = extract_date(t, datetime.fromtimestamp(unix_ts, TZ).date())
    except FutureDate as e:
        return f"Tanggal {e} belum terjadi, tidak dicatat."
    pair = make_transfer(t, unix_ts, sender_id, accounts, on_date)
    if pair:
        for e in pair:
            queue.add(e)
        return "\n".join(confirmation(e) for e in pair)
    if re.match(r"^[+-]?\s*pindah kas\b", t, re.IGNORECASE):  # transfer tidak valid: jangan dicatat setengah
        return "Pindah kas tidak terbaca, tidak dicatat. Contoh: 'pindah kas BSI ke cash 100rb'."
    entry = make_entry(t, unix_ts, sender_id, categories, accounts, lexicon, on_date)
    if entry is None:
        return "Nominal tidak terbaca, tidak dicatat.\n" + HELP
    if accounts and entry["account"] is None:
        return "Akun belum disebut, tidak dicatat. Contoh: 'cash bensin 50rb'.\nAkun: " + ", ".join(accounts)
    queue.add(entry)
    return confirmation(entry)
