#!/usr/bin/env python3
"""Detail per sheet (tray per lebar x orientasi, conduit per ukuran x jenis x orientasi, support, elevasi) dari PDF vektor.

  python sheetdetail.py plan    PDF --out DIR [--sheets 3,7] [--budget 240]   # DRY-RUN (OCR di-cache; ulangi bila belum selesai)
  python sheetdetail.py execute PDF --out DIR --confirm                       # Excel, hanya setelah user setuju

Aturan (instruksi user):
 - Skala = tulisan "SCALE - 1:N" milik view itu sendiri (bukan title block), dicek ke dimensi grid (6000/7500).
   Konflik label vs grid dilaporkan di AWAL; label tetap dipakai dan hasil diberi PROVISIONAL.
 - Lebar tray dari callout "CABLE TRAY nnn(W)" hasil OCR (BUKAN legenda A-K). Callout "POWER-200, CONTROL-100" = pembagian
   ruang kabel, diabaikan. Tray = garis tengah. Plan = horizontal, section = vertikal (batas atas, duplikat antar-section).
 - Conduit: label "54mm CONTROL EL+..." (OCR). Satu rute berlabel >1 jenis = 1 pipa per label (panjang rute x jumlah label).
   Orientasi dari segmen vektor garis hijau: horizontal / vertikal / miring (panjang hipotenusa asli).
   Penempatan label ke rute = komponen hijau terdekat: SELALU PROVISIONAL (cek overlay).
 - Support: kode SU[H|V]-nnn<ukuran><C|S>; qty dari sheet detail (pasangan terdekat 'n Ea').
Angka = keluaran skrip."""
import argparse, collections, json, math, os, re, sys, time
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import takeoff as T
import conduit as C

DPI = 300
PX_TO_PT = 72.0 / DPI
STD = (50, 75, 100, 120, 150, 200, 250)
EL_RE = re.compile(r"^EL\+?(\d{3,5})mm", re.I)
SUP_RE = re.compile(r"^SU([HV])-?(\d+)([A-K])([CS])$", re.I)
CONDUIT_SIZES = (16, 22, 28, 36, 42, 54, 70, 82, 92, 104)   # G-Type conduit pipe; maks desain 104 mm
LETTER_W = {"A": 100, "B": 200, "C": 300, "D": 400, "E": 500, "F": 600, "G": 700, "H": 800, "I": 900, "J": 1000, "K": 400}
FLOORS_NOTE = "level lantai section"


# ------------------------------------------------------------ skala per view
def view_scale(words):
    """words PyMuPDF (x0,y0,x1,y1,text,...). 'SCALE' diikuti '1:N' sebaris; title block (x > 90% lebar) dibuang."""
    out = []
    for a in words:
        if a[4].upper() != "SCALE": continue
        for b in words:
            m = re.fullmatch(r"1:(\d{2,4})", b[4])
            if m and abs(b[1] - a[1]) < 4 and 0 < b[0] - a[0] < 80: out.append(int(m.group(1)))
    return out


def dim_scale(xs, words=None, width=None):
    """Verifikasi skala dari jarak garis grid vertikal: >=3 garis berurutan dengan dua jarak sama = 6000 atau 7500 mm
    pada salah satu skala standar (dimensi 6000/7500 digambar vektor, bukan teks, jadi dibaca dari geometri)."""
    votes = collections.Counter(); xs = sorted(set(round(x, 1) for x in xs))
    for N in STD:
        for D in (6000, 7500):
            g = D / (N * T.PT_MM)
            for i in range(len(xs) - 2):
                g1, g2 = xs[i + 1] - xs[i], xs[i + 2] - xs[i + 1]
                if abs(g1 - g) <= 0.02 * g and abs(g2 - g) <= 0.02 * g: votes[N] += 1
    return votes


