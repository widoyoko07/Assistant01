#!/usr/bin/env python3
"""site-photo-renamer: bagian mekanis (hash, tanggal, rasio, crop, penamaan, log, verifikasi).
Penilaian isi foto (pekerjaan, lokasi, timestamp, objek utama) dilakukan Claude secara visual lalu ditulis ke decisions.json.

  scan    INPUT --work DIR [--chat F] [--from YYYY-MM-DD] [--to YYYY-MM-DD] [--sender TEXT] [--limit N]
  plan    --work DIR                      -> DRY-RUN: tabel pratinjau + daftar pertanyaan (tidak ada foto dibuat)
  execute --work DIR --out OUT --confirm  -> crop 4:3, simpan ke final/needs-cleaning/check, log.csv, verifikasi

File asli tidak pernah diubah: semua hasil ditulis ke folder baru."""
import argparse, csv, datetime as dt, hashlib, json, os, re, shutil, sys, zipfile

from PIL import Image, ImageOps

try:
    import pillow_heif; pillow_heif.register_heif_opener()
except Exception:
    pass

PHOTO_EXT = {".jpg", ".jpeg", ".png", ".webp", ".heic"}
RATIO, TOL = 4 / 3, 0.006
BAD = r'[\\/:*?"<>|]'
MAXLEN = 120
JPEG_Q = 95

# ------------------------------------------------------------------ util
def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""): h.update(b)
    return h.hexdigest()

def sanitize(s):
    return re.sub(r"\s+", " ", re.sub(BAD, " ", s or "")).strip(" .")

def load_json(p, default=None):
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else default

