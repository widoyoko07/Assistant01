"""K1: logika bot keuangan pribadi tanpa jaringan (pesan -> entri -> antrean)."""
import json
import re
import zipfile
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from ..common.money import UNCATEGORIZED, parse_amount, parse_entry, strip_amount
from . import fuel, listrik
from .classify import classify
from .dates import FutureDate, extract_date, only_date
from .fuel import FuelError, fmt_km
from .listrik import ListrikError, fmt_kwh
from .report import bbm_text, listrik_text, rekap_text, saldo_text

TZ = ZoneInfo("Asia/Jakarta")


def build_help(accounts=None):
    acc = ", ".join(accounts) if accounts else "-"
    return ("CARA MENCATAT\n"
            "- <akun> <keterangan> <nominal>, mis. cash bensin 50rb\n"
            "- awali + untuk pemasukan, mis. +jago gaji 5jt\n"
            "- pindah akun (jadi 2 baris): BSI ke JAGO pindah kas 2jt\n"
            "- subcategory sendiri di akhir (otomatis dihapus dari keterangan): jago internet magnolia 311575 Indihome. Tanpa itu, bot menebak dari kata di keterangan\n"
            "- tanggal mundur di awal/akhir: kemarin cash parkir 5rb, kamis ..., 29/10 ..., tgl 29 ..., 2 hari lalu ...\n"
            "- banyak sekaligus: satu baris satu transaksi. Baris pertama berisi tanggal saja (mis. kemarin) berlaku untuk semua baris\n"
            "- bensin Supra/Vario (masuk juga ke tabel BBM): jago BP 92 Supra 40rb 3.05L km39200.1 (harsat otomatis; atau tambah @16130). Motor lain: tanpa liter/km\n"
            "- token listrik + meter: jago token listrik 200rb 128,2kwh meter 141,14\n"
            "- bacaan meter saja: meter 95,3 (tambah jam 05.48 bila bukan sekarang)\n"
            "- nominal di atas Rp5 juta (bukan pindah kas) ditahan dulu: balas ya untuk mencatat, batal untuk membatalkan\n\n"
            "PERINTAH\n"
            "/terakhir [n] - tampilkan n catatan terakhir (bawaan 3)\n"
            "/saldo [akun] - saldo semua akun, atau satu akun + 5 mutasi terakhir\n"
            "/rekap [hari|minggu|bulan] - total masuk/keluar dan 5 pengeluaran terbesar (bawaan bulan; minggu mulai Senin)\n"
            "/bbm [supra|vario] [km sekarang] - kisaran km saat bensin habis\n"
            "/listrik [kWh sekarang] - perkiraan kapan sisa 20 kWh dan 0 kWh (hanya hitung)\n"
            "/cek <pesan> - simulasi: lihat hasil baca bot tanpa mencatat\n"
            "/bantuan - pesan ini\n\n"
            f"AKUN: {acc}")


class Ctx:
    """Konteks BBM/listrik: cfg = bagian pribadi di config.yaml, tables = pembaca _bbmmotor/_listrik (ledger.Tables).
    Tanpa Ctx, pesan tidak diperiksa untuk BBM/listrik."""

    def __init__(self, cfg=None, tables=None):
        self.cfg = cfg or {}
        self.motors = (self.cfg.get("bbm") or {}).get("motors") or {}
        self.tables = tables
        self.limit = self.cfg.get("confirm_over", 5_000_000) or 0   # K8f: nominal di atas ini perlu "ya"; 0/kosong = nonaktif
        self.pending = {}   # sender_id -> (teks, waktu pesan) yang menunggu konfirmasi

    def subcategories(self, categories):
        """Daftar subcategory sah: tabel _catagories di Excel; bila tidak terbaca, kunci kamus kata kunci di config."""
        read = getattr(self.tables, "subcategories", None)
        if read:
            try:
                subs = read()
                if subs:
                    return subs
            except (OSError, KeyError, ValueError, zipfile.BadZipFile):
                pass
        return list(categories)


def split_subcategory(note, subs):
    """(subcategory | None, keterangan tanpa subcategory). Subcategory yang ditulis di AKHIR keterangan (nama persis, huruf
    besar/kecil bebas, yang terpanjang didahulukan) dipakai dan dibuang dari keterangan; bila keterangan jadi kosong, tidak dipakai."""
    for sub in sorted(subs or [], key=len, reverse=True):
        m = re.search(rf"(?<!\w){re.escape(sub)}$", note.strip(), re.IGNORECASE)
        if m:
            rest = note.strip()[:m.start()].strip(" ,-:;")
            if rest:
                return sub, rest
    return None, note


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