def resolve_view_scale(page, cfg, override=None):
    W = page.rect.width; words = page.get_text("words")
    labs = [n for n in view_scale(words) if n]
    drs = page.get_cdrawings(); xs = T.vertical_x(page, W * cfg["content_xmax_frac"], drawings=drs)
    votes = dim_scale(xs, words, W); grid = votes.most_common(1)[0][0] if votes else None
    lab = collections.Counter(labs).most_common(1)[0][0] if labs else None
    flags = []; status = "label"
    N = lab
    if override: return int(override), "override", [], drs
    if lab and grid and lab != grid: flags.append(f"KONFLIK SKALA: label view 1:{lab} vs grid 1:{grid} (votes {dict(votes)}); dipakai label 1:{lab}, PROVISIONAL, WAJIB dicek"); status = "KONFLIK"
    elif lab and grid: status = "label+grid"
    elif lab: flags.append(f"skala 1:{lab} dari label view; grid 6000/7500 tidak terverifikasi (PROVISIONAL)"); status = "label-saja"
    elif grid: N = grid; status = "grid-saja"; flags.append(f"label skala tidak ditemukan; dipakai grid 1:{grid} (PROVISIONAL)")
    else: flags.append("skala tidak ditemukan: sheet dilewati")
    if len(set(labs)) > 1: flags.append(f"beberapa label skala di sheet: {sorted(set(labs))}")
    return N, status, flags, drs


# ------------------------------------------------------------ OCR (cache per halaman)
def page_ocr(doc, pg, out, dpi=DPI):
    path = os.path.join(out, "ocr_cache", f"p{pg:03d}.json")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh: return json.load(fh)
    words = C.ocr_words(doc[pg - 1], dpi)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh: json.dump(words, fh)
    return words


def tray_callouts(words):
    """'CABLE TRAY 400(W) X 100(H)mm' -> [{w, x, y, conf}] (px). Wajib didahului token TRAY sebaris."""
    out = []
    for t in words:
        m = re.match(r"^(\d{3,4})\(?W", t["t"], re.I)
        if not m: continue
        if any(o["t"].upper().startswith("TRAY") and abs(o["y"] - t["y"]) < 20 and 0 < t["x"] - o["x"] < 400 for o in words):
            out.append({"w": int(m.group(1)), "x": t["x"], "y": t["y"], "conf": t["c"]})
    return out


def conduit_labels(words):
    labs, unpaired = C.parse_labels(words)
    els = [(int(EL_RE.match(w["t"]).group(1)), w) for w in words if EL_RE.match(w["t"])]
    for l in labs:
        near = [(abs(w["x"] - l["x"]) + abs(w["y"] - l["y"]), e, w["c"]) for e, w in els
                if 0 < w["y"] - l["y"] < 150 and abs(w["x"] - l["x"]) < 120]
        l["el"], l["el_conf"] = (min(near)[1], min(near)[2]) if near else (None, None)
    return labs, unpaired


# ------------------------------------------------------------ geometri
def conduit_segments(drs, col, tol, xmax):
    """Segmen vektor hijau: (x0,y0,x1,y1) pt, duplikat koordinat dibuang. Kurva ('c') tidak ikut (dilaporkan)."""
    seen, segs, curves = set(), [], 0
    for dr in drs:
        if not T.iscol(dr.get("color"), col, tol): continue
        for it in dr["items"]:
            if it[0] == "c": curves += 1
            if it[0] != "l": continue
            a, b = it[1], it[2]
            if (a[0] > xmax and b[0] > xmax) or math.hypot(b[0] - a[0], b[1] - a[1]) < 0.3: continue
            key = tuple(sorted(((round(a[0], 1), round(a[1], 1)), (round(b[0], 1), round(b[1], 1)))))
            if key in seen: continue
            seen.add(key); segs.append((a[0], a[1], b[0], b[1]))
    return segs, curves


def orient(seg):
    ang = abs(math.degrees(math.atan2(seg[3] - seg[1], seg[2] - seg[0]))) % 180
    return "v" if abs(ang - 90) < 3 else "h" if (ang < 3 or ang > 177) else "d"


def components(page, cfg, drs, px, xmax, close_pt):
    import cv2
    from scipy import ndimage as ndi
    m = T.make_mask(page, cfg["colors"]["conduit"], cfg["color_tol"], px, xmax, drawings=drs)
    k = max(1, round(close_pt * px))
    mc = cv2.morphologyEx(m, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (k, k)))
    lab, n = ndi.label(mc > 0, structure=np.ones((3, 3)))
    return m, lab, n


