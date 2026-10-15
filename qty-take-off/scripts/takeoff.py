#!/usr/bin/env python3
"""qty-take-off: ukur panjang cable tray (garis ungu) dan conduit (garis hijau) dari PDF shop drawing VEKTOR.

  python takeoff.py inspect PDF --out DIR                 # inventaris warna/skala/peran per sheet (tanpa hitung)
  python takeoff.py plan    PDF --out DIR [--config F] [--scale 3=200] [--sheets 5,14]   # DRY-RUN: hitung + QA
  python takeoff.py execute PDF --out DIR --confirm       # tulis Excel dari hasil plan (hanya setelah user setuju)

Anti-bug: skala dicek dua arah (label vs geometri grid); peran sheet dikonfirmasi user; tray = garis tengah
(bukan jumlah garis); vertikal conduit = BATAS ATAS (belum dedup antar-section); overlay PNG untuk cek visual;
cross-check jarak support. Angka tidak diketik ulang manual."""
import argparse, collections, hashlib, json, math, os, re, sys
import numpy as np

PT_MM = 25.4 / 72.0                      # mm kertas per titik PDF
HERE = os.path.dirname(os.path.abspath(__file__))
SEC_RE = re.compile(r"SECTION\s*\n?\s*SCALE")
LEGEND_RE = re.compile(r"\b([A-K])\s*=\s*(\d{2,4})\s*W\s*x\s*(\d{2,4})\s*H", re.I)
TRAY_CALLOUT_RE = re.compile(
    r"(?:CABLE\s+)?(?:TRAY|LADDER)\b.{0,80}?(\d{2,4})\s*(?:\(\s*W\s*\)|W)\s*[x×]\s*"
    r"(\d{2,4})\s*(?:\(\s*H\s*\)|H)\s*MM\b", re.I | re.S)
SUPPORT_RE = re.compile(r"(SU[HV]-\d+([A-K])[A-Z])\s*\n?\s*QTY\s*\n?\s*(\d+)\s*EA", re.I)


def load_config(path=None):
    cfg = json.load(open(os.path.join(HERE, "config.default.json"), encoding="utf-8"))
    if path: cfg.update(json.load(open(path, encoding="utf-8")))
    return cfg


class PlanMismatchError(ValueError):
    pass


