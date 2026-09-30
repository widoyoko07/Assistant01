#!/usr/bin/env python3
"""PDF Attendance (teks/scan) -> '<SC>_<YYYYMMDD>_Attendance.txt' berformat 'Nama | Role | PT/CV'.

Pakai: python3 pdf_to_att.py <file.pdf> --out /tmp/mp_att/WME_20260930_Attendance.txt [--dpi 300] [--pages-dir /tmp/pages]
Parser membaca lapisan teks lebih dulu dan hanya merender halaman yang gagal menghasilkan baris tabel.
Tabel dikenali dari header; dua tabel berdampingan didukung. Nomor urut yang hilang dan confidence OCR
dilaporkan. Untuk OCR, perlu Poppler dan Tesseract; --pages-dir menyimpan gambar halaman yang dirender."""
import argparse, os, re, statistics, subprocess, tempfile

NAME, POS, PT, SIG, NO = ("name", "nama"), ("position", "posisi", "jabatan", "role"), ("pt", "pt/cv", "cv", "perusahaan"), ("signature", "sign", "ttd", "paraf", "tanda"), ("no", "no.", "nomor")

def words_from_text_layer(page):
    ws = [dict(t=w["text"], x=w["x0"], y=w["top"], w=w["x1"] - w["x0"], h=w["bottom"] - w["top"], c=100.0)
          for w in page.extract_words()]
    return ws, float(page.width)

def words_from_ocr(img):
    try:
        import pytesseract, cv2
    except ModuleNotFoundError as exc:
        raise RuntimeError("Modul OCR belum terpasang. Jalankan: python3 -m pip install -r requirements-pdf.txt") from exc
    im = cv2.imread(img, cv2.IMREAD_GRAYSCALE)
    if im is None: raise RuntimeError(f"Gambar halaman tidak dapat dibaca: {img}")
    _, im = cv2.threshold(im, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    try:
        d = pytesseract.image_to_data(im, lang="eng", config="--psm 6", output_type=pytesseract.Output.DICT)
    except pytesseract.pytesseract.TesseractNotFoundError as exc:
        raise RuntimeError("Tesseract belum terpasang atau tidak ada di PATH.") from exc
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

def parse_page(ws, width):
    halves = [(0, width)]
    if sum(1 for w in ws if w["t"].lower().strip(".:") in NAME) >= 2:
        halves = [(0, width / 2), (width / 2, width + 1)]
    return [row for x0, x1 in halves for row in (parse_half(ws, x0, x1) or [])]

def render_page(pdf, page_number, dpi, pages_dir):
    os.makedirs(pages_dir, exist_ok=True)
    prefix = os.path.join(pages_dir, f"page-{page_number:04d}")
    try:
        subprocess.run(["pdftoppm", "-f", str(page_number), "-l", str(page_number), "-r", str(dpi),
                        "-png", "-singlefile", pdf, prefix], check=True, stdout=subprocess.DEVNULL)
    except FileNotFoundError as exc:
        raise RuntimeError("Poppler pdftoppm belum terpasang atau tidak ada di PATH.") from exc
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"pdftoppm gagal merender halaman {page_number}.") from exc
    return prefix + ".png"

def extract_page(page, pdf, page_number, dpi, pages_dir):
    try:
        text_words, width = words_from_text_layer(page)
    except Exception:
        text_words, width = [], float(page.width)
    text_rows = parse_page(text_words, width)
    if text_rows:
        return text_rows, "text", None

    image = render_page(pdf, page_number, dpi, pages_dir)
    ocr_words, width = words_from_ocr(image)
    return parse_page(ocr_words, width), "ocr", image

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("pdf"); ap.add_argument("--out", required=True)
    ap.add_argument("--dpi", type=int, default=300); ap.add_argument("--pages-dir")
    a = ap.parse_args()
    if a.dpi < 72: ap.error("--dpi harus minimal 72")
    tmp = a.pages_dir or tempfile.mkdtemp(); os.makedirs(tmp, exist_ok=True)
    try:
        import pdfplumber
    except ModuleNotFoundError as exc:
        raise SystemExit("pdfplumber belum terpasang. Jalankan: python3 -m pip install -r requirements-pdf.txt") from exc
    people, low, empty = [], [], []
    text_pages, ocr_pages = [], []
    try:
        with pdfplumber.open(a.pdf) as doc:
            for page_number, page in enumerate(doc.pages, 1):
                got, source, image = extract_page(page, a.pdf, page_number, a.dpi, tmp)
                if source == "text": text_pages.append(page_number)
                else: ocr_pages.append(page_number)
                if not got: empty.append(page_number)
                elif source == "ocr" and statistics.mean(r["conf"] for r in got) < 60: low.append(page_number)
                people += got
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
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
    print(f"{len(text_pages) + len(ocr_pages)} halaman | teks: {len(text_pages)}, OCR: {len(ocr_pages)} | {len(people)} baris bernama -> {a.out}")
    if empty: print(f"⚠ halaman tanpa baris terbaca: {empty} (header tidak dikenali, halaman kosong, atau tulisan tangan)")
    if low: print(f"⚠ keyakinan OCR rendah (<60) di halaman {low}: hasil tidak dapat diandalkan, baca visual (gambar di {tmp})")
    if rng: print("⚠ nomor urut tidak muncul dalam hasil: " + ", ".join(f"{x}" if x == y else f"{x}-{y}" for x, y in rng) + " (indikasi baris kosong/OCR terlewat, bukan bukti halaman hilang)")

if __name__ == "__main__": main()