def comp_of(lab, x_pt, y_pt, px):
    x, y = int(x_pt * px), int(y_pt * px); h, w = lab.shape
    win = lab[max(0, y - 2):min(h, y + 3), max(0, x - 2):min(w, x + 3)]
    v = win[win > 0]
    return int(np.bincount(v).argmax()) if v.size else 0


def nearest_comp(lab, cx_px, cy_px, px_mask):
    from scipy import ndimage as ndi
    ys, xs = np.nonzero(lab > 0)
    if not len(xs): return 0, None
    d = (xs - cx_px) ** 2 + (ys - cy_px) ** 2; i = int(d.argmin())
    return int(lab[ys[i], xs[i]]), math.sqrt(float(d[i])) / px_mask     # jarak dalam pt


# ------------------------------------------------------------ satu sheet
def process_sheet(doc, row, cfg, out, px, ocr_words_):
    p = doc[row["sheet"] - 1]; role = row["role"]; W = p.rect.width; xmax = W * cfg["content_xmax_frac"]
    N, st, flags, drs = resolve_view_scale(p, cfg, cfg["scales"].get(str(row["sheet"])))
    rec = {"sheet": row["sheet"], "role": role, "scale": N, "scale_status": st, "tray": {}, "conduit_runs": [], "conduit_unlabeled_m": {},
           "labels": [], "unpaired": [], "flags": flags, "levels": sorted({int(re.sub(r"\D", "", w[4])) for w in p.get_text("words") if re.fullmatch(r"EL\+\d{4}", w[4]) and w[0] > 0.5 * W}) if role == "section" else []}
    if N is None: return rec
    k = N * T.PT_MM; tag = f"sheet{row['sheet']:02d}"
    # --- tray
    call = tray_callouts(ocr_words_)
    widths = sorted({c["w"] for c in call})
    if row["items"].get("tray"):
        if not widths: rec["flags"].append("tray berwarna ada tetapi callout 'CABLE TRAY nnn(W)' tidak terbaca OCR: lebar tidak ditentukan, tray tidak dihitung")
        else:
            vertical = role == "section"
            m = T.make_mask(p, cfg["colors"]["tray"], cfg["color_tol"], px, xmax, "v" if vertical else "all", drawings=drs)
            tot, per, sk = T.measure(m, cfg["close_mm"]["tray"] / k, px, [w / k for w in widths])
            res = {str(widths[i]): round(float(v) * k / 1000, 2) for i, v in per.items()}
            rec["tray"] = {w: {"orient": "vertikal" if vertical else "horizontal", "m": v} for w, v in res.items()}
            rec["tray_total_m"] = round(float(tot) * k / 1000, 2)
            rec["tray_callouts"] = {str(w): sum(1 for c in call if c["w"] == w) for w in widths}
            if len(widths) > 1: rec["flags"].append(f"lebar tray >1 ({widths}): pembagian panjang per lebar = estimasi lebar raster; total lebih andal")
            if vertical: rec["flags"].append("tray vertikal dari section = BATAS ATAS (tray yang sama bisa tampak di sheet section lain)")
            T.write_overlay(m, sk, os.path.join(out, "overlay", f"{tag}_tray.png"))
    # --- conduit
    labs_all, unp = conduit_labels(ocr_words_); rec["unpaired"] = unp
    labs = [l for l in labs_all if l["size"] in CONDUIT_SIZES]
    cab = [l for l in labs_all if l["size"] > max(CONDUIT_SIZES)]
    bad = [l for l in labs_all if l["size"] <= max(CONDUIT_SIZES) and l["size"] not in CONDUIT_SIZES]
    rec["cables_in_tray"] = [{"size": l["size"], "type": l["type"], "el": l["el"]} for l in cab]
    if cab: rec["flags"].append(f"{len(cab)} label >{max(CONDUIT_SIZES)} mm ({sorted({l['size'] for l in cab})}) = kabel pada tray/ladder, BUKAN conduit; dikeluarkan dari hitungan conduit")
    if bad: rec["flags"].append(f"{len(bad)} label ukuran di luar daftar conduit ({sorted({l['size'] for l in bad})}): kemungkinan salah baca OCR, dikeluarkan; cek visual")
    for l in labs: l["x_pt"], l["y_pt"] = l["x"] * PX_TO_PT, l["y"] * PX_TO_PT
    rec["labels"] = [{k2: l[k2] for k2 in ("size", "type", "el", "conf", "known", "low_conf", "x_pt", "y_pt")} for l in labs]
    if row["items"].get("conduit"):
        segs, curves = conduit_segments(drs, cfg["colors"]["conduit"], cfg["color_tol"], xmax)
        if curves: rec["flags"].append(f"{curves} kurva hijau (tikungan) tidak ikut terukur; panjang sedikit kurang")
        m, lab, n = components(p, cfg, drs, px, xmax, cfg["close_mm"]["conduit"] / k)
        comp = collections.defaultdict(lambda: {"h": 0.0, "v": 0.0, "d": 0.0, "labels": []})
        for s in segs:
            c = comp_of(lab, (s[0] + s[2]) / 2, (s[1] + s[3]) / 2, px)
            comp[c][orient(s)] += math.hypot(s[2] - s[0], s[3] - s[1]) * k / 1000
        comp.pop(0, None)
        for l in labs:
            c, dist = nearest_comp(lab, l["x_pt"] * px, l["y_pt"] * px, px)
            l["comp"], l["dist_pt"] = c, dist
            if c in comp: comp[c]["labels"].append(l)
            else: rec["flags"].append(f"label {l['size']}mm {l['type']} tanpa rute hijau")
        far = [l for l in labs if l.get("dist_pt") and l["dist_pt"] > 150]
        if far: rec["flags"].append(f"{len(far)} label berjarak >150 pt dari rute hijau terdekat (penempatan label meragukan)")
        runs = collections.defaultdict(lambda: {"h": 0.0, "v": 0.0, "d": 0.0, "n": 0})
        for c, d in comp.items():
            if not d["labels"]:
                for o in "hvd": rec["conduit_unlabeled_m"][o] = round(rec["conduit_unlabeled_m"].get(o, 0) + d[o], 2)
                continue
            tot_c = d["h"] + d["v"] + d["d"]
            if tot_c > 30 or len(d["labels"]) > 3: rec["flags"].append(f"rute #{c}: {tot_c:.0f} m dengan {len(d['labels'])} label = kemungkinan gabungan banyak garis hijau (hatch/trafo/ground); alokasi label TIDAK ANDAL, pakai overlay")
            for l in d["labels"]:
                r = runs[(l["size"], l["type"])]; r["n"] += 1
                for o in "hvd": r[o] += d[o]
            els = [l["el"] for l in d["labels"] if l["el"]]
            if len(els) >= 2 and d["v"] > 0:
                span = (max(els) - min(els)) / 1000
                if abs(span - d["v"]) > 0.1 * max(span, d["v"]): rec["flags"].append(f"rute #{c}: selisih EL label {span:.2f} m vs geometri vertikal {d['v']:.2f} m (beda >10%)")
                rec.setdefault("el_check", []).append({"comp": c, "el_span_m": round(span, 3), "geom_v_m": round(d["v"], 3)})
        rec["conduit_runs"] = [{"size": s, "type": t, "labels": r["n"], "horizontal_m": round(r["h"], 2), "vertikal_m": round(r["v"], 2), "miring_m": round(r["d"], 2)}
                               for (s, t), r in sorted(runs.items())]
        if role == "section" and any(r["vertikal_m"] for r in rec["conduit_runs"]): rec["flags"].append("conduit vertikal dari section = batas atas (belum dedup antar-section)")
        import cv2
        img = cv2.cvtColor(cv2.resize(m, None, fx=0.25, fy=0.25, interpolation=cv2.INTER_AREA), cv2.COLOR_GRAY2BGR)
        for l in labs:
            cv2.putText(img, f"{l['size']}{l['type'][0]}>{l.get('comp')}", (int(l["x_pt"] * px * 0.25), int(l["y_pt"] * px * 0.25)), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 255), 1)
        cv2.imwrite(os.path.join(out, "overlay", f"{tag}_conduit_labels.png"), img)
    if unp: rec["flags"].append(f"{len(unp)} token ukuran conduit tanpa jenis (OCR): {[u['size'] for u in unp]}; cek visual")
    low = [l for l in labs if l["low_conf"]]
    if low: rec["flags"].append(f"{len(low)} label conduit confidence OCR <{C.LOW_CONF}: cek visual")
    return rec