def source_manifest(path, cfg, **options):
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    config = json.dumps(cfg, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return {
        "file": os.path.basename(path),
        "sha256": digest.hexdigest(),
        "config_sha256": hashlib.sha256(config).hexdigest(),
        "options": options,
    }


def validate_plan_manifest(result, expected):
    if result.get("manifest") != expected:
        raise PlanMismatchError(
            "Sumber atau konfigurasi tidak cocok dengan dry-run. Jalankan plan ulang "
            "di folder output yang sama sebelum execute."
        )


def iscol(c, t, tol=0.05):
    return bool(c) and all(abs(a - b) <= tol for a, b in zip(c, t))


# ------------------------------------------------------------ teks / peran / skala
def guess_role(text):
    """Jenis halaman dari teks. 'SECTION' berdiri sendiri (atau SECTION-A) = section; 'PLAN AT EL' = plan.
    Bila keduanya ada, yang lebih banyak menang (judul sheet section memuat beberapa label SECTION)."""
    t = text.upper(); lines = [l.strip() for l in t.split("\n") if l.strip()]
    if "CABLE LIST" in t: return "list"
    if re.search(r"\bDETAIL\s+[A-Z]\d", t) or "SUPPORT NO." in t: return "detail"
    n_sec = sum(1 for l in lines if re.fullmatch(r"SECTION(?:\s*[-:]?\s*[A-Z]{1,2})?", l)) + len(SEC_RE.findall(t))
    n_plan = t.count("PLAN AT EL")
    if n_sec and n_sec > n_plan: return "section"
    if n_plan: return "plan"
    return "other"


def label_scales(text):
    return collections.Counter(int(x) for x in re.findall(r"\b1\s*:\s*(\d{2,4})\b", text))


def vertical_x(page, xmax, minx=40, drawings=None):
    acc = collections.defaultdict(float)
    for dr in (drawings if drawings is not None else page.get_cdrawings()):
        for it in dr["items"]:
            if it[0] == "l":
                a, b = it[1], it[2]
                if abs(a[0] - b[0]) < 0.05 and abs(a[1] - b[1]) > 3 and minx < a[0] < xmax:
                    acc[round(a[0] * 2) / 2] += abs(a[1] - b[1])
    return sorted(x for x, l in acc.items() if l >= 250)


def grid_scale(xs, gap_seqs, tol=0.03):
    """Cocokkan posisi garis grid dengan deret jarak (mm) yang diketahui; garis lain (noise) di antaranya diabaikan.
    Return mm per pt atau None. Butuh minimal 4 garis grid cocok agar tidak kebetulan."""
    best = None
    for seq in gap_seqs:
        for s in (seq, seq[::-1]):
            cum = [0]
            for g in s: cum.append(cum[-1] + g)
            for i, x0 in enumerate(xs):
                for j in range(i + 1, len(xs)):
                    for k in range(3, len(cum)):
                        dx = xs[j] - x0
                        if dx < 40: continue
                        r = cum[k] / dx                      # mm per pt kandidat
                        ok = all(any(abs(xx - (x0 + c / r)) <= tol * (s[min(m, len(s) - 1)] / r) for xx in xs) for m, c in enumerate(cum[:k + 1]))
                        if ok and (best is None or k > best[1]): best = (r, k)
    return best if best else None


def snap_scale(r, standards=(20, 25, 50, 75, 100, 120, 150, 200, 250, 300, 500), tol=0.03):
    """mm/pt -> penyebut skala standar terdekat (dalam toleransi) atau None. Menolak hasil kebetulan seperti 1:88."""
    n = r / PT_MM
    c = min(standards, key=lambda v: abs(v - n))
    return c if abs(c - n) / c <= tol else None


def legend_widths(text):
    return {k.upper(): (int(w), int(h)) for k, w, h in LEGEND_RE.findall(text)}


def tray_callout_widths(text):
    return sorted({int(w) for w, _ in TRAY_CALLOUT_RE.findall(text)})


def parse_supports(text):
    return {m.group(1).upper(): {"qty": int(m.group(3)), "letter": m.group(2).upper()} for m in SUPPORT_RE.finditer(text)}


def tray_width_candidates(row, cfg):
    """Callout tray jadi sumber utama; berikutnya lebar support/legenda, lalu konfigurasi."""
    callouts = row.get("tray_callout_widths", [])
    if callouts: return sorted(set(map(int, callouts)))
    legend = row.get("legend", {})
    support_widths = {
        int(legend[s["letter"]][0])
        for s in row.get("supports", {}).values()
        if s["letter"] in legend
    }
    if support_widths: return sorted(support_widths)
    widths = {int(w) for w, _ in legend.values()}
    return sorted(widths or set(map(int, cfg["tray_widths_mm"])))


# ------------------------------------------------------------ raster + skeleton
def make_mask(page, col, tol, px, xmax, kind="all", drawings=None):
    import cv2
    m = np.zeros((int(page.rect.height * px), int(page.rect.width * px)), np.uint8)
    for dr in (drawings if drawings is not None else page.get_cdrawings()):
        if not iscol(dr.get("color"), col, tol): continue
        for it in dr["items"]:
            if it[0] != "l": continue
            ax, ay, bx, by = it[1][0], it[1][1], it[2][0], it[2][1]
            if (ax > xmax and bx > xmax) or math.hypot(bx - ax, by - ay) < 0.3: continue
            ang = abs(math.degrees(math.atan2(by - ay, bx - ax))) % 180
            isv, ish = abs(ang - 90) < 3, (ang < 3 or ang > 177)
            if kind == "all" or (kind == "v" and isv) or (kind == "h" and ish):
                cv2.line(m, (int(ax * px), int(ay * px)), (int(bx * px), int(by * px)), 255, 2)
    return m


def edge_lengths(sk, px, cls=None):
    """Panjang skeleton (pt): sisi lurus 1, diagonal sqrt2. Dengan cls -> dict kelas -> pt."""
    sk = sk.astype(bool); out = collections.defaultdict(float)
    S, N, E, W = slice(1, None), slice(None, -1), slice(1, None), slice(None, -1)
    for sa, sb, w in (((slice(None), E), (slice(None), W), 1.0), ((S, slice(None)), (N, slice(None)), 1.0),
                      ((S, E), (N, W), math.sqrt(2)), ((S, W), (N, E), math.sqrt(2))):
        both = sk[sa] & sk[sb]
        if cls is None: out[0] += both.sum() * w
        else:
            for k in np.unique(cls[sa][both]): out[int(k)] += (cls[sa][both] == k).sum() * w
    return {k: v / px for k, v in out.items()}


def measure(m, close_pt, px, widths_pt=None, thick_pt=0.6):
    """-> (total_pt, {indeks_lebar: pt}, skeleton). Lebar lokal dari distance transform, diklasifikasi ke lebar terdekat."""
    import cv2
    from skimage.morphology import skeletonize
    from scipy import ndimage as ndi
    if not m.any(): return 0.0, {}, m > 0
    k = max(1, round(close_pt * px))
    mc = cv2.morphologyEx(m, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (k, k))) if close_pt > 0 else m
    sk = skeletonize(mc > 0)
    if not widths_pt: return sum(edge_lengths(sk, px).values()), {}, sk
    w = 2 * ndi.distance_transform_edt(mc > 0) / px
    exp = np.array(widths_pt) + thick_pt
    cls = np.zeros(sk.shape, np.int16); ys, xs = np.nonzero(sk)
    cls[ys, xs] = np.argmin(np.abs(w[ys, xs][:, None] - exp[None, :]), axis=1) + 1
    per = edge_lengths(sk, px, cls)
    return sum(per.values()), {i - 1: v for i, v in per.items() if i > 0}, sk


