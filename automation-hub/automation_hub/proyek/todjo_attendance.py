"""M3b2: tabel absensi TODJO (hasil baca foto form) -> jumlah per blok dan role sheet ME.

Kolom CSV: Nama, Posisi, PT/CV, Tanda tangan (ya | tidak | ragu). Hanya 'ya' yang dihitung; 'ragu' dilaporkan
supaya pengguna memutuskan (ubah ke ya/tidak), tidak ditebak. Anita (HSE Tohoma, sudah resign) tidak boleh ada di tabel.
"""
import csv

from ..common import config as cfgmod

HEADER = ["Nama", "Posisi", "PT/CV", "Tanda tangan"]


def read(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return [r for r in csv.DictReader(f)]


def count(rows, cfg=None):
    """({(blok, role): n}, [baris ragu], [baris tak dikenal]). PT/CV dicocokkan tanpa huruf besar/kecil dan ejaan 'Dwidjo/Dwijo'."""
    t = (cfg or cfgmod.load())["todjo_attendance"]
    blocks = {k.lower(): v for k, v in t["blocks"].items()}
    roles = {k.lower(): v for k, v in t["role_map"].items()}
    counts, doubt, unknown = {}, [], []
    for r in rows:
        status = (r["Tanda tangan"] or "").strip().lower()
        if status == "ragu":
            doubt.append(r)
            continue
        if status != "ya":
            continue
        pt = r["PT/CV"].strip().lower().replace("dwijo", "dwidjo")
        block, role = blocks.get(pt), roles.get(r["Posisi"].strip().lower())
        if not block or not role:
            unknown.append(r)
            continue
        counts[(block, role)] = counts.get((block, role), 0) + 1
    return counts, doubt, unknown


def count_sc(rows, sc, cfg=None):
    """Seperti count() untuk SC dengan satu blok (WKP, BCP): aturan di config attendance_sc[sc]."""
    t = (cfg or cfgmod.load())["attendance_sc"][sc]
    roles = {k.lower(): v for k, v in t["role_map"].items()}
    counts, doubt, unknown = {}, [], []
    for r in rows:
        status = (r["Tanda tangan"] or "").strip().lower()
        if status == "ragu":
            doubt.append(r)
            continue
        if status != "ya":
            continue
        role = roles.get(r["Posisi"].strip().lower())
        if not role:
            unknown.append(r)
            continue
        counts[(t["block"], role)] = counts.get((t["block"], role), 0) + 1
    return counts, doubt, unknown
