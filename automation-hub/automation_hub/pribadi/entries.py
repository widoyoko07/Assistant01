"""K1: logika bot keuangan pribadi tanpa jaringan (pesan -> entri -> antrean)."""
import json
import re
import zipfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from ..common.money import UNCATEGORIZED, parse_amount, parse_entry, strip_amount
from .classify import classify
from .dates import FutureDate, extract_date, only_date
from .report import rekap_text, saldo_text

TZ = ZoneInfo("Asia/Jakarta")


def build_help(accounts=None):
    acc = ", ".join(accounts) if accounts else "-"
    return ("CARA MENCATAT\n"
            "- <akun> <keterangan> <nominal>, mis. cash bensin 50rb\n"
            "- awali + untuk pemasukan, mis. +jago gaji 5jt\n"
            "- pindah akun (jadi 2 baris): BSI ke JAGO pindah kas 2jt\n"
            "- tanggal mundur di awal/akhir: kemarin cash parkir 5rb, kamis ..., 29/10 ..., tgl 29 ..., 2 hari lalu ...\n"
            "- banyak sekaligus: satu baris satu transaksi. Baris pertama berisi tanggal saja (mis. kemarin) berlaku untuk semua baris\n\n"
            "PERINTAH\n"
            "/terakhir [n] - tampilkan n catatan terakhir (bawaan 3)\n"
            "/saldo [akun] - saldo semua akun, atau satu akun + 5 mutasi terakhir\n"
            "/rekap [hari|minggu|bulan] - total masuk/keluar dan 5 pengeluaran terbesar (bawaan bulan; minggu mulai Senin)\n"
            "/cek <pesan> - simulasi: lihat hasil baca bot tanpa mencatat\n"
            "/bantuan - pesan ini\n\n"
            f"AKUN: {acc}")


def rupiah(n):
    return "Rp" + f"{n:,}".replace(",", ".")


def _has_description(rest):
    return bool(strip_amount(rest, fallback=False).strip(" +-"))


def find_account(text, accounts):
    """(akun, teks tanpa nama akun). Akun di awal pesan (setelah tanda +/-) didahulukan, baru di mana saja.
    Nama terpanjang dicoba dulu ('Jago ART' sebelum 'JAGO'), kecuali bila itu tidak menyisakan deskripsi
    sedangkan akun yang lebih pendek menyisakannya ('jago ART 150001' = akun JAGO, deskripsi ART)."""
    ordered = sorted(accounts or [], key=len, reverse=True)
    head = re.match(r"^([+-]?\s*)(.*)$", text.strip(), re.DOTALL)
    found = []
    for acc in ordered:
        m = re.match(rf"{re.escape(acc)}(?!\w)\s*(.*)$", head.group(2), re.IGNORECASE | re.DOTALL)
        if m:
            found.append((acc, (head.group(1) + m.group(1)).strip()))
    if found:
        return next((f for f in found if _has_description(f[1])), found[0])
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
        "note": strip_amount(re.sub(r"^[+-]\s*", "", text.strip()), fallback=False),  # tanda +/- dan nominal bukan bagian deskripsi
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

    def clear(self, sent_count):
        self._write(self.all()[sent_count:])


def make_transfer(text, unix_ts, sender_id, accounts, on_date=None):
    """'BSI ke JAGO pindah kas 2jt' atau 'pindah kas BSI ke JAGO 2jt' -> (dua entri, True);
    pola transfer tetapi tidak valid -> (None, True); bukan transfer -> (None, False)."""
    t = text.strip().lstrip("+-").strip()
    starts = bool(re.match(r"^pindah kas\b", t, re.IGNORECASE))
    if not accounts:
        return None, starts
    names = "|".join(re.escape(a) for a in sorted(accounts, key=len, reverse=True))
    m = re.match(rf"^(?:pindah kas\s+)?({names})\s+ke\s+({names})(?!\w)\s*(.*)$", t, re.IGNORECASE | re.DOTALL)
    if not m:
        return None, starts
    canon = {a.lower(): a for a in accounts}
    src, dst = canon[m.group(1).lower()], canon[m.group(2).lower()]
    amount = parse_amount(re.sub(r"\bpindah kas\b", " ", m.group(3), flags=re.IGNORECASE))
    if not amount or src == dst:
        return None, True
    ts = datetime.fromtimestamp(unix_ts, TZ)
    base = {"ts": ts.isoformat(timespec="seconds"), "date": (on_date or ts.date()).isoformat(), "category": "Pindah Kas",
            "amount": amount, "note": "Pindah kas", "sender": sender_id}
    return [dict(base, type="pengeluaran", account=src), dict(base, type="pemasukan", account=dst)], True


def _process(t, unix_ts, sender_id, categories, queue, accounts, lexicon, default_date=None):
    """Satu baris -> (entri | None, kode galat | None). Entri ditambahkan ke antrean bila berhasil."""
    try:
        on_date, t = extract_date(t, datetime.fromtimestamp(unix_ts, TZ).date())
    except FutureDate as e:
        return None, f"future:{e}"
    on_date = on_date or default_date
    pair, attempted = make_transfer(t, unix_ts, sender_id, accounts, on_date)
    if pair:
        for e in pair:
            queue.add(e)
        return pair, None
    if attempted:
        return None, "transfer"
    entry = make_entry(t, unix_ts, sender_id, categories, accounts, lexicon, on_date)
    if entry is None:
        return None, "amount"
    if accounts and entry["account"] is None:
        return None, "account"
    queue.add(entry)
    return [entry], None