def write_overlay(mask, sk, path):
    import cv2
    a = cv2.resize(mask, None, fx=0.25, fy=0.25, interpolation=cv2.INTER_AREA)
    img = cv2.cvtColor(a, cv2.COLOR_GRAY2BGR)
    img[cv2.resize(sk.astype(np.uint8) * 255, None, fx=0.25, fy=0.25, interpolation=cv2.INTER_AREA) > 0] = (0, 0, 255)
    cv2.imwrite(path, img)


# ------------------------------------------------------------ inventaris + hitung
def inspect(pdf, cfg):
    import pymupdf as fitz
    doc = fitz.open(pdf); rows = []
    for i, p in enumerate(doc, 1):
        text = p.get_text(); cnt = collections.Counter()
        for dr in p.get_drawings():
            for name, col in cfg["colors"].items():
                if iscol(dr.get("color"), col, cfg["color_tol"]): cnt[name] += len(dr["items"])
        g = grid_scale(vertical_x(p, p.rect.width * cfg["content_xmax_frac"]), cfg["grid_gaps_mm"])
        rows.append({"sheet": i, "role": cfg["roles"].get(str(i), guess_role(text)), "items": dict(cnt),
                     "label_scales": dict(label_scales(text)), "geometry_scale": snap_scale(g[0]) if g else None,
                     "geometry_lines": (g[1] + 1) if g else 0,
                     "supports": parse_supports(text), "legend": legend_widths(text),
                     "tray_callout_widths": tray_callout_widths(text)})
    return {"file": os.path.basename(pdf), "pages": len(doc), "vector_ok": any(r["items"] for r in rows), "sheets": rows}


def resolve_scale(row, cfg):
    """Prioritas: override > geometri grid > label. Mengembalikan (N, status, peringatan)."""
    lab = max(row["label_scales"], key=row["label_scales"].get) if row["label_scales"] else None
    geo = row["geometry_scale"]
    if str(row["sheet"]) in cfg["scales"]: return int(cfg["scales"][str(row["sheet"])]), "override", None
    if geo and lab and abs(geo - lab) / lab > 0.03:
        if row.get("geometry_lines", 0) >= 9:
            return geo, "geometri", f"label skala 1:{lab} TIDAK cocok dengan geometri grid 1:{geo} ({row['geometry_lines']} garis grid cocok); dipakai 1:{geo}"
        return lab, "label-saja", f"label 1:{lab} vs geometri 1:{geo} bertentangan tetapi bukti grid lemah ({row.get('geometry_lines', 0)} garis); dipakai label, WAJIB dicek manual"
    if geo: return geo, "geometri", None
    if lab: return lab, "label-saja", f"skala 1:{lab} hanya dari label, belum terverifikasi geometri (grid tidak terdeteksi)"
    return None, "tidak-ada", "skala tidak ditemukan"


