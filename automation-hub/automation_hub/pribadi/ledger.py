"""K8g/K8h: baca buku besar (04.record) dari salinan lokal xlsx + entri yang belum masuk Excel (hanya baca).
Sumber: tabel di xlsx, baris inbox TSV yang belum tercatat di sheet inbox_log, dan antrean bot yang belum terkirim."""
import re
import shutil
import tempfile
import zipfile
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path
from xml.etree import ElementTree as ET

from .fuel import detect_motor
from .listrik import from_serial
from .records import NS, _shared, _sheet_path
from .sync import entry_id

EPOCH = date(1899, 12, 30)  # serial tanggal Excel


def _cells(row, ss):
    out = {}
    for c in row.findall("m:c", NS):
        col = re.match(r"[A-Z]+", c.get("r")).group()
        v = c.find("m:v", NS)
        if v is not None:
            out[col] = ss[int(v.text)] if c.get("t") == "s" else v.text
        elif c.find("m:is", NS) is not None:
            out[col] = "".join(t.text or "" for t in c.iter(f"{{{NS['m']}}}t"))
    return out


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


@contextmanager
def _book(xlsx):
    """(zip, shared strings) dari salinan sementara agar tidak bentrok dengan Excel yang sedang terbuka."""
    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / "ledger.xlsx"
        shutil.copyfile(xlsx, copy)
        with zipfile.ZipFile(copy) as z:
            yield z, _shared(z)


def _logged(z, ss, log_sheet="inbox_log"):
    try:
        return {_cells(r, ss).get("A") for r in ET.fromstring(z.read(_sheet_path(z, log_sheet))).iter(f"{{{NS['m']}}}row")}
    except StopIteration:  # sheet inbox_log belum ada
        return set()


def read_xlsx(xlsx, sheet="04.record", header_row=11, log_sheet="inbox_log"):
    """(baris transaksi, ID inbox yang sudah ditarik)."""
    with _book(xlsx) as (z, ss):
        rows = []
        for r in ET.fromstring(z.read(_sheet_path(z, sheet))).iter(f"{{{NS['m']}}}row"):
            if int(r.get("r")) <= header_row:
                continue
            c = _cells(r, ss)
            if not c.get("D") or not c.get("C"):
                continue
            rows.append({"date": EPOCH + timedelta(days=int(float(c["C"]))), "account": c["D"].strip(),
                         "desc": c.get("E", ""), "debit": _num(c.get("F")), "credit": _num(c.get("G")),
                         "sub": c.get("I", ""), "ctype": c.get("M", "")})
        return rows, _logged(z, ss, log_sheet)


def _col_index(letters):
    n = 0
    for ch in letters:
        n = n * 26 + ord(ch) - 64
    return n


def _col_letters(n):
    out = ""
    while n:
        n, rem = divmod(n - 1, 26)
        out = chr(65 + rem) + out
    return out


def read_table(z, ss, sheet, table):
    """[(nomor baris Excel, {nama kolom: nilai})] untuk Excel Table `table` di `sheet`; rentang dibaca dari definisi tabel."""
    ref = cols = None
    for n in z.namelist():
        if n.startswith("xl/tables/") and n.endswith(".xml"):
            root = ET.fromstring(z.read(n))
            if root.get("displayName") == table:
                ref, cols = root.get("ref"), [c.get("name") for c in root.find("m:tableColumns", NS)]
                break
    if ref is None:
        raise KeyError(f"tabel {table} tidak ada di file Excel")
    a, header_row, _, last_row = re.match(r"([A-Z]+)(\d+):([A-Z]+)(\d+)", ref).groups()
    letters = [_col_letters(_col_index(a) + i) for i in range(len(cols))]
    out = []
    for r in ET.fromstring(z.read(_sheet_path(z, sheet))).iter(f"{{{NS['m']}}}row"):
        n = int(r.get("r"))
        if int(header_row) < n <= int(last_row):
            c = _cells(r, ss)
            d = {name: c.get(let) for name, let in zip(cols, letters)}
            if any(v not in (None, "") for v in d.values()):
                out.append((n, d))
    return out


def read_inbox(path):
    """{ID: baris} dari inbox TSV; kosong bila file belum ada."""
    path = Path(path)
    if not path.exists():
        return {}
    out = {}
    for line in path.read_text(encoding="utf-8-sig").splitlines()[1:]:
        p = line.split("\t")
        if len(p) >= 7 and p[0]:
            out[p[0]] = {"date": date.fromisoformat(p[1]), "account": p[2], "desc": p[3], "debit": _num(p[4]),
                         "credit": _num(p[5]), "sub": p[6], "ctype": ""}
    return out