# ------------------------------------------------------------ support + elevasi
def parse_supports(doc, rows):
    sup = {}
    for r in rows:
        if r["role"] != "detail": continue
        words = doc[r["sheet"] - 1].get_text("words")
        pw = doc[r["sheet"] - 1].rect.width
        codes = [(w, SUP_RE.match(w[4])) for w in words if SUP_RE.match(w[4]) and w[0] < 0.88 * pw]
        qty = []
        for i, w in enumerate(words):
            if w[4].lower() == "ea":
                prev = [x for x in words if x[4].isdigit() and abs(x[1] - w[1]) < 6 and 0 <= w[0] - x[2] < 30]
                if prev: qty.append((prev[0], int(prev[0][4])))
        pairs = sorted(((math.hypot(c[0][0] - q[0][0], c[0][1] - q[0][1]), i, j) for i, c in enumerate(codes) for j, q in enumerate(qty)))
        ui, uj = set(), set()
        for d, i, j in pairs:
            if i in ui or j in uj: continue
            ui.add(i); uj.add(j); w, m = codes[i]
            sup[w[4].upper()] = {"orient": "H" if m.group(1).upper() == "H" else "V", "type": m.group(2), "letter": m.group(3).upper(),
                                 "width": LETTER_W[m.group(3).upper()], "mount": m.group(4).upper(), "qty": qty[j][1], "sheet": r["sheet"], "dist_pt": round(d)}
        for i, (w, m) in enumerate(codes):
            if i not in ui: print(f"  (support {w[4]} di sheet {r['sheet']} tanpa qty 'n Ea' terbaca: diabaikan)", file=sys.stderr)
    return sup


