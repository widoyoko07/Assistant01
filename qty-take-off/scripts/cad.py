#!/usr/bin/env python3
"""Jalur CAD untuk qty-take-off: DWG/DXF -> panjang tray/conduit EKSAK dari entitas (tanpa skala, tanpa raster).

  python cad.py convert FILE.dwg --out DIR     # DWG -> DXF (dwg2dxf / ODAFileConverter), verifikasi terbaca
  python cad.py scan    FILE.dxf               # layer, satuan, layout, blok support, kandidat layer tray/conduit
Dipakai oleh takeoff.py (plan/execute) bila input .dwg/.dxf. Hasil lebih akurat dari PDF; PDF = cadangan."""
import collections, json, math, os, re, shutil, subprocess, sys, tempfile

SUPPORT_RE = re.compile(r"^SUH-\d+([A-K])[A-Z]$", re.I)
TRAY_RE = re.compile(r"tray|ladder|cabletray|\bct[-_ ]|trunk", re.I)
CONDUIT_RE = re.compile(r"conduit|cndt|\bcdt\b|g-type|gtype", re.I)
ACI = {"tray": 6, "conduit": 3}          # magenta, hijau (cadangan bila nama layer tidak informatif)


class ConvertError(Exception): pass


# ------------------------------------------------------------ konversi DWG -> DXF
def dwg_version(path):
    with open(path, "rb") as f: tag = f.read(6).decode("ascii", "ignore")
    return {"AC1032": "AutoCAD 2018+", "AC1027": "AutoCAD 2013", "AC1024": "AutoCAD 2010", "AC1021": "AutoCAD 2007",
            "AC1018": "AutoCAD 2004", "AC1015": "AutoCAD 2000"}.get(tag, f"tidak dikenal ({tag})")


def find_converter():
    for name, env in (("dwg2dxf", "DWG2DXF_BIN"), ("ODAFileConverter", "ODA_BIN")):
        p = os.environ.get(env) or shutil.which(name)
        if p and os.path.exists(p): return name, p
    return None, None