def _line(e):
    if e.get("kind") == "meter":
        return f"{e['date']} meter {fmt_kwh(e['listrik']['sisa'])} kWh"
    return f"{e['date']} {e['type']} {rupiah(e['amount'])} [{e['category']}] {e['note']}"


def confirmation(e):
    if e.get("kind") == "meter":
        t = datetime.fromisoformat(e["listrik"]["t"])
        return f"Tercatat meter {listrik.fmt_time(t, t)}: {fmt_kwh(e['listrik']['sisa'])} kWh"
    cat = e["category"]
    warn = "\n(kategori belum dikenali; isi manual di Excel)" if cat == UNCATEGORIZED else ""
    acc = f"{e['account']} " if e.get("account") else ""
    extra = ""
    if e.get("bbm"):
        b = e["bbm"]
        extra += f"\n{b['motor']}: {listrik.dec(b['liter'], 3).rstrip('0').rstrip(',')} L @{rupiah(b['harsat'])}, km {fmt_km(b['km'])} (masuk juga ke tabel BBM)"
    if e.get("listrik"):
        li = e["listrik"]
        extra += f"\nMeter {fmt_kwh(li['sisa'])} kWh" + (f" (isi {fmt_kwh(li['topup'])} kWh)" if li.get("topup") else "") + " (masuk juga ke tabel listrik)"
    return f"Tercatat {e['date']}: {acc}{e['type']} {rupiah(e['amount'])} [{cat}] - {e['note']}{warn}{extra}"


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


def _stamp(on_date, hm, ts):
    when = listrik.stamp(on_date or ts.date(), hm, ts)
    if when.replace(tzinfo=TZ) > ts + timedelta(minutes=5):
        raise ListrikError(f"waktu {listrik.fmt_time(when)} belum terjadi")
    return when


def _meter_entry(reading, ts, sender_id, on_date, hm):
    listrik.check_sisa(reading)
    when = _stamp(on_date, hm, ts)
    return {"kind": "meter", "ts": ts.isoformat(timespec="seconds"), "date": when.date().isoformat(), "type": "meter",
            "category": "Listrik", "account": "", "amount": 0, "note": f"meter {fmt_kwh(reading)} kWh", "sender": sender_id,
            "listrik": {"t": when.isoformat(timespec="minutes"), "topup": None, "sisa": reading}}


def _km_reason(bbm, on_date, ctx, force):
    """Alasan menolak km yang tidak masuk akal dibanding riwayat motor itu; None bila wajar atau tidak bisa dicek."""
    if force or ctx.tables is None:
        return None
    try:
        rows = [r for r in ctx.tables.bbm() if r["motor"] == bbm["motor"]]
    except (OSError, KeyError, ValueError, zipfile.BadZipFile):
        return None
    reason = fuel.check_km(bbm["km"], on_date, rows, (ctx.cfg.get("bbm") or {}).get("max_km_jump", 1000))
    return f"{reason}. Cek km; bila memang benar, kirim ulang dengan tambahan kata 'paksa'." if reason else None