def crosscheck(tray, sup, legend, cfg):
    lo, hi = cfg["spacing_range_m"]; byw = collections.defaultdict(int); out = []
    for d in sup.values():
        w = legend.get(d["letter"], (None,))[0]
        if w: byw[str(w)] += d["qty"]
    for w, L in tray.items():
        q = byw.get(w)
        if not q: out.append(f"tray {w}W: qty support tidak terbaca, tidak bisa dicocokkan"); continue
        sp = L / q
        out.append(f"tray {w}W: {L:.1f} m / {q} support = {sp:.2f} m per support" + ("" if lo <= sp <= hi else f"  PERINGATAN: di luar {lo}-{hi} m"))
    return out


def plan(pdf, cfg, out, only=None):
    import pymupdf as fitz
    inv = inspect(pdf, cfg)
    if not inv["vector_ok"]:
        raise SystemExit("PDF tidak memuat garis vektor berwarna tray/conduit (mungkin scan/raster). Takeoff otomatis tidak andal; minta PDF vektor dari CAD.")
    doc = fitz.open(pdf); px = cfg["px_per_pt"]
    os.makedirs(os.path.join(out, "overlay"), exist_ok=True); sheets = []
    for row in inv["sheets"]:
        if (only and row["sheet"] not in only) or not row["items"]: continue
        role = row["role"]; N, st, fl = resolve_scale(row, cfg)
        rec = {"sheet": row["sheet"], "role": role, "scale": N, "scale_status": st, "tray_m": {},
               "tray_length_m": 0.0, "tray_vertical_length_m": 0.0, "tray_vertical_m": {},
               "conduit_h_m": 0.0, "conduit_v_m": 0.0, "flags": [fl] if fl else []}
        sheets.append(rec)
        if N is None: rec["flags"].append("dilewati: skala tidak diketahui"); continue
        k = N * PT_MM; p = doc[row["sheet"] - 1]; xmax = p.rect.width * cfg["content_xmax_frac"]; tag = f"sheet{row['sheet']:02d}"
        if row["items"].get("tray"):
            if role in cfg["tray_from"]:
                is_vertical = role in cfg.get("tray_vertical_from", [])
                widths = tray_width_candidates(row, cfg)
                m = make_mask(p, cfg["colors"]["tray"], cfg["color_tol"], px, xmax,
                              "v" if is_vertical else "all")
                tray_pt, per, sk = measure(m, cfg["close_mm"]["tray"] / k, px, [w / k for w in widths])
                rec["tray_m"] = {str(widths[i]): round(float(v) * k / 1000, 1) for i, v in per.items()}
                rec["tray_length_m"] = round(float(tray_pt) * k / 1000, 3)
                if is_vertical:
                    rec["tray_vertical_m"] = dict(rec["tray_m"])
                    rec["tray_vertical_length_m"] = rec["tray_length_m"]
                    rec["flags"].append("tray vertikal dari section = batas atas, belum didedup antar-section")
                write_overlay(m, sk, os.path.join(out, "overlay", f"{tag}_tray.png"))
            else: rec["flags"].append(f"tray ada di sheet peran '{role}' tidak dihitung (hanya dari {cfg['tray_from']})")
        if row["items"].get("conduit"):
            if role in cfg["conduit_horizontal_from"]:
                m = make_mask(p, cfg["colors"]["conduit"], cfg["color_tol"], px, xmax)
                tot, _, sk = measure(m, cfg["close_mm"]["conduit"] / k, px)
                rec["conduit_h_m"] = round(tot * k / 1000, 1)
                write_overlay(m, sk, os.path.join(out, "overlay", f"{tag}_conduit.png"))
            if role in cfg["conduit_vertical_from"]:
                m = make_mask(p, cfg["colors"]["conduit"], cfg["color_tol"], px, xmax, "v")
                tot, _, _ = measure(m, cfg["close_mm"]["conduit"] / k, px)
                rec["conduit_v_m"] = round(tot * k / 1000, 1)
                rec["flags"].append("vertikal dari section = batas atas, belum dedup antar-section")
    tray = collections.defaultdict(float); tray_plan = collections.defaultdict(float)
    tray_vertical = collections.defaultdict(float); tray_length = tray_plan_length = tray_vertical_length = 0.0
    sup = {}; legend = {}
    for r in sheets:
        tray_length += r["tray_length_m"]
        tray_vertical_length += r["tray_vertical_length_m"]
        tray_plan_length += r["tray_length_m"] - r["tray_vertical_length_m"]
        for w, v in r["tray_m"].items():
            tray[w] += v
            if w in r["tray_vertical_m"]: tray_vertical[w] += v
            else: tray_plan[w] += v
    for row in inv["sheets"]: sup.update(row["supports"]); legend.update(row["legend"])
    res = {"file": inv["file"], "manifest": source_manifest(pdf, cfg, mode="pdf", tray_width_model="callout-candidate-raster-v1"),
           "sheets": sheets, "tray_total_m": {w: round(float(v), 1) for w, v in tray.items()},
           "tray_length_total_m": round(tray_length, 1), "tray_plan_length_m": round(tray_plan_length, 1),
           "tray_vertical_upper_length_m": round(tray_vertical_length, 1),
           "tray_plan_m": {w: round(float(v), 1) for w, v in tray_plan.items()},
           "tray_vertical_upper_m": {w: round(float(v), 1) for w, v in tray_vertical.items()},
           "conduit_h_total_m": round(sum(r["conduit_h_m"] for r in sheets), 1),
           "conduit_v_upper_m": round(sum(r["conduit_v_m"] for r in sheets), 1),
           "supports": sup, "checks": crosscheck(dict(tray_plan), sup, legend, cfg)}
    for name, obj in (("plan.json", res), ("inventory.json", inv)):
        with open(os.path.join(out, name), "w", encoding="utf-8") as fh: json.dump(obj, fh, ensure_ascii=False, indent=1)
    return res


