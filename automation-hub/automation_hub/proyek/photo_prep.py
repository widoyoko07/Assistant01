"""M4c: siapkan foto untuk DPR: rasio 4:3 dan tanpa cap waktu/lokasi aplikasi kamera.

Cap waktu dicari dengan OCR (tesseract) pada kata khas cap (hari, bulan, jam, Jakarta, Kecamatan, ...). Bila cap ada di
bagian bawah foto, bagian itu dipotong lalu foto dipotong ke 4:3 di tengah. Bila cap ada tetapi tidak bisa dibuang dengan
memotong bawah, foto tetap dipotong ke 4:3 dan nama file diberi akhiran " TS".
"""
import re
import subprocess
import tempfile
from pathlib import Path

RATIO = 4 / 3
MAX_W = 1600
_WORD = re.compile(r"^(okt|oktober|nov|november|senin|selasa|rabu|kamis|jumat|sabtu|minggu|jakarta|kecamatan|penjaringan|"
                   r"jalan|indonesia|pluit|utara|khusus|daerah|ibukota|waduk|selatan|\d{1,2}[.:]\d{2}[.:]\d{2})[,.:]?$", re.I)
BOTTOM_FROM = 0.55     # cap dianggap "di bawah" bila kata cap paling atas ada di bawah 55% tinggi foto


def stamp_top(img):
    """y paling atas kata cap (piksel) atau None bila tidak ada cap. Perlu >= 3 kata cap agar teks lain tidak salah dikira cap."""
    with tempfile.TemporaryDirectory() as t:
        p = Path(t) / "a.png"
        img.save(p)
        out = subprocess.run(["tesseract", str(p), "stdout", "tsv"], capture_output=True, text=True, timeout=120).stdout
    ys = []
    for line in out.splitlines()[1:]:
        c = line.split("\t")
        if len(c) >= 12 and c[11].strip() and _WORD.match(c[11].strip()):
            try:
                if float(c[10]) >= 30:
                    ys.append(int(c[7]))
            except ValueError:
                pass
    return min(ys) if len(ys) >= 3 else None


def crop_box(w, h):
    """Kotak (l, t, r, b) 4:3 di tengah dalam gambar w x h."""
    if w / h > RATIO:
        nw = round(h * RATIO)
        return ((w - nw) // 2, 0, (w - nw) // 2 + nw, h)
    nh = round(w / RATIO)
    return (0, (h - nh) // 2, w, (h - nh) // 2 + nh)


def prepare(img):
    """(gambar 4:3, cap_tersisa). cap_tersisa True bila cap ada tetapi tidak bisa dibuang."""
    top = stamp_top(img)
    remaining = False
    if top is not None:
        if top > img.height * BOTTOM_FROM:
            img = img.crop((0, 0, img.width, max(int(top - img.height * 0.01), 1)))
        else:
            remaining = True
    img = img.crop(crop_box(*img.size))
    if img.width > MAX_W:
        img = img.resize((MAX_W, round(MAX_W / RATIO)))
    return img, remaining
