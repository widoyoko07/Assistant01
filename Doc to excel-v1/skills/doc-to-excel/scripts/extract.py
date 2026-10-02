#!/usr/bin/env python3
"""Ekstraksi baris/tabel dari PDF (teks maupun scan) dan gambar/screenshot.

  python3 extract.py --inventory <file|folder>
  python3 extract.py <file|folder> --out-dir /tmp/doc2x [--dpi 300] [--lang eng+ind] [--render-all]

Per halaman: lapisan teks PDF dibaca lebih dulu (pdfplumber); bila halaman tidak punya teks (scan) atau
file adalah gambar, halaman dirender dan dibaca dengan Tesseract. Hasil per file: <stem>.json (baris + sel +
keyakinan), <stem>.txt (baris dipisah ' | ', mudah dibaca), dan PNG halaman OCR untuk verifikasi visual.
Peringatan (halaman kosong, keyakinan OCR rendah) dicetak di akhir; bawa ke Catatan/Log, jangan dibuang."""
import argparse, json, os, statistics, subprocess, sys

IMG_EXT = {".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff", ".bmp", ".gif"}
LOW_CONF = 75


def files_in(path):
    if os.path.isdir(path):
        return [os.path.join(path, f) for f in sorted(os.listdir(path))
                if os.path.splitext(f)[1].lower() in IMG_EXT | {".pdf"}]
    return [path]


def cluster_rows(words, gap_factor=1.6):
    """words: dict(t,x,y,w,h,c) -> baris; sel baru bila jarak antar kata > gap_factor x tinggi median."""
    words = [w for w in words if w["t"].strip()]
    if not words:
        return []
    mh = statistics.median(w["h"] for w in words) or 1
    words.sort(key=lambda w: (w["y"] + w["h"] / 2, w["x"]))
    rows, cur = [], [words[0]]
    for w in words[1:]:
        if abs((w["y"] + w["h"] / 2) - statistics.mean(v["y"] + v["h"] / 2 for v in cur)) <= 0.6 * mh:
            cur.append(w)
        else:
            rows.append(cur)
            cur = [w]
    rows.append(cur)
    out = []
    for r in rows:
        r.sort(key=lambda w: w["x"])
        cells, cell = [], [r[0]]
        for w in r[1:]:
            if w["x"] - (cell[-1]["x"] + cell[-1]["w"]) > gap_factor * mh:
                cells.append(cell)
                cell = [w]
            else:
                cell.append(w)
        cells.append(cell)
        out.append({"y": round(statistics.mean(w["y"] for w in r), 1),
                    "cells": [" ".join(w["t"] for w in c) for c in cells],
                    "x": [round(c[0]["x"], 1) for c in cells],
                    "conf": [round(statistics.mean(w["c"] for w in c), 1) for c in cells]})
    return out