def convert_dwg(path, out_dir, timeout=280):
    """Return path DXF. Gagal -> ConvertError dengan instruksi yang bisa langsung disampaikan ke user."""
    os.makedirs(out_dir, exist_ok=True)
    ver = dwg_version(path); size = os.path.getsize(path) / 1e6
    kind, bin_ = find_converter()
    hint = (f"DWG {ver}, {size:.0f} MB tidak dapat dikonversi otomatis di sini. Minta user mengekspor dari AutoCAD: "
            "SAVEAS -> DXF (versi 2013/2018 ASCII), atau PDF vektor (PLOT, bukan scan), lalu unggah ulang.")
    if not kind: raise ConvertError("Tidak ada converter DWG (dwg2dxf/ODAFileConverter). " + hint)
    out = os.path.join(out_dir, os.path.splitext(os.path.basename(path))[0] + ".dxf")
    try:
        if kind == "dwg2dxf":
            r = subprocess.run([bin_, "-y", "-o", out, path], capture_output=True, text=True, timeout=timeout,
                               env={**os.environ, "LD_LIBRARY_PATH": os.path.join(os.path.dirname(os.path.dirname(bin_)), "lib") + ":" + os.environ.get("LD_LIBRARY_PATH", "")})
        else:                              # ODAFileConverter in_dir out_dir ACAD2018 DXF 0 1 filter
            src = tempfile.mkdtemp(); shutil.copy(path, src)
            r = subprocess.run([bin_, src, out_dir, "ACAD2018", "DXF", "0", "1", os.path.basename(path)], capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise ConvertError(f"Konversi melebihi {timeout} detik. " + hint)
    if not os.path.exists(out) or os.path.getsize(out) < 1000:
        tail = (r.stderr or r.stdout or "").strip().splitlines()[-2:]
        raise ConvertError(f"{kind} gagal ({' | '.join(tail)}). " + hint)
    try: load(out)
    except Exception as e: raise ConvertError(f"DXF hasil konversi tidak terbaca ({type(e).__name__}). " + hint)
    return out


# ------------------------------------------------------------ baca DXF
def load(path):
    import ezdxf
    return ezdxf.readfile(path)


def unit_factor_to_m(doc, assume="mm"):
    """Faktor satuan gambar -> meter. INSUNITS=0 (unitless) -> asumsi config + peringatan."""
    from ezdxf import units
    u = doc.units
    if u == 0:
        return units.conversion_factor(getattr(units, assume.upper(), units.MM), units.M), f"INSUNITS tidak diisi; diasumsikan {assume}"
    return units.conversion_factor(u, units.M), None


def _flat_len(e):
    """Panjang entitas melengkung/polyline lewat flattening path (tetap 3D bila ada z)."""
    from ezdxf import path as ep
    pts = list(ep.make_path(e).flattening(0.01))
    return [(pts[i], pts[i + 1]) for i in range(len(pts) - 1)]


def segments(e):
    """Entitas -> daftar segmen lurus ((x,y,z),(x,y,z)). Tipe tak dikenal -> []."""
    t = e.dxftype()
    if t == "LINE": return [(tuple(e.dxf.start), tuple(e.dxf.end))]
    if t in ("LWPOLYLINE", "POLYLINE", "ARC", "SPLINE", "ELLIPSE"):
        try: return [(tuple(a), tuple(b)) for a, b in _flat_len(e)]
        except Exception: return []
    return []


def walk(layout, depth=0, parent_layer=None, max_depth=4):
    """Hasil: (entitas, layer_efektif). INSERT dibongkar rekursif; layer '0' di dalam blok mewarisi layer INSERT."""
    for e in layout:
        t = e.dxftype()
        lay = e.dxf.layer if e.dxf.layer != "0" or parent_layer is None else parent_layer
        if t == "INSERT" and depth < max_depth:
            try:
                for v in e.virtual_entities():
                    yield from walk([v], depth + 1, e.dxf.layer if e.dxf.layer != "0" else parent_layer)
            except Exception: pass
        elif t != "INSERT": yield e, lay


def dist3(a, b): return math.dist(a, b)


def hv(a, b):
    h = math.hypot(b[0] - a[0], b[1] - a[1]); v = abs(b[2] - a[2]); return h, v


# ------------------------------------------------------------ scan
def scan(path, cfg=None):
    doc = load(path); msp = doc.modelspace(); k, uw = unit_factor_to_m(doc, (cfg or {}).get("assume_units", "mm"))
    lay = collections.defaultdict(lambda: collections.Counter()); length = collections.defaultdict(float)
    sup = collections.Counter(); has_z = False
    for e, l in walk(msp):
        lay[l][e.dxftype()] += 1
        for a, b in segments(e):
            length[l] += dist3(a, b) * k
            if abs(a[2]) > 1e-6 or abs(b[2]) > 1e-6: has_z = True
    for e in msp:
        if e.dxftype() == "INSERT" and SUPPORT_RE.match(e.dxf.name): sup[e.dxf.name.upper()] += 1
    layers = []
    for name, cnt in sorted(lay.items()):
        ent = doc.layers.get(name) if name in doc.layers else None
        role = "tray" if TRAY_RE.search(name) else "conduit" if CONDUIT_RE.search(name) else None
        color = ent.color if ent is not None else None
        if role is None and color in (ACI["tray"], ACI["conduit"]): role = {6: "tray", 3: "conduit"}[color] + "?(warna)"
        layers.append({"layer": name, "entities": dict(cnt), "length_m": round(length[name], 1), "aci": color, "role_guess": role})
    layouts = [{"name": ly.name, "viewports": len([v for v in ly if v.dxftype() == "VIEWPORT"])} for ly in doc.layouts if ly.name != "Model"]
    return {"file": os.path.basename(path), "dxfversion": doc.dxfversion, "units": int(doc.units), "units_warning": uw,
            "has_3d": has_z, "layers": layers, "layouts": layouts, "support_blocks": dict(sup), "xrefs": [b.name for b in doc.blocks if b.block.dxf.get("flags", 0) & 4]}


# ------------------------------------------------------------ ukur
def layer_width_mm(name, cfg):
    if name in cfg.get("layer_widths", {}): return cfg["layer_widths"][name]
    m = re.search(r"(?<!\d)(\d{3,4})(?!\d)", name)
    if m and int(m.group(1)) in cfg["tray_widths_mm"]: return int(m.group(1))
    return None


def measure(path, cfg):
    """-> dict hasil seragam dengan jalur PDF (satu 'sheet' bernama 'Model')."""
    doc = load(path); msp = doc.modelspace(); k, uw = unit_factor_to_m(doc, cfg.get("assume_units", "mm"))
    tray_re = re.compile(cfg.get("layers", {}).get("tray", TRAY_RE.pattern), re.I)
    cond_re = re.compile(cfg.get("layers", {}).get("conduit", CONDUIT_RE.pattern), re.I)
    seen = set(); dup = collections.defaultdict(float)
    tray = collections.defaultdict(lambda: {"total": 0.0, "short": 0.0, "long": 0.0, "n": 0}); ch = cv = 0.0; flags = []
    if uw: flags.append(uw)
    maxw = max(cfg["tray_widths_mm"]) * 0.001 / k if k else 0     # lebar tray terbesar dalam satuan gambar -> m
    for e, l in walk(msp):
        role = "tray" if tray_re.search(l) else "conduit" if cond_re.search(l) else None
        if role is None: continue
        for a, b in segments(e):
            key = tuple(sorted((tuple(round(c, 1) for c in a), tuple(round(c, 1) for c in b))))
            L = dist3(a, b) * k
            if key in seen: dup[role] += L; continue                # garis ganda di CAD (bug umum) dibuang
            seen.add(key)
            if role == "conduit":
                h, v = hv(a, b); ch += h * k; cv += v * k
            else:
                w = layer_width_mm(l, cfg); d = tray[w]; d["total"] += L; d["n"] += 1
                d["short" if L <= cfg.get("rung_factor", 1.5) * max(cfg["tray_widths_mm"]) / 1000 else "long"] += L
    out = {}
    for w, d in tray.items():
        ladder = d["total"] > 0 and d["short"] / d["total"] > 0.15 and d["n"] > 20      # banyak segmen pendek = rung
        L = d["long"] / 2 if ladder else d["total"]
        key = str(w) if w else "tanpa-lebar"
        out[key] = round(out.get(key, 0) + L, 1)
        if ladder: flags.append(f"tray lebar {w}: terdeteksi gambar ladder (rel+rung); panjang = rel/2; KONFIRMASI ke user")
        if not w: flags.append("lebar tray tidak terbaca dari nama layer; isi layer_widths di config")
    for r, v in dup.items():
        if v > 0.5: flags.append(f"{r}: {v:.1f} m garis ganda (koordinat sama) dibuang")
    has_z = cv > 0
    if not has_z: flags.append("gambar 2D (tanpa selisih Z): conduit vertikal tidak ada di geometri; hitung dari elevasi/callout")
    sup = collections.Counter(e.dxf.name.upper() for e in msp if e.dxftype() == "INSERT" and SUPPORT_RE.match(e.dxf.name))
    letters = cfg.get("support_letter_width_mm", {})
    supports = {n: {"qty": q, "letter": SUPPORT_RE.match(n).group(1).upper()} for n, q in sup.items()}
    return {"sheet": "Model", "role": "model", "scale": None, "scale_status": "CAD (satuan gambar, tanpa skala)", "tray_m": out,
            "conduit_h_m": round(ch, 1), "conduit_v_m": round(cv, 1), "flags": flags}, supports, {k2.upper(): (v, 0) for k2, v in letters.items()}


if __name__ == "__main__":
    if len(sys.argv) < 3: raise SystemExit(__doc__)
    cmd, f = sys.argv[1], sys.argv[2]
    if cmd == "convert":
        out = sys.argv[sys.argv.index("--out") + 1] if "--out" in sys.argv else "/tmp/tk"
        try: print(convert_dwg(f, out))
        except ConvertError as e: raise SystemExit(f"GAGAL: {e}")
    elif cmd == "scan": print(json.dumps(scan(f), ensure_ascii=False, indent=1))
