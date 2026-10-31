"""M4b: butir Work Description terpilih ("x" di kolom Pakai, sheet WD Kandidat) -> foto, per (tanggal, SC).

Pasangan dibuat menurut urutan: butir ke-n ke foto ke-n pada laporan hari itu. Ini usulan awal; tabel hasilnya
dikoreksi pengguna. Butir tanpa foto dan foto sisa dilaporkan, tidak ditebak.
"""
import csv
from pathlib import Path

from ..common import config as cfgmod
from ..common.runlog import RunLog

HEADER = ["Tanggal", "SC", "No", "Butir Final", "Foto", "Catatan"]


def selected_items(xlsx, sheet="WD Kandidat"):
    """[(tanggal, SC, butir)] untuk baris ber-"x" di kolom Pakai. Butir = kolom 'Butir Final' bila terisi, selain itu 'Butir'."""
    import openpyxl
    wb = openpyxl.load_workbook(xlsx, read_only=True)
    rows = wb[sheet].iter_rows(values_only=True)
    head = list(next(rows))
    col = {h: i for i, h in enumerate(head) if h}
    out = []
    for r in rows:
        if str(r[col["Pakai"]] or "").strip().lower() != "x":
            continue
        final = r[col["Butir Final"]] if "Butir Final" in col else None
        out.append((r[col["Tanggal"]], r[col["SC"]], str(final or r[col["Butir"]]).strip()))
    return out


def manifest_photos(root=None):
    """{(tanggal, SC): [foto]} dari data/04_photos/manifest.csv, urutan laporan."""
    base = cfgmod.data_dir(root=root) / "04_photos"
    found = {}
    path = base / "manifest.csv"
    if not path.is_file():
        return found
    with open(path, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            if r["file"]:
                found.setdefault((r["date"], r["sc"]), []).append(str(base / r["date"].replace("-", "") / r["sc"] / r["file"]))
    return found


def pair(items, photos):
    """items: [(tanggal, SC, butir)], photos: {(tanggal, SC): [path]} -> baris tabel (lihat HEADER)."""
    by_key = {}
    for d, sc, text in items:
        by_key.setdefault((d, sc), []).append(text)
    rows = []
    for (d, sc), texts in sorted(by_key.items()):
        pics = photos.get((d, sc), [])
        for n, text in enumerate(texts):
            if n < len(pics):
                rows.append([d, sc, n + 1, text, pics[n], ""])
            else:
                rows.append([d, sc, n + 1, text, "", "tidak ada foto di ekspor" if not pics else "foto kurang dari butir"])
        for extra in pics[len(texts):]:
            rows.append([d, sc, "", "", extra, "foto sisa (belum dipasangkan)"])
    return rows


def write_csv(xlsx, root=None, log=None):
    log = log or RunLog("photo_pairs", root=root)
    rows = pair(selected_items(xlsx), manifest_photos(root))
    out_dir = cfgmod.data_dir(root=root) / "05_pairs"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "pasangan_foto_wd.csv"
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(HEADER)
        w.writerows(rows)
    missing = sum(1 for r in rows if r[3] and not r[4])
    if missing:
        log.warn(f"{missing} butir terpilih tanpa foto")
    log.done(f"{path} ({len(rows)} baris)")
    return path


if __name__ == "__main__":
    import sys
    write_csv(Path(sys.argv[1]))