def _process(t, unix_ts, sender_id, categories, queue, accounts, lexicon, default_date=None, ctx=None):
    """Satu baris -> (entri | None, kode galat | None). Entri ditambahkan ke antrean bila berhasil."""
    ts = datetime.fromtimestamp(unix_ts, TZ)
    try:
        on_date, t = extract_date(t, ts.date())
    except FutureDate as e:
        return None, f"future:{e}"
    on_date = on_date or default_date
    hm = None
    try:
        if ctx and listrik.relevant(t):
            hm, t = listrik.extract_time(t)
            reading = listrik.parse_reading(t)
            if reading is not None:
                entry = _meter_entry(reading, ts, sender_id, on_date, hm)
                queue.add(entry)
                return [entry], None
    except ListrikError as e:
        return None, f"msg:{e}"
    pair, attempted = make_transfer(t, unix_ts, sender_id, accounts, on_date)
    if pair:
        for e in pair:
            queue.add(e)
        return pair, None
    if attempted:
        return None, "transfer"
    info = topup = None
    if ctx:
        try:
            topup, t = listrik.extract_topup(t)
            info, t = fuel.extract(t, ctx.motors)
        except (ListrikError, FuelError) as e:
            return None, f"msg:{e}"
    entry = make_entry(t, unix_ts, sender_id, categories, accounts, lexicon, on_date)
    if entry is None:
        return None, "amount"
    if accounts and entry["account"] is None:
        return None, "account"
    explicit = False
    if ctx:
        sub, note = split_subcategory(entry["note"], ctx.subcategories(categories))
        if sub:
            entry["category"], entry["note"], explicit = sub, note, True
    try:
        if info:
            if not explicit:
                entry["category"] = fuel.MOTOR_CATEGORY if info["motor"] else fuel.OTHER_CATEGORY
            entry["type"] = "pengeluaran"
            bbm = fuel.finish(info, entry["amount"])
            if bbm:
                reason = _km_reason(bbm, date.fromisoformat(entry["date"]), ctx, info["force"])
                if reason:
                    return None, f"msg:{reason}"
                entry["bbm"] = bbm
        if topup:
            listrik.check_sisa(topup["sisa"])
            when = _stamp(on_date, hm, ts)
            entry["listrik"] = {"t": when.isoformat(timespec="minutes"), "topup": topup["topup"], "sisa": topup["sisa"]}
    except (FuelError, ListrikError) as e:
        return None, f"msg:{e}"
    queue.add(entry)
    return [entry], None


def _error_single(code, accounts):
    if code.startswith("msg:"):
        return code[4:].rstrip(".") + ". Tidak dicatat."
    if code.startswith("future:"):
        return f"Tanggal {code[7:]} belum terjadi, tidak dicatat."
    return {
        "transfer": "Pindah kas tidak terbaca, tidak dicatat. Contoh: 'BSI ke JAGO pindah kas 2jt'.",
        "amount": "Nominal tidak terbaca, tidak dicatat. Ketik /bantuan untuk contoh format.",
        "account": "Akun belum disebut, tidak dicatat. Contoh: 'cash bensin 50rb'.\nAkun: " + ", ".join(accounts or []),
    }[code]


_REASON = {"transfer": "pindah kas tidak terbaca", "amount": "nominal tidak terbaca", "account": "akun belum disebut"}


def _reason(code):
    if code.startswith("msg:"):
        return code[4:]
    return f"tanggal {code[7:]} belum terjadi" if code.startswith("future:") else _REASON[code]


def _compact(entries):
    e = entries[0]
    if e.get("kind") == "meter":
        return _line(e)
    if len(entries) == 2:
        return f"{e['date']} pindah kas {rupiah(e['amount'])} {e['account']} -> {entries[1]['account']}"
    sign = "+" if e["type"] == "pemasukan" else "-"
    flag = " (kategori?)" if e["category"] == UNCATEGORIZED else ""
    return f"{e['date']} {e['account']} {sign}{rupiah(e['amount'])} [{e['category']}] {e['note']}{flag}"


_BULLET = re.compile(r"^(?:\d+[.)]\s+|[\u2022*\u00b7]\s+)")


def _lines(text):
    return [x for x in (_BULLET.sub("", l.strip()) for l in text.splitlines()) if x]


def _multi(lines, unix_ts, sender_id, categories, queue, accounts, lexicon, ctx=None):
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
        entries, err = _process(line, unix_ts, sender_id, categories, queue, accounts, lexicon, default_date, ctx)
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


YES = {"ya", "y", "iya", "ok", "oke", "benar", "betul"}
NO = {"batal", "tidak", "gak", "ga", "nggak", "no", "n"}
CONFIRM_TTL = 600  # detik


def _big_entries(text, unix_ts, sender_id, categories, accounts, lexicon, ctx):
    """Entri pengeluaran/pemasukan (bukan pindah kas/meter) di atas batas, dan jumlah baris transaksi; tanpa menyimpan."""
    lines = _lines(text)
    default_date = None
    try:
        default_date = only_date(lines[0], datetime.fromtimestamp(unix_ts, TZ).date()) if len(lines) > 1 else None
    except FutureDate:
        return [], 0
    if default_date:
        lines = lines[1:]
    big = []
    for line in lines:
        entries, err = _process(line, unix_ts, sender_id, categories, _Dry(), accounts, lexicon, default_date, ctx)
        if err:
            continue
        big += [e for e in entries if e.get("kind") != "meter" and e["category"] != "Pindah Kas" and e["amount"] > ctx.limit]
    return big, len(lines)


