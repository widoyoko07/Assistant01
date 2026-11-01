"""K8g/K8h: baca buku besar (04.record) dari salinan lokal xlsx + entri yang belum masuk Excel (hanya baca).
Sumber: tabel di xlsx, baris inbox TSV yang belum tercatat di sheet inbox_log, dan antrean bot yang belum terkirim."""
import re
import shutil
import tempfile
import zipfile
from datetime import date, timedelta
from pathlib import Path
from xml.etree import ElementTree as ET

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


def read_xlsx(xlsx, sheet="04.record", header_row=11, log_sheet="inbox_log"):
    """(baris transaksi, ID inbox yang sudah ditarik). Dibaca dari salinan sementara agar tidak bentrok dengan Excel."""
    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / "ledger.xlsx"
        shutil.copyfile(xlsx, copy)
        z = zipfile.ZipFile(copy)
        ss = _shared(z)
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
        try:
            logged = {_cells(r, ss).get("A") for r in ET.fromstring(z.read(_sheet_path(z, log_sheet))).iter(f"{{{NS['m']}}}row")}
        except StopIteration:  # sheet inbox_log belum ada
            logged = set()
        return rows, logged


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
    pending += [from_entry(e) for e in queue_entries if entry_id(e) not in seen]
    return rows + pending, len(pending)