# ------------------------------------------------------------ output
def print_plan(res):
    print("## DRY-RUN takeoff (belum ada Excel)\n")
    print("| Sheet | Peran | Skala (status) | Tray m per lebar (section vertikal = batas atas) | Conduit horizontal m | Conduit vertikal m (batas atas) |\n|---|---|---|---|---|---|")
    for r in res["sheets"]:
        tr = ", ".join(f"{k}W={v}" for k, v in r["tray_m"].items()) or "-"
        print(f"| {r['sheet']} | {r['role']} | 1:{r['scale']} ({r['scale_status']}) | {tr} | {r['conduit_h_m'] or '-'} | {r['conduit_v_m'] or '-'} |")
    plan_m = res.get("tray_plan_m", res["tray_total_m"])
    vertical_m = res.get("tray_vertical_upper_m", {})
    print(f"\nTray total per lebar (m, termasuk section vertikal batas atas): {res['tray_total_m']} | "
          f"panjang total {res.get('tray_length_total_m', sum(res['tray_total_m'].values()))} m | "
          f"plan {res.get('tray_plan_length_m', sum(plan_m.values())):.1f} m | "
          f"section vertikal batas atas {res.get('tray_vertical_upper_length_m', sum(vertical_m.values())):.1f} m")
    print("\nCross-check support:"); [print(" - " + c) for c in res["checks"]]
    fl = [(r["sheet"], f) for r in res["sheets"] for f in r["flags"]]
    if fl: print("\nPeringatan:"); [print(f" - sheet {s}: {f}") for s, f in fl]
    if res.get("source") == "cad":
        import cad
        cad.print_extra(res["sheets"][0])