def spacing_checks(sheets, sup, cfg):
    lo, hi = cfg["spacing_range_m"]; out = []
    for ori, key in (("H", "horizontal"), ("V", "vertikal")):
        tray = collections.defaultdict(float)
        for r in sheets:
            for w, d in r["tray"].items():
                if d["orient"] == key: tray[int(w)] += d["m"]
        q = collections.defaultdict(int)
        for s in sup.values():
            if s.get("qty") and s["orient"] == ori: q[s["width"]] += s["qty"]
        for w in sorted(set(tray) | set(q)):
            if not tray.get(w) or not q.get(w): out.append(f"tray {w}W {key}: tray {tray.get(w, 0):.1f} m, support {ori} qty {q.get(w, 0)}: tidak bisa dicocokkan"); continue
            sp = tray[w] / q[w]
            out.append(f"tray {w}W {key}: {tray[w]:.1f} m / {q[w]} support = {sp:.2f} m per support" + ("" if lo <= sp <= hi else f"  PERINGATAN: di luar {lo}-{hi} m"))
    return out


def plan_titles(doc, rows):
    lv = set()
    for r in rows:
        if r["role"] == "plan":
            lv |= {int(x) for x in re.findall(r"PLAN AT EL\s*\+\s*(\d{3,5})", doc[r["sheet"] - 1].get_text())}
    return sorted(lv)