def save_json(p, o):
    json.dump(o, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

# ------------------------------------------------------------------ tanggal
def exif_date(im):
    try:
        ex = im.getexif()
        v = ex.get_ifd(0x8769).get(0x9003) or ex.get(0x0132)
        if v:
            return dt.datetime.strptime(str(v)[:10], "%Y:%m:%d").date().isoformat()
    except Exception:
        pass
    return None

def name_date(fn):
    for pat in (r"(?:IMG|VID|PHOTO)-(20\d{2})(\d{2})(\d{2})-WA", r"(20\d{2})-(\d{2})-(\d{2})", r"(20\d{2})(\d{2})(\d{2})"):
        m = re.search(pat, fn)
        if m:
            try: return dt.date(*map(int, m.groups())).isoformat()
            except ValueError: pass
    return None

MSG = re.compile(r"^\u200e?\[?(\d{1,2})/(\d{1,2})/(\d{2,4}),?\s+\d{1,2}[.:]\d{2}(?:[.:]\d{2})?\s*(?:[APap][Mm])?\]?\s*(?:-\s*)?([^:]+?):\s?(.*)$")
FILEREF = re.compile(r"([\w\-. ()]+\.(?:jpe?g|png|webp|heic))", re.I)

def parse_chat(path):
    """-> {nama_file_lower: {date, sender, caption}}. Urutan d/m vs m/d dideteksi dari seluruh isi chat."""
    lines = open(path, encoding="utf-8", errors="ignore").read().splitlines()
    hits = [MSG.match(l) for l in lines]
    first_gt12 = any(h and int(h.group(1)) > 12 for h in hits)
    second_gt12 = any(h and int(h.group(2)) > 12 for h in hits)
    mdy = second_gt12 and not first_gt12
    out, cur = {}, None
    for l, h in zip(lines, hits):
        if h:
            a, b, y, sender, body = int(h.group(1)), int(h.group(2)), int(h.group(3)), h.group(4).strip(), h.group(5)
            d, m = (b, a) if mdy else (a, b)
            try: date = dt.date(y + 2000 if y < 100 else y, m, d).isoformat()
            except ValueError: cur = None; continue
            fm = FILEREF.search(body)
            if fm:
                fn = fm.group(1).strip().replace("<attached: ", "")
                cap = re.sub(r"\(file attached\)|<attached:.*?>", "", body[fm.end():]).strip()
                cur = out.setdefault(fn.lower(), {"date": date, "sender": sender, "caption": cap})
            else: cur = None
        elif cur is not None and l.strip():                      # baris lanjutan = caption
            cur["caption"] = (cur["caption"] + " " + l.strip()).strip()
    return out

# ------------------------------------------------------------------ scan
def cmd_scan(a):
    work = a.work; os.makedirs(os.path.join(work, "preview"), exist_ok=True)
    src = a.input
    if src.lower().endswith(".zip"):
        dst = os.path.join(work, "unzipped"); shutil.rmtree(dst, ignore_errors=True)
        zipfile.ZipFile(src).extractall(dst); src = dst
    files = sorted(os.path.join(r, f) for r, _, fs in os.walk(src) for f in fs)
    chat_path = a.chat or next((f for f in files if os.path.basename(f).lower() in ("_chat.txt", "chat.txt")), None)
    chat = parse_chat(chat_path) if chat_path else {}
    inv, seen = [], {}
    n_photo = 0
    for f in files:
        base = os.path.basename(f)
        if f == chat_path or base.lower() in ("_chat.txt", "chat.txt"): continue
        rec = {"id": f"p{len(inv) + 1:03d}", "path": os.path.abspath(f), "name": base, "status": "ok", "reason": ""}
        inv.append(rec)
        if os.path.splitext(base)[1].lower() not in PHOTO_EXT:
            rec.update(status="skipped", reason="bukan foto (video/PDF/stiker/lainnya)"); continue
        try:
            rec["hash"] = sha(f)
            with Image.open(f) as im0:
                ed = exif_date(im0)
                im = ImageOps.exif_transpose(im0)          # dimensi sesudah koreksi orientasi EXIF
                rec["w"], rec["h"] = im.size
                rec["rotated_by_exif"] = (im.size != im0.size)
                th = im.convert("RGB"); th.thumbnail((1024, 1024))
                th.save(os.path.join(work, "preview", rec["id"] + ".jpg"), quality=85)
        except Exception as e:
            rec.update(status="skipped", reason=f"tidak bisa dibaca ({type(e).__name__}; HEIC perlu pillow-heif)"); continue
        n_photo += 1
        if rec["hash"] in seen:
            rec.update(status="skipped", reason=f"duplikat persis dari {seen[rec['hash']]}"); continue
        seen[rec["hash"]] = base
        c = chat.get(base.lower())
        if c: rec.update(sender=c["sender"], caption=c["caption"])
        cands = [("chat.txt", c["date"] if c else None), ("EXIF", ed), ("nama file", name_date(base))]
        rec["date"], rec["date_source"] = next(((d, s) for s, d in cands if d), (None, "tidak ada"))
        rec["date_conflict"] = sorted({d for _, d in cands if d}) if len({d for _, d in cands if d}) > 1 else []
        if a.date_from and rec["date"] and rec["date"] < a.date_from: rec.update(status="skipped", reason="di luar filter tanggal")
        elif a.date_to and rec["date"] and rec["date"] > a.date_to: rec.update(status="skipped", reason="di luar filter tanggal")
        elif a.sender and a.sender.lower() not in (rec.get("sender") or "").lower(): rec.update(status="skipped", reason="di luar filter pengirim")
    if a.limit:
        k = 0
        for r in inv:
            if r["status"] == "ok":
                k += 1
                if k > a.limit: r.update(status="skipped", reason=f"di luar batas batch ({a.limit})")
    save_json(os.path.join(work, "inventory.json"), inv)
    ok = [r for r in inv if r["status"] == "ok"]
    print(f"File dipindai: {len(inv)} | foto terbaca: {n_photo} | diproses: {len(ok)} | dilewati: {len(inv) - len(ok)}")
    print(f"chat.txt: {chat_path or 'tidak ada'} ({len(chat)} foto bercaption/berpengirim terpetakan)")
    for s in ("chat.txt", "EXIF", "nama file", "tidak ada"):
        print(f"  tanggal dari {s}: {sum(1 for r in ok if r['date_source'] == s)}")
    for r in inv:
        if r["status"] == "skipped": print(f"  dilewati {r['name']}: {r['reason']}")
    print(f"Pratinjau (maks 1024 px) untuk dilihat: {work}/preview/<id>.jpg ; id & metadata: {work}/inventory.json")
    print(f"Berikutnya: tulis {work}/decisions.json lalu jalankan plan.")

# ------------------------------------------------------------------ plan
def crop_rect(w, h):
    """Rect crop tengah (x0,y0,x1,y1 piksel) atau None bila sudah 4:3 / portrait."""
    if h > w: return None
    r = w / h
    if abs(r - RATIO) <= TOL: return None
    if r > RATIO: nw = round(h * RATIO); x0 = (w - nw) // 2; return (x0, 0, x0 + nw, h)
    nh = round(w / RATIO); y0 = (h - nh) // 2; return (0, y0, w, y0 + nh)

def ts_state(dec, rect, w, h):
    """none | safe (seluruh overlay berada di luar area crop) | unsafe."""
    if not dec.get("timestamp"): return "none"
    box = dec.get("ts_box")
    if not box or not rect: return "unsafe"
    bx0, by0, bx1, by1 = box[0] * w, box[1] * h, box[2] * w, box[3] * h
    m = 0.01 * max(w, h)
    return "safe" if (bx1 <= rect[0] - m or bx0 >= rect[2] + m or by1 <= rect[1] - m or by0 >= rect[3] + m) else "unsafe"

def cmd_plan(a):
    inv = load_json(os.path.join(a.work, "inventory.json")); dec = load_json(os.path.join(a.work, "decisions.json"), {})
    if inv is None: sys.exit("inventory.json tidak ada: jalankan scan dulu.")
    items, questions = [], []
    for r in inv:
        if r["status"] != "ok": continue
        d = dec.get(r["id"], {}); flags = []; notes = []
        if r["id"] not in dec: notes.append("belum ada keputusan visual di decisions.json"); flags.append("CHECK")
        work, loc = sanitize(d.get("work")), sanitize(d.get("location"))
        if d.get("unsure") or not work or not loc: flags.append("CHECK")
        if not r["date"]: flags.append("CHECK"); notes.append("tanggal tidak dapat dipastikan")
        if r["date_conflict"]: flags.append("CHECK"); notes.append("tanggal berbeda antar sumber: " + ", ".join(r["date_conflict"]))
        if d.get("note"): notes.append(d["note"])
        portrait = r["h"] > r["w"]
        rect = crop_rect(r["w"], r["h"])
        if portrait: flags.append("PORTRAIT"); notes.append("portrait, tidak dipaksa ke 4:3")
        if d.get("crop_cuts_subject") and rect: flags.append("CHECK"); notes.append("crop 4:3 memotong objek utama; disimpan tanpa crop")
        ts = ts_state(d, rect, r["w"], r["h"])
        if ts == "unsafe": flags.append("TS")
        if ts == "safe": notes.append("timestamp berada di luar area crop 4:3, hilang oleh crop")
        folder = "needs-cleaning" if "TS" in flags else ("check" if flags else "final")
        apply_crop = bool(rect) and not d.get("crop_cuts_subject") and not portrait
        items.append(dict(id=r["id"], path=r["path"], old=r["name"], w=r["w"], h=r["h"], date=r["date"], date_source=r["date_source"],
                          work=work or "Unidentified Work", location=loc or "Unidentified Location", flags=sorted(set(flags), key=["TS", "CHECK", "PORTRAIT"].index),
                          folder=folder, crop=list(rect) if apply_crop else None, ts=ts, notes=notes, question=d.get("question")))
    # nama + bentrok
    items.sort(key=lambda x: (x["date"] or "9999", x["old"]))
    count = {}
    for it in items:
        yymmdd = it["date"][2:].replace("-", "") if it["date"] else "XXXXXX"
        marks = "".join(f" [{f}]" for f in it["flags"])
        core = sanitize(f"{yymmdd} {it['work']} {it['location']}")[: MAXLEN - len(marks) - 3].rstrip()
        k = core.lower(); count[k] = count.get(k, 0) + 1
        it["new"] = f"{core}{'' if count[k] == 1 else f' {count[k]:02d}'}{marks}.jpg"
        if it["question"]: questions.append(f"{it['old']}: {it['question']}")
    save_json(os.path.join(a.work, "plan.json"), items)
    print("## DRY-RUN (belum ada file yang dibuat)\n")
    print("| Nama lama | Nama baru | Tanggal (sumber) | Rasio | Timestamp | Status |\n|---|---|---|---|---|---|")
    for it in items:
        rs = f"{it['w']}x{it['h']} -> " + ("crop 4:3" if it["crop"] else ("portrait" if it["h"] > it["w"] else "sudah 4:3" if abs(it["w"] / it["h"] - RATIO) <= TOL else "tanpa crop"))
        print(f"| {it['old']} | {it['new']} | {it['date'] or '?'} ({it['date_source']}) | {rs} | "
              f"{ {'none': 'tidak ada', 'safe': 'hilang oleh crop', 'unsafe': 'ADA [TS]'}[it['ts']] } | {it['folder']}{'; ' + '; '.join(it['notes']) if it['notes'] else ''} |")
    print(f"\nFinal: {sum(i['folder'] == 'final' for i in items)} | needs-cleaning: {sum(i['folder'] == 'needs-cleaning' for i in items)} | "
          f"check: {sum(i['folder'] == 'check' for i in items)} | dilewati: {sum(r['status'] != 'ok' for r in inv)}")
    if questions:
        print("\n### Pertanyaan (satu daftar)"); [print(f"{n}. {q}") for n, q in enumerate(questions, 1)]

# ------------------------------------------------------------------ execute
def cmd_execute(a):
    if not a.confirm: sys.exit("Ditolak: execute hanya boleh setelah user mengonfirmasi tabel DRY-RUN (tambahkan --confirm).")
    inv = load_json(os.path.join(a.work, "inventory.json")); plan = load_json(os.path.join(a.work, "plan.json"))
    if not plan: sys.exit("plan.json tidak ada: jalankan plan dulu.")
    out = os.path.abspath(a.out)
    for s in ("final", "needs-cleaning", "check"): os.makedirs(os.path.join(out, s), exist_ok=True)
    clash = [os.path.join(out, it["folder"], it["new"]) for it in plan if os.path.exists(os.path.join(out, it["folder"], it["new"]))]
    if clash or os.path.exists(os.path.join(out, "log.csv")):
        sys.exit("Menolak menimpa (tidak ada yang ditulis). Pakai --out folder baru. Sudah ada: " + ", ".join(clash[:3] + (["log.csv"] if os.path.exists(os.path.join(out, "log.csv")) else [])))
    for it in plan:
        dst = os.path.join(out, it["folder"], it["new"])
        with Image.open(it["path"]) as im0:
            ex = im0.getexif(); im = ImageOps.exif_transpose(im0)
            untouched = not it["crop"] and im.size == im0.size and im0.format == "JPEG"
            if untouched: shutil.copyfile(it["path"], dst); continue          # tanpa re-encode = tanpa penurunan kualitas
            if it["crop"]: im = im.crop(tuple(it["crop"]))
            try: ex[0x0112] = 1
            except Exception: pass
            im.convert("RGB").save(dst, "JPEG", quality=JPEG_Q, subsampling=0, exif=ex.tobytes())
    rows = [[it["old"], it["new"], it["folder"], it["date"] or "", it["date_source"], "; ".join(f"[{f}]" for f in it["flags"]) or "ok", "; ".join(it["notes"])] for it in plan]
    rows += [[r["name"], "", "dilewati", "", "", r["reason"], ""] for r in inv if r["status"] != "ok"]
    with open(os.path.join(out, "log.csv"), "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f); w.writerow(["nama_asli", "nama_baru", "folder", "tanggal", "sumber_tanggal", "keputusan", "catatan"]); w.writerows(rows)
    verify(out, plan, inv)
    if a.zip: shutil.make_archive(out, "zip", out); print(f"ZIP: {out}.zip")

def verify(out, plan, inv):
    errs, pat = [], re.compile(r"^(\d{6}|XXXXXX) .+\.jpg$")
    placed = 0
    for s in ("final", "needs-cleaning", "check"):
        for fn in os.listdir(os.path.join(out, s)):
            placed += 1; p = os.path.join(out, s, fn)
            if not pat.match(re.sub(r"( \[(TS|CHECK|PORTRAIT)\])+\.jpg$", ".jpg", fn)): errs.append(f"nama tidak sesuai pola: {s}/{fn}")
            if s == "final":
                if "[TS]" in fn: errs.append(f"[TS] di final: {fn}")
                with Image.open(p) as im:
                    if abs(im.width / im.height - RATIO) > TOL: errs.append(f"rasio bukan 4:3: {fn} ({im.width}x{im.height})")
    skipped = sum(r["status"] != "ok" for r in inv)
    if len(inv) != placed + skipped: errs.append(f"jumlah tidak cocok: input {len(inv)} != output {placed} + dilewati {skipped}")
    f = lambda k: sum(i["folder"] == k for i in plan)
    print(f"\n## Ringkasan\nTotal file input: {len(inv)} | berhasil: {placed} (final {f('final')}, needs-cleaning/[TS] {f('needs-cleaning')}, check {f('check')}) | dilewati: {skipped}")
    print("Verifikasi akhir: " + ("LULUS (semua final 4:3, nama sesuai pola, tanpa [TS] di final, jumlah cocok)" if not errs else "GAGAL"))
    for e in errs: print(" - " + e)

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); sp = ap.add_subparsers(dest="cmd", required=True)
    s = sp.add_parser("scan"); s.add_argument("input"); s.add_argument("--work", required=True); s.add_argument("--chat")
    s.add_argument("--from", dest="date_from"); s.add_argument("--to", dest="date_to"); s.add_argument("--sender"); s.add_argument("--limit", type=int)
    p = sp.add_parser("plan"); p.add_argument("--work", required=True)
    e = sp.add_parser("execute"); e.add_argument("--work", required=True); e.add_argument("--out", required=True)
    e.add_argument("--confirm", action="store_true"); e.add_argument("--zip", action="store_true")
    a = ap.parse_args(); {"scan": cmd_scan, "plan": cmd_plan, "execute": cmd_execute}[a.cmd](a)