def execute(out, expected_manifest):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    with open(os.path.join(out, "plan.json"), encoding="utf-8") as fh: res = json.load(fh)
    validate_plan_manifest(res, expected_manifest)
    wb = Workbook(); ws = wb.active; ws.title = "Per Sheet"
    widths = sorted({w for r in res["sheets"] for w in r["tray_m"]}, key=lambda x: (not x.isdigit(), int(x) if x.isdigit() else 0, x)) or ["200", "700"]
    ws.append(["Sheet", "Peran", "Skala 1:", "Status skala"] + [f"Tray {w}W (m)" if w.isdigit() else f"Tray {w} (m)" for w in widths] + ["Conduit horizontal (m)", "Conduit vertikal batas atas (m)", "Catatan"])
    for c in ws[1]:
        c.font = Font(name="Arial", bold=True, color="FFFFFF"); c.fill = PatternFill("solid", fgColor="305496"); c.alignment = Alignment(wrap_text=True)
    for r in res["sheets"]:
        ws.append([r["sheet"], r["role"], r["scale"], r["scale_status"]] + [r["tray_m"].get(w, 0) for w in widths] + [r["conduit_h_m"], r["conduit_v_m"], "; ".join(r["flags"])])
    last = ws.max_row; from openpyxl.utils import get_column_letter as CL
    ws.append(["TOTAL", "", "", ""] + [f"=SUM({CL(5 + i)}2:{CL(5 + i)}{last})" for i in range(len(widths) + 2)])
    for c in ws[ws.max_row]: c.font = Font(name="Arial", bold=True)
    for i in range(1, ws.max_column + 1): ws.column_dimensions[CL(i)].width = 90 if i == ws.max_column else 16
    wc = wb.create_sheet("Catatan")
    source_note = ("Catatan takeoff: panjang CAD diukur dari entitas setelah konversi DWG/DXF; hasil bergantung pada satuan "
                   "gambar, pemetaan layer, dan pemisahan view. Belum termasuk waste."
                   if res.get("source") == "cad"
                   else "Catatan takeoff: ukur vektor PDF, akurasi sekitar +/-5%, belum termasuk waste.")
    wc.append([source_note]); wc["A1"].font = Font(name="Arial", bold=True)
    for c in res["checks"]: wc.append([c])
    if res.get("source") == "cad":
        import cad
        cad.add_cad_sheets(wb, res["sheets"][0])
        wc.append(["Garis tumpang tindih pada geometri yang sama digabung; pemisahan kategori tetap mengikuti layer CAD."])
    else:
        wc.append(["Tray vertikal dari section = batas atas dan belum didedup antar-section."])
        wc.append(["Conduit vertikal = batas atas: section menampilkan conduit yang sama (belum dedup)."])
    wc.append(["Support (qty di sheet detail): " + ", ".join(f"{k}={v['qty']}" for k, v in res["supports"].items())])
    wc.column_dimensions["A"].width = 140
    path = os.path.join(out, "Takeoff_Tray_Conduit.xlsx"); wb.save(path); print("Excel:", path)


def plan_cad(path, cfg, out):
    """Jalur DWG/DXF: konversi bila perlu, ukur dari entitas. Hasil berbentuk sama dengan jalur PDF."""
    import cad
    dxf = path
    if path.lower().endswith(".dwg"):
        try: dxf = cad.convert_dwg(path, out)
        except cad.ConvertError as e: raise SystemExit(f"GAGAL membaca DWG: {e}")
    rec, sup, legend = cad.measure(dxf, cfg)
    res = {"file": os.path.basename(path), "manifest": source_manifest(path, cfg, mode="cad"),
           "sheets": [rec], "tray_total_m": dict(rec["tray_m"]),
           "tray_length_total_m": round(sum(rec["tray_m"].values()), 1), "tray_plan_length_m": round(sum(rec["tray_m"].values()), 1),
           "tray_vertical_upper_length_m": 0.0, "tray_plan_m": dict(rec["tray_m"]),
           "tray_vertical_upper_m": {}, "conduit_h_total_m": rec["conduit_h_m"],
           "conduit_v_upper_m": 0.0 if not rec["conduit_v_m"] else rec["conduit_v_m"], "supports": sup, "source": "cad",
           "checks": crosscheck(dict(rec["tray_m"]), sup, legend, cfg)}
    with open(os.path.join(out, "plan.json"), "w", encoding="utf-8") as fh: json.dump(res, fh, ensure_ascii=False, indent=1)
    return res