def _confirm_gate(t, unix_ts, sender_id, categories, accounts, lexicon, ctx):
    """K8f. (balasan | None, teks, waktu): balasan terisi = pesan ditahan/dibatalkan; None = lanjut proses teks itu."""
    word = t.lower().strip(" .!")
    pend = ctx.pending.pop(sender_id, None)
    if pend:
        if word in NO:
            return "Dibatalkan, tidak dicatat.", t, unix_ts
        if word in YES:
            if unix_ts - pend[1] > CONFIRM_TTL:
                return "Konfirmasi kedaluwarsa (lebih dari 10 menit). Kirim ulang pesannya.", t, unix_ts
            return None, pend[0], pend[1]  # sudah dikonfirmasi: proses pesan semula, tanpa cek lagi
    if not ctx.limit:
        return None, t, unix_ts
    big, n = _big_entries(t, unix_ts, sender_id, categories, accounts, lexicon, ctx)
    if not big:
        return None, t, unix_ts
    ctx.pending[sender_id] = (t, unix_ts)
    lines = ["Nominal besar, belum dicatat:"] + [f"- {e['date']} {e['account'] or ''} {e['type']} {rupiah(e['amount'])} [{e['category']}] {e['note']}".replace("  ", " ") for e in big]
    if n > len(big):
        lines.append(f"(+ {n - len(big)} baris lain di pesan yang sama ikut tertahan)")
    lines.append("Benar? Ketik ya untuk mencatat, batal untuk membatalkan (berlaku 10 menit).")
    return "\n".join(lines), t, unix_ts


def handle_message(text, unix_ts, sender_id, categories, queue, accounts=None, lexicon=None, ledger=None, ctx=None):
    """Balasan teks untuk satu pesan (perintah, satu transaksi, atau banyak baris); menambah antrean."""
    t = text.strip()
    m = re.match(r"^(?:/terakhir|(\d+)\s+terakhir)\s*(\d+)?$", t, re.IGNORECASE)
    if m:
        n = min(int(m.group(1) or m.group(2) or 3), 20)
        rows = queue.last(n)
        if not rows:
            return "Belum ada entri."
        return "\n".join(_line(e) for e in rows)
    cmd = re.match(r"^/(\w+)\s*(.*)$", t, re.DOTALL)
    if cmd:
        name, arg = cmd.group(1).lower(), cmd.group(2).strip()
        if name == "cek":
            if not arg or arg.startswith("/"):
                return "Pakai: /cek <pesan biasa>, mis. /cek cash parkir 5rb"
            res = handle_message(arg, unix_ts, sender_id, categories, _Dry(), accounts, lexicon, ctx=ctx)
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
        if name in ("bbm", "listrik"):
            if ctx is None or ctx.tables is None:
                return "Fitur ini butuh file Excel; LEDGER_PATH atau INBOX_PATH belum diatur di .env."
            now = datetime.fromtimestamp(unix_ts, TZ)
            try:
                if name == "bbm":
                    return bbm_text(ctx.tables.bbm(), ctx.cfg["bbm"], arg, now.date())
                return listrik_text(ctx.tables.listrik(), ctx.cfg["listrik"], arg, now.replace(tzinfo=None))
            except (OSError, KeyError, ValueError, zipfile.BadZipFile) as e:
                return f"Excel tidak bisa dibaca sekarang ({type(e).__name__}). Coba lagi sebentar."
        if name in ("bantuan", "help", "start"):
            return build_help(accounts)
        return "Perintah tidak dikenal. Ketik /bantuan."
    if ctx is not None and not isinstance(queue, _Dry):
        reply, t, unix_ts = _confirm_gate(t, unix_ts, sender_id, categories, accounts, lexicon, ctx)
        if reply:
            return reply
    lines = _lines(t)
    if len(lines) > 1:
        return _multi(lines, unix_ts, sender_id, categories, queue, accounts, lexicon, ctx)
    entries, err = _process(lines[0] if lines else t, unix_ts, sender_id, categories, queue, accounts, lexicon, None, ctx)
    if err:
        return _error_single(err, accounts)
    out = "\n".join(confirmation(e) for e in entries)
    if ctx and ctx.tables and entries[0].get("listrik"):  # sekalian perkiraan terbaru
        try:
            out += "\n\n" + listrik_text(ctx.tables.listrik(), ctx.cfg["listrik"], "", datetime.fromtimestamp(unix_ts, TZ).replace(tzinfo=None))
        except (OSError, KeyError, ValueError, zipfile.BadZipFile):
            pass
    return out
