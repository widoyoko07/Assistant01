#!/usr/bin/env python3
"""PDF Attendance (teks/scan) -> file teks '<SC>_<YYYYMMDD>_Attendance.txt' berformat 'Nama | Role | PT/CV'.

Pakai:  python3 pdf_to_att.py <file.pdf> --out /tmp/mp_att/WME_20260930_Attendance.txt [--dpi 300] [--pages-dir /tmp/pages]
Tabel dikenali dari kepala kolom (Name/Nama, Position/Jabatan, PT/CV, Signature/TTD); layout dua tabel berdampingan
per halaman didukung. Selalu menyertakan pemeriksaan: nomor urut yang hilang (halaman/baris tak terbaca) dan
keyakinan OCR per halaman. Tulisan tangan (mis. BCP) tidak bisa dibaca tesseract: skrip menandainya dan
--pages-dir menyimpan gambar halaman agar Claude membacanya secara visual.
Syarat: file PDF harus ada di sandbox (unggah ke chat) atau di komputer lokal dengan poppler + tesseract."""
import argparse, glob, os, re, statistics, subprocess, sys, tempfile

NAME, POS, PT, SIG, NO = ("name", "nama"), ("position", "posisi", "jabatan", "role"), ("pt", "pt/cv", "cv", "perusahaan"), ("signature", "sign", "ttd", "paraf", "tanda"), ("no", "no.", "nomor")

def words_from_text_layer(pdf, pn):
    import pdfplumber
    with pdfplumber.open(pdf) as doc:
        pg = doc.pages[pn]
        ws = [dict(t=w["text"], x=w["x0"], y=w["top"], w=w["x1"] - w["x0"], h=w["bottom"] - w["top"], c=100.0) for w in pg.extract_words()]
        return ws, float(pg.width)

def words_from_ocr(img):
    import pytesseract, cv2
    im = cv2.imread(img, cv2.IMREAD_GRAYSCALE)
    _, im = cv2.threshold(im, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    d = pytesseract.image_to_data(im, lang="eng", config="--psm 6", output_type=pytesseract.Output.DICT)
    ws = [dict(t=d["text"][i].strip(), x=d["left"][i], y=d["top"][i], w=d["width"][i], h=d["height"][i], c=float(d["conf"][i]))
          for i in range(len(d["text"])) if d["text"][i].strip() and float(d["conf"][i]) >= 0]
    return ws, float(im.shape[1])

def parse_half(ws, x0, x1):
    ws = [w for w in ws if x0 <= w["x"] + w["w"] / 2 < x1]
    hdr = {}
    for w in ws:
        t = w["t"].lower().strip(".:|")
        for key, names in (("name", NAME), ("pos", POS), ("pt", PT), ("sig", SIG), ("no", NO)):
            if t in names and key not in hdr: hdr[key] = w
    if "name" not in hdr or "pos" not in hdr: return None
    top = hdr["name"]["y"] + hdr["name"]["h"]
    cut = lambda k: hdr[k]["x"] - 8 if k in hdr else None
    nx, px, tx, sx = cut("name"), cut("pos"), cut("pt"), cut("sig")
    body = sorted([w for w in ws if w["y"] > top], key=lambda w: (w["y"], w["x"]))
    if not body: return []
    tol = 0.6 * statistics.median(w["h"] for w in body)
    rows, cur = [], [body[0]]
    for w in body[1:]:
        if abs(w["y"] - cur[-1]["y"]) <= tol: cur.append(w)
        else: rows.append(cur); cur = [w]
    rows.append(cur)
    out = []
    for r in rows:
        r.sort(key=lambda w: w["x"])
        num = next((int(w["t"]) for w in r if w["x"] < nx and w["t"].isdigit()), None)
        seg = lambda a, b: " ".join(w["t"] for w in r if (a is None or w["x"] >= a) and (b is None or w["x"] < b))
        name = seg(nx, px); role = seg(px, tx or sx); pt = seg(tx, sx) if tx else ""
        if num is not None and name.strip():
            out.append(dict(no=num, name=name.strip(), role=role.strip(), pt=pt.strip(), conf=statistics.mean(w["c"] for w in r)))
    return out

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("pdf"); ap.add_argument("--out", required=True)
    ap.add_argument("--dpi", type=int, default=300); ap.add_argument("--pages-dir")
    a = ap.parse_args()
    tmp = a.pages_dir or tempfile.mkdtemp(); os.makedirs(tmp, exist_ok=True)
    subprocess.run(["pdftoppm", "-r", str(a.dpi), "-png", a.pdf, os.path.join(tmp, "p")], check=True)
    imgs = sorted(glob.glob(os.path.join(tmp, "p*.png")))
    people, low, empty = [], [], []
    for i, img in enumerate(imgs):
        try: ws, W = words_from_text_layer(a.pdf, i)
        except Exception: ws = []
        if len(ws) < 40: ws, W = words_from_ocr(img)                 # tidak ada teks di PDF: OCR gambar
        halves = [(0, W)]
        if sum(1 for w in ws if w["t"].lower().strip(".:") in NAME) >= 2: halves = [(0, W / 2), (W / 2, W + 1)]
        got = [r for x0, x1 in halves for r in (parse_half(ws, x0, x1) or [])]
        if not got: empty.append(i + 1)
        elif statistics.mean(r["conf"] for r in got) < 60: low.append(i + 1)
        people += got
    with open(a.out, "w", encoding="utf-8") as f:
        for p in people: f.write(f"{p['name']} | {p['role']} | {p['pt']}\n")
    nums = sorted({p["no"] for p in people})
    miss = sorted(set(range(1, (nums[-1] if nums else 0) + 1)) - set(nums))
    rng, s = [], None
    for n in miss:
        if s is None: s = e = n
        elif n == e + 1: e = n
        else: rng.append((s, e)); s = e = n
    if s is not None: rng.append((s, e))
    print(f"{len(imgs)} halaman | {len(people)} baris bernama -> {a.out}")
    if empty: print(f"⚠ halaman tanpa tabel terbaca: {empty} (kepala kolom tidak ditemukan / tulisan tangan)")
    if low: print(f"⚠ keyakinan OCR rendah (<60) di halaman {low}: hasil tidak dapat diandalkan, baca visual (gambar di {tmp})")
    if rng: print("⚠ nomor urut tidak terbaca: " + ", ".join(f"{x}" if x == y else f"{x}-{y}" for x, y in rng) + " (baris kosong di formulir, atau OCR melewatkan baris)")

if __name__ == "__main__": main()