def ocr_words(img_path, lang, threshold=True):
    import pytesseract, cv2
    im = cv2.imread(img_path, cv2.IMREAD_GRAYSCALE)
    if im is None:
        raise RuntimeError(f"gambar tidak terbaca: {img_path}")
    if im.shape[1] < 1600:                      # screenshot kecil: perbesar agar teks kecil terbaca
        im = cv2.resize(im, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    if threshold:
        im = cv2.threshold(im, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
    d = pytesseract.image_to_data(im, lang=lang, config="--psm 6", output_type=pytesseract.Output.DICT)
    return [dict(t=d["text"][i].strip(), x=d["left"][i], y=d["top"][i], w=d["width"][i], h=d["height"][i],
                 c=float(d["conf"][i]))
            for i in range(len(d["text"])) if d["text"][i].strip() and float(d["conf"][i]) >= 0]


def pick_lang(want):
    try:
        import pytesseract
        have = set(pytesseract.get_languages())
    except Exception:
        return want or "eng"
    if want:
        return "+".join(l for l in want.split("+") if l in have) or "eng"
    return "eng+ind" if "ind" in have else "eng"


def render(pdf, n, dpi, outdir, stem):
    os.makedirs(outdir, exist_ok=True)
    prefix = os.path.join(outdir, f"{stem}_p{n:03d}")
    try:
        subprocess.run(["pdftoppm", "-f", str(n), "-l", str(n), "-r", str(dpi), "-png", "-singlefile", pdf, prefix],
                       check=True, stdout=subprocess.DEVNULL)
    except FileNotFoundError as exc:
        raise RuntimeError("Poppler (pdftoppm) belum terpasang") from exc
    return prefix + ".png"


def inventory(path):
    import pdfplumber
    for f in files_in(path):
        ext = os.path.splitext(f)[1].lower()
        size = os.path.getsize(f) // 1024
        if ext == ".pdf":
            with pdfplumber.open(f) as doc:
                n = len(doc.pages)
                sample = doc.pages[:3]
                words = [len(p.extract_words()) for p in sample]
                tbl = sum(len(p.extract_tables()) for p in sample)
            if min(words, default=0) >= 5:
                kind = "PDF teks"
            elif max(words, default=0) < 5:
                kind = "PDF scan/foto (perlu OCR)"
            else:
                kind = "PDF campuran"
            print(f"{os.path.basename(f)} | {kind} | {n} hlm | {size} KB | kata di 3 hlm awal: {words} | tabel bergaris: {tbl}")
        elif ext in IMG_EXT:
            from PIL import Image
            w, h = Image.open(f).size
            print(f"{os.path.basename(f)} | gambar/screenshot | {w}x{h} | {size} KB | "
                  + ("resolusi rendah, OCR kurang andal" if w < 800 else "OK untuk OCR"))
        else:
            print(f"{os.path.basename(f)} | tipe tidak didukung ({ext})")


def process(f, a, lang):
    stem = os.path.splitext(os.path.basename(f))[0]
    ext = os.path.splitext(f)[1].lower()
    pages, warns = [], []
    if ext in IMG_EXT:
        rows = cluster_rows(ocr_words(f, lang, not a.no_threshold))
        pages.append({"page": 1, "method": "ocr", "image": f, "rows": rows, "tables": []})
    else:
        import pdfplumber
        with pdfplumber.open(f) as doc:
            for n, pg in enumerate(doc.pages, 1):
                try:
                    ws = [dict(t=w["text"], x=w["x0"], y=w["top"], w=w["x1"] - w["x0"], h=w["bottom"] - w["top"], c=100.0)
                          for w in pg.extract_words()]
                except Exception:
                    ws = []
                if len(ws) >= a.min_words:
                    try:
                        tables = [t for t in pg.extract_tables() if t and len(t) >= 2]
                    except Exception:
                        tables = []
                    pages.append({"page": n, "method": "text", "rows": cluster_rows(ws), "tables": tables,
                                  "image": render(f, n, a.dpi, a.out_dir, stem) if a.render_all else None})
                else:
                    img = render(f, n, a.dpi, a.out_dir, stem)
                    pages.append({"page": n, "method": "ocr", "image": img,
                                  "rows": cluster_rows(ocr_words(img, lang, not a.no_threshold)), "tables": []})
    base = os.path.basename(f)
    for p in pages:
        confs = [c for r in p["rows"] for c in r["conf"]]
        p["mean_conf"] = round(statistics.mean(confs), 1) if confs else None
        if not p["rows"]:
            warns.append(f"{base} hlm {p['page']}: tidak ada baris terbaca (kosong/tulisan tangan/header tidak jelas), baca visual dari gambar")
        elif p["method"] == "ocr" and p["mean_conf"] < LOW_CONF:
            warns.append(f"{base} hlm {p['page']}: keyakinan OCR rendah ({p['mean_conf']}), wajib verifikasi visual: {p['image']}")
    os.makedirs(a.out_dir, exist_ok=True)
    with open(os.path.join(a.out_dir, stem + ".json"), "w", encoding="utf-8") as j:
        json.dump({"file": base, "pages": pages, "warnings": warns}, j, ensure_ascii=False, indent=1)
    with open(os.path.join(a.out_dir, stem + ".txt"), "w", encoding="utf-8") as t:
        for p in pages:
            t.write(f"=== {base} | hlm {p['page']} | {p['method']}"
                    + (f" | konf {p['mean_conf']}" if p["mean_conf"] is not None else "") + " ===\n")
            for r in p["rows"]:
                t.write(" | ".join(r["cells"]) + "\n")
    nocr = sum(p["method"] == "ocr" for p in pages)
    print(f"{base}: {len(pages)} hlm (teks {len(pages) - nocr}, OCR {nocr}), "
          f"{sum(len(p['rows']) for p in pages)} baris -> {a.out_dir}/{stem}.txt")
    return warns


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--inventory", action="store_true")
    ap.add_argument("--out-dir", default="/tmp/doc2x")
    ap.add_argument("--dpi", type=int, default=300)
    ap.add_argument("--lang")
    ap.add_argument("--min-words", type=int, default=5)
    ap.add_argument("--render-all", action="store_true", help="render semua halaman PDF teks juga (untuk verifikasi visual)")
    ap.add_argument("--no-threshold", action="store_true", help="matikan binarisasi Otsu (foto dengan pencahayaan tidak rata)")
    a = ap.parse_args()
    if a.inventory:
        inventory(a.path)
        sys.exit()
    lang = pick_lang(a.lang)
    allw = []
    for f in files_in(a.path):
        try:
            allw += process(f, a, lang)
        except Exception as e:
            allw.append(f"{os.path.basename(f)}: GAGAL diproses ({e})")
    for w in allw:
        print("⚠ " + w)