def main():
    ap = argparse.ArgumentParser(); sp = ap.add_subparsers(dest="cmd", required=True)
    for n in ("inspect", "plan", "execute"):
        s = sp.add_parser(n); s.add_argument("pdf"); s.add_argument("--out", required=True); s.add_argument("--config")
        s.add_argument("--scale", action="append", default=[]); s.add_argument("--sheets")
        s.add_argument("--batch", action="store_true", help="paksa mode batch (PDF gabungan banyak sheet, checkpoint + resume)")
        s.add_argument("--budget", type=int, default=240, help="detik per jalankan (batch); ulangi perintah sama untuk melanjutkan")
        s.add_argument("--px", type=int, default=4, help="piksel per pt raster (batch)")
        if n == "execute": s.add_argument("--confirm", action="store_true")
    a = ap.parse_args(); cfg = load_config(a.config)
    for sc in a.scale: k, v = sc.split("="); cfg["scales"][k] = int(v)
    os.makedirs(a.out, exist_ok=True)
    if a.pdf.lower().endswith((".dwg", ".dxf")):
        import cad
        if a.cmd == "inspect":
            f = a.pdf
            if f.lower().endswith(".dwg"):
                try: f = cad.convert_dwg(f, a.out)
                except cad.ConvertError as e: raise SystemExit(f"GAGAL membaca DWG: {e}")
            print(json.dumps(cad.scan(f, cfg), ensure_ascii=False, indent=1)); return
        if a.cmd == "plan": print_plan(plan_cad(a.pdf, cfg, a.out)); return
        if a.cmd == "execute":
            if not a.confirm: sys.exit("Ditolak: execute hanya setelah user menyetujui hasil dry-run (tambahkan --confirm).")
            if not os.path.exists(os.path.join(a.out, "plan.json")): sys.exit("plan.json tidak ada: jalankan plan dulu.")
            try: execute(a.out, source_manifest(a.pdf, cfg, mode="cad"))
            except PlanMismatchError as e: raise SystemExit(str(e))
            return
    if a.pdf.lower().endswith(".pdf") and a.cmd in ("plan", "execute"):
        import pymupdf as fitz
        npages = len(fitz.open(a.pdf))
        if a.batch or npages > cfg.get("batch_threshold", 40):
            import batch
            if a.cmd == "plan": batch.run(a.pdf, cfg, a.out, a.budget, a.px); return
            if not a.confirm: sys.exit("Ditolak: execute hanya setelah user menyetujui hasil dry-run (tambahkan --confirm).")
            expected = source_manifest(a.pdf, cfg, mode="pdf-batch", px=a.px, page_count=npages,
                                       tray_width_model="callout-candidate-raster-v1")
            try: batch.write_excel(a.out, expected)
            except PlanMismatchError as e: raise SystemExit(str(e))
            return
    if a.cmd == "inspect":
        inv = inspect(a.pdf, cfg)
        with open(os.path.join(a.out, "inventory.json"), "w", encoding="utf-8") as fh: json.dump(inv, fh, ensure_ascii=False, indent=1)
        for r in inv["sheets"]:
            if r["items"]: print(r["sheet"], r["role"], r["items"], "label", r["label_scales"], "geometri", r["geometry_scale"])
    elif a.cmd == "plan":
        print_plan(plan(a.pdf, cfg, a.out, {int(x) for x in a.sheets.split(",")} if a.sheets else None))
    else:
        if not a.confirm: sys.exit("Ditolak: execute hanya setelah user menyetujui hasil dry-run (tambahkan --confirm).")
        if not os.path.exists(os.path.join(a.out, "plan.json")): sys.exit("plan.json tidak ada: jalankan plan dulu.")
        try: execute(a.out, source_manifest(a.pdf, cfg, mode="pdf", tray_width_model="callout-candidate-raster-v1"))
        except PlanMismatchError as e: raise SystemExit(str(e))

if __name__ == "__main__": main()