# ------------------------------------------------------------ plan / execute
def plan(pdf, cfg, out, only=None, budget=240, px=None):
    import pymupdf as fitz
    px = px or cfg["px_per_pt"]; doc = fitz.open(pdf); inv = T.inspect(pdf, cfg)
    os.makedirs(os.path.join(out, "overlay"), exist_ok=True)
    rows = [r for r in inv["sheets"]]; todo = [r for r in rows if r["role"] in ("plan", "section") and r["items"] and (not only or r["sheet"] in only)]
    t0 = time.time(); sheets = []
    for r in todo:
        if time.time() - t0 > budget:
            print(f"BELUM selesai ({len(sheets)}/{len(todo)} sheet). Ulangi perintah yang sama (OCR sudah di-cache)."); return None
        sheets.append(process_sheet(doc, r, cfg, out, px, page_ocr(doc, r["sheet"], out)))
    sup = parse_supports(doc, rows); plan_lv = plan_titles(doc, rows)
    sec_lv = sorted({l for s in sheets for l in s["levels"]})
    top = []
    for s in sheets:
        if s["scale_status"] == "KONFLIK": top.append(f"sheet {s['sheet']}: " + next(f for f in s["flags"] if f.startswith("KONFLIK")))
    if plan_lv and sec_lv and not set(plan_lv) <= set(sec_lv):
        top.append(f"elevasi: judul plan EL+{plan_lv} tidak sama dengan level lantai section {sec_lv} (beda acuan/ketinggian, cek)")
    res = {"file": os.path.basename(pdf), "manifest": T.source_manifest(pdf, cfg, mode="sheetdetail", px=px, dpi=DPI),
           "sheets": sheets, "supports": sup, "spacing": spacing_checks(sheets, sup, cfg), "top_warnings": top,
           "plan_levels": plan_lv, "section_levels": sec_lv}
    with open(os.path.join(out, "sheetdetail.json"), "w", encoding="utf-8") as fh: json.dump(res, fh, ensure_ascii=False, indent=1, default=float)
    print_plan(res); return res


def print_plan(res):
    print("## DRY-RUN detail per sheet (belum ada Excel) - semua angka PROVISIONAL\n")
    if res["top_warnings"]:
        print("**Peringatan utama:**"); [print(f"- {w}") for w in res["top_warnings"]]; print()
    for s in res["sheets"]:
        print(f"### Sheet {s['sheet']} ({s['role']}), skala view 1:{s['scale']} [{s['scale_status']}]")
        if s["tray"]: print("Tray: " + "; ".join(f"W{w} {d['orient']} {d['m']} m" for w, d in sorted(s["tray"].items(), key=lambda x: int(x[0]))))
        if s["conduit_runs"]:
            print("| Conduit | Jenis | Label | Horizontal m | Vertikal m | Miring m |\n|---|---|---|---|---|---|")
            for r in s["conduit_runs"]: print(f"| {r['size']} mm | {r['type'].title()} | {r['labels']} | {r['horizontal_m']} | {r['vertikal_m']} | {r['miring_m']} |")
        if s["conduit_unlabeled_m"]: print(f"Conduit tanpa label: {s['conduit_unlabeled_m']} (m, h/v/d)")
        for f in s["flags"]: print(f" - {f}")
        print()
    tt = collections.defaultdict(float); ct = collections.defaultdict(lambda: [0, 0.0, 0.0, 0.0])
    for s in res["sheets"]:
        for w, d in s["tray"].items(): tt[(int(w), d["orient"])] += d["m"]
        for r in s["conduit_runs"]:
            c = ct[(r["size"], r["type"])]; c[0] += r["labels"]; c[1] += r["horizontal_m"]; c[2] += r["vertikal_m"]; c[3] += r["miring_m"]
    print("### Total semua sheet (vertikal = batas atas, duplikat antar-section belum dibuang)")
    print("Tray: " + "; ".join(f"W{w} {o} {v:.1f} m" for (w, o), v in sorted(tt.items())))
    print("| Conduit | Jenis | Label | H m | V m | Miring m |\n|---|---|---|---|---|---|")
    for (sz, ty), c in sorted(ct.items()): print(f"| {sz} mm | {ty.title()} | {c[0]} | {c[1]:.1f} | {c[2]:.1f} | {c[3]:.1f} |")
    print("\nSupport (sheet detail): " + (", ".join(f"{k}={v['qty']}" for k, v in res["supports"].items()) or "tidak terbaca"))
    print("Cek jarak support:"); [print(f" - {c}") for c in res["spacing"]]
    print("\nBatas: +/-5%, tanpa waste; aksesori, fitting, busduct belum dihitung. Gambar berstatus perlu dicek (komentar reviewer); angka bisa berubah di revisi.")