def _error_single(code, accounts):
    if code.startswith("future:"):
        return f"Tanggal {code[7:]} belum terjadi, tidak dicatat."
    return {
        "transfer": "Pindah kas tidak terbaca, tidak dicatat. Contoh: 'BSI ke JAGO pindah kas 2jt'.",
        "amount": "Nominal tidak terbaca, tidak dicatat. Ketik /bantuan untuk contoh format.",
        "account": "Akun belum disebut, tidak dicatat. Contoh: 'cash bensin 50rb'.\nAkun: " + ", ".join(accounts or []),
    }[code]


_REASON = {"transfer": "pindah kas tidak terbaca", "amount": "nominal tidak terbaca", "account": "akun belum disebut"}


def _reason(code):
    return f"tanggal {code[7:]} belum terjadi" if code.startswith("future:") else _REASON[code]


def _compact(entries):
    e = entries[0]
    if len(entries) == 2:
        return f"{e['date']} pindah kas {rupiah(e['amount'])} {e['account']} -> {entries[1]['account']}"
    sign = "+" if e["type"] == "pemasukan" else "-"
    flag = " (kategori?)" if e["category"] == UNCATEGORIZED else ""
    return f"{e['date']} {e['account']} {sign}{rupiah(e['amount'])} [{e['category']}] {e['note']}{flag}"


_BULLET = re.compile(r"^(?:\d+[.)]\s+|[\u2022*\u00b7]\s+)")


def _lines(text):
    return [x for x in (_BULLET.sub("", l.strip()) for l in text.splitlines()) if x]


def _multi(lines, unix_ts, sender_id, categories, queue, accounts, lexicon):
    base = datetime.fromtimestamp(unix_ts, TZ).date()
    default_date = None
    try:
        default_date = only_date(lines[0], base)
    except FutureDate as e:
        return f"Tanggal {e} belum terjadi, tidak ada yang dicatat."
    if default_date:
        lines = lines[1:]
    if not lines:
        return "Tidak ada transaksi di bawah tanggal itu."
    out, ok = [], 0
    for line in lines:
        entries, err = _process(line, unix_ts, sender_id, categories, queue, accounts, lexicon, default_date)
        if err:
            out.append(f"GAGAL: {line} -> {_reason(err)}")
        else:
            ok += 1
            out.append(f"OK: {_compact(entries)}")
    head = f"Tercatat {ok} dari {len(lines)} baris" + ("" if ok == len(lines) else ". Kirim ulang yang GAGAL.")
    text = head + "\n" + "\n".join(out)
    return text if len(text) <= 3800 else text[:3800] + "\n..."


class _Dry:
    """Antrean palsu untuk /cek: menampung entri tanpa menyimpan."""

    def add(self, entry):
        pass

    def last(self, n):
        return []


def handle_message(text, unix_ts, sender_id, categories, queue, accounts=None, lexicon=None, ledger=None):
    """Balasan teks untuk satu pesan (perintah, satu transaksi, atau banyak baris); menambah antrean."""
    t = text.strip()
    m = re.match(r"^(?:/terakhir|(\d+)\s+terakhir)\s*(\d+)?$", t, re.IGNORECASE)
    if m:
        n = min(int(m.group(1) or m.group(2) or 3), 20)
        rows = queue.last(n)
        if not rows:
            return "Belum ada entri."
        return "\n".join(f"{e['date']} {e['type']} {rupiah(e['amount'])} [{e['category']}] {e['note']}" for e in rows)
    cmd = re.match(r"^/(\w+)\s*(.*)$", t, re.DOTALL)
    if cmd:
        name, arg = cmd.group(1).lower(), cmd.group(2).strip()
        if name == "cek":
            if not arg or arg.startswith("/"):
                return "Pakai: /cek <pesan biasa>, mis. /cek cash parkir 5rb"
            res = handle_message(arg, unix_ts, sender_id, categories, _Dry(), accounts, lexicon)
            return "SIMULASI (tidak dicatat)\n" + res.replace("Tercatat", "Akan dicatat")
        if name in ("saldo", "rekap"):
            if ledger is None:
                return "Fitur ini butuh file Excel; LEDGER_PATH atau INBOX_PATH belum diatur di .env."
            try:
                rows, pending = ledger()
            except (OSError, KeyError, ValueError, zipfile.BadZipFile) as e:
                return f"Excel tidak bisa dibaca sekarang ({type(e).__name__}). Coba lagi sebentar."
            today = datetime.fromtimestamp(unix_ts, TZ).date()
            return saldo_text(rows, pending, accounts, arg, today) if name == "saldo" else rekap_text(rows, pending, arg, today)
        if name in ("bantuan", "help", "start"):
            return build_help(accounts)
        return "Perintah tidak dikenal. Ketik /bantuan."
    lines = _lines(t)
    if len(lines) > 1:
        return _multi(lines, unix_ts, sender_id, categories, queue, accounts, lexicon)
    entries, err = _process(lines[0] if lines else t, unix_ts, sender_id, categories, queue, accounts, lexicon)
    if err:
        return _error_single(err, accounts)
    return "\n".join(confirmation(e) for e in entries)