def _opt(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def bbm_row(n, d, motors):
    """Baris tabel _bbmmotor -> dict; None bila tanggal kosong."""
    if not d.get("TANGGAL"):
        return None
    note = d.get("KETERANGAN") or ""
    return {"date": EPOCH + timedelta(days=int(float(d["TANGGAL"]))), "motor": detect_motor(note, motors), "desc": note,
            "liter": _opt(d.get("LITER")), "harsat": _opt(d.get("HARSAT")), "km": _opt(d.get("KM")),
            "amount": _num(d.get("UANG KELUAR")), "row": n, "seq": n}


def read_tsv(path):
    """{ID: kolom} dari file inbox TSV (tanpa header); kosong bila file belum ada."""
    path = Path(path)
    if not path.exists():
        return {}
    out = {}
    for line in path.read_text(encoding="utf-8-sig").splitlines()[1:]:
        p = line.split("\t")
        if p and p[0]:
            out[p[0]] = p
    return out


def bbm_from_tsv(p, motors, seq):
    if len(p) < 9:
        return None
    return {"date": date.fromisoformat(p[1]), "motor": detect_motor(p[5], motors), "desc": p[5], "liter": _opt(p[6]),
            "harsat": _opt(p[7]), "km": _opt(p[8]), "amount": _num(p[3]), "row": None, "seq": 10**9 + seq}


def bbm_from_entry(e, motors, seq):
    b = e["bbm"]
    return {"date": date.fromisoformat(e["date"]), "motor": b["motor"], "desc": e["note"], "liter": b["liter"],
            "harsat": b["harsat"], "km": b["km"], "amount": e["amount"], "row": None, "seq": 10**9 + seq}


def listrik_row(d):
    """Baris tabel _listrik -> pembacaan; None bila waktu atau sisa kosong."""
    t, s = d.get("Waktu"), _opt(d.get("kWH Sisa"))
    return None if not t or s is None else {"t": from_serial(t), "topup": _opt(d.get("kWH Topup")), "sisa": s}


def listrik_from_tsv(p):
    if len(p) < 4:
        return None
    return {"t": datetime.strptime(p[1], "%Y-%m-%d %H:%M"), "topup": _opt(p[2]), "sisa": _opt(p[3])}


def listrik_from_entry(e):
    li = e["listrik"]
    return {"t": datetime.fromisoformat(li["t"]), "topup": li.get("topup"), "sisa": li["sisa"]}


def from_entry(e):
    spend = e["type"] == "pengeluaran"
    return {"date": date.fromisoformat(e["date"]), "account": e.get("account") or "", "desc": e["note"],
            "debit": e["amount"] if spend else 0, "credit": 0 if spend else e["amount"], "sub": e["category"], "ctype": ""}


def load(xlsx, inbox_path, queue_entries):
    """(semua baris, jumlah baris yang belum masuk Excel)."""
    rows, logged = read_xlsx(xlsx)
    inbox = read_inbox(inbox_path) if inbox_path else {}
    pending = [r for i, r in inbox.items() if i not in logged]
    seen = set(inbox) | logged
    pending += [from_entry(e) for e in queue_entries if e.get("kind") != "meter" and entry_id(e) not in seen]
    return rows + pending, len(pending)


class Tables:
    """Pembaca _bbmmotor dan _listrik: isi tabel di Excel + baris inbox yang belum ditarik makro + antrean bot."""

    def __init__(self, xlsx, inbox_dir, cfg, queue):
        self.xlsx, self.dir, self.cfg, self.queue = Path(xlsx), Path(inbox_dir), cfg, queue
        self.motors = cfg["bbm"]["motors"]
        self._subs = None  # (waktu ubah file, daftar subcategory)

    def subcategories(self):
        """Kolom Subcategory tabel _catagories (sheet 02.category); disimpan sementara selama file tidak berubah."""
        c = self.cfg.get("category_table") or {"sheet": "02.category", "table": "_catagories"}
        mtime = self.xlsx.stat().st_mtime
        if self._subs and self._subs[0] == mtime:
            return self._subs[1]
        with _book(self.xlsx) as (z, ss):
            rows = read_table(z, ss, c["sheet"], c["table"])
        subs = [r["Subcategory"] for _, r in rows if r.get("Subcategory")]
        self._subs = (mtime, subs)
        return subs

    def bbm(self):
        """Isian BBM motor (semua motor), urut: Excel, inbox, antrean."""
        c = self.cfg["bbm"]
        with _book(self.xlsx) as (z, ss):
            table, log = read_table(z, ss, c["sheet"], c["table"]), _logged(z, ss)
        rows = [r for n, d in table if (r := bbm_row(n, d, self.motors))]
        tsv = read_tsv(self.dir / self.cfg["inbox_bbm_file"])
        for i, (rid, p) in enumerate(tsv.items()):
            if rid not in log and (r := bbm_from_tsv(p, self.motors, i)):
                rows.append(r)
        seen = set(tsv) | log
        rows += [bbm_from_entry(e, self.motors, 5000 + i) for i, e in enumerate(self.queue.all())
                 if e.get("bbm") and entry_id(e) + "b" not in seen]
        return rows

    def listrik(self):
        """Pembacaan meter dalam urutan tabel: Excel, inbox, antrean."""
        c = self.cfg["listrik"]
        with _book(self.xlsx) as (z, ss):
            table, log = read_table(z, ss, c["sheet"], c["table"]), _logged(z, ss)
        rows = [r for _, d in table if (r := listrik_row(d))]
        tsv = read_tsv(self.dir / self.cfg["inbox_listrik_file"])
        rows += [r for rid, p in tsv.items() if rid not in log and (r := listrik_from_tsv(p))]
        seen = set(tsv) | log
        rows += [listrik_from_entry(e) for e in self.queue.all() if e.get("listrik") and entry_id(e) + "l" not in seen]
        return rows