def execute(out, expected):
    from openpyxl import Workbook
    from openpyxl.styles import Font
    with open(os.path.join(out, "sheetdetail.json"), encoding="utf-8") as fh: res = json.load(fh)
    T.validate_plan_manifest(res, expected)
    wb = Workbook(); ws = wb.active; ws.title = "Tray per Sheet"
    ws.append(["Sheet", "Peran", "Skala 1:", "Status skala", "Lebar tray (mm)", "Orientasi", "Panjang (m)"])
    for s in res["sheets"]:
        for w, d in s["tray"].items(): ws.append([s["sheet"], s["role"], s["scale"], s["scale_status"], int(w), d["orient"], d["m"]])
    ws.append(["TOTAL", "", "", "", "", "", f"=SUM(G2:G{ws.max_row})"])
    wc = wb.create_sheet("Conduit per Sheet"); wc.append(["Sheet", "Ukuran (mm)", "Jenis", "Jumlah label", "Horizontal (m)", "Vertikal (m, batas atas)", "Miring (m)"])
    for s in res["sheets"]:
        for r in s["conduit_runs"]: wc.append([s["sheet"], r["size"], r["type"], r["labels"], r["horizontal_m"], r["vertikal_m"], r["miring_m"]])
    n = wc.max_row; wc.append(["TOTAL", "", ""] + [f"=SUM({c}2:{c}{n})" for c in "DEFG"])
    wsu = wb.create_sheet("Support"); wsu.append(["Kode", "Orientasi", "Ukuran tray (mm)", "Tumpuan", "Qty", "Sheet"])
    for k, v in res["supports"].items(): wsu.append([k, v.get("orient"), v.get("width"), v.get("mount"), v.get("qty"), v.get("sheet")])
    wn = wb.create_sheet("Catatan"); wn.column_dimensions["A"].width = 150
    wn.append(["Hasil PROVISIONAL: ukur vektor + OCR label, +/-5%, tanpa waste. Penempatan label conduit ke rute = komponen terdekat (cek overlay)."]); wn["A1"].font = Font(bold=True)
    for t in res["top_warnings"] + res["spacing"] + [f"sheet {s['sheet']}: {f}" for s in res["sheets"] for f in s["flags"]]: wn.append([t])
    path = os.path.join(out, "Detail_per_Sheet.xlsx"); wb.save(path); print("Excel:", path)


def main():
    ap = argparse.ArgumentParser(); sp = ap.add_subparsers(dest="cmd", required=True)
    for n in ("plan", "execute"):
        s = sp.add_parser(n); s.add_argument("pdf"); s.add_argument("--out", required=True); s.add_argument("--config")
        s.add_argument("--scale", action="append", default=[]); s.add_argument("--sheets"); s.add_argument("--budget", type=int, default=240)
        if n == "execute": s.add_argument("--confirm", action="store_true")
    a = ap.parse_args(); cfg = T.load_config(a.config)
    for sc in a.scale: k, v = sc.split("="); cfg["scales"][k] = int(v)
    os.makedirs(a.out, exist_ok=True)
    if a.cmd == "plan": plan(a.pdf, cfg, a.out, {int(x) for x in a.sheets.split(",")} if a.sheets else None, a.budget); return
    if not a.confirm: sys.exit("Ditolak: execute hanya setelah user menyetujui dry-run (tambahkan --confirm).")
    if not os.path.exists(os.path.join(a.out, "sheetdetail.json")): sys.exit("sheetdetail.json tidak ada: jalankan plan dulu.")
    try: execute(a.out, T.source_manifest(a.pdf, cfg, mode="sheetdetail", px=cfg["px_per_pt"], dpi=DPI))
    except T.PlanMismatchError as e: sys.exit(str(e))


if __name__ == "__main__": main()
