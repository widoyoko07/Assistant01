#!/usr/bin/env python3
"""combine-sheets: gabung sheet laporan dari banyak file Excel menjadi satu .xlsx, tanpa membuka Excel.

Dikerjakan di level XML (zip), satu file sumber per giliran, sehingga ringan di memori dan gambar/logo/shape ikut persis.
  scan   --input DIR --keyword jun [--out-json F]        -> DRY-RUN: tabel file/sheet cocok, masalah, nama kembar
  build  --input DIR --keyword jun --out HASIL.xlsx --confirm   -> gabung + Index + verifikasi otomatis
  verify --input DIR --keyword jun --out HASIL.xlsx      -> bandingkan hasil dengan sumber (sel, gaya, merge, gambar)

Aturan (keputusan user):
 - Sheet diambil bila nama sheet memuat kata kunci (huruf besar/kecil diabaikan), diurutkan menurut angka tanggal pada nama.
 - Rumus yang hanya merujuk sel di sheet yang sama dipertahankan. Rumus yang merujuk sheet lain / file lain / nama terdefinisi
   dijadikan nilai (nilai terakhir tersimpan). Hyperlink ke sheet/file lain dihapus (teks tetap).
 - Defined names dibuang (kecuali Print_Area/Print_Titles milik sheet yang diambil). Link eksternal tidak dibawa.
 - Sheet 'Index' di depan, nama sheet kembar diberi pembeda, file bermasalah dilaporkan (tidak dilewati diam-diam)."""
import argparse, collections, copy, glob, hashlib, json, os, posixpath, re, sys, zipfile
from xml.sax.saxutils import escape
from lxml import etree

NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
RNS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PNS = "http://schemas.openxmlformats.org/package/2006/relationships"
T_IMG = RNS + "/image"; T_DRAW = RNS + "/drawing"; T_LINK = RNS + "/hyperlink"
CT_EXT = {"png": "image/png", "jpeg": "image/jpeg", "jpg": "image/jpeg", "gif": "image/gif", "emf": "image/x-emf",
          "wmf": "image/x-wmf", "bmp": "image/bmp", "tif": "image/tiff", "tiff": "image/tiff"}
KEEP_NAMES = ("_xlnm.Print_Area", "_xlnm.Print_Titles")


def q(t): return "{%s}%s" % (NS, t)
def canon(el): return etree.tostring(el, method="c14n", exclusive=True) if el is not None else b""
def xml_bytes(root): return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def col_row(ref):
    m = re.match(r"([A-Z]+)(\d+)$", ref)
    return m.group(1), int(m.group(2))


def quote_sheet(n): return "'" + n.replace("'", "''") + "'" if re.search(r"[^A-Za-z0-9_]", n) or not n else n


SHEETREF = re.compile(r"('(?:[^']|'')+'|[A-Za-z0-9_.\u00c0-\uffff]+)!")


def split_literals(f): return re.sub(r'"(?:[^"]|"")*"', '""', f)


def is_cross(ftext, own, names):
    """True bila rumus merujuk sheet lain, file lain, atau nama terdefinisi."""
    t = split_literals(ftext)
    if "[" in t: return True
    for m in SHEETREF.finditer(t):
        n = m.group(1)
        n = n[1:-1].replace("''", "'") if n.startswith("'") else n
        if n != own: return True
    if names:
        for tok in re.finditer(r"(?<![A-Za-z0-9_.'!$])([A-Za-z_\\][A-Za-z0-9_.]*)(?![A-Za-z0-9_.(!'])", t):
            if tok.group(1).lower() in names: return True
    return False


def rename_refs(text, old, new):
    if old == new: return text
    def sub(m):
        n = m.group(1); nn = n[1:-1].replace("''", "'") if n.startswith("'") else n
        return quote_sheet(new) + "!" if nn == old else m.group(0)
    return SHEETREF.sub(sub, text)


# ------------------------------------------------------------------ styles
class Styles:
    def __init__(self, data):
        self.root = etree.fromstring(data)
        nf = self.root.find(q("numFmts"))
        self.codes = {int(n.get("numFmtId")): n.get("formatCode") for n in (nf if nf is not None else [])}
        self.fonts = self.root.find(q("fonts")); self.fills = self.root.find(q("fills"))
        self.borders = self.root.find(q("borders")); self.xfs = self.root.find(q("cellXfs"))

    def code(self, nid): return self.codes.get(nid, "builtin:%d" % nid) if nid >= 164 or nid in self.codes else "builtin:%d" % nid

    def sig(self, i):
        xf = self.xfs[i]; a = xf.attrib
        return (self.code(int(a.get("numFmtId", 0))), canon(self.fonts[int(a.get("fontId", 0))]),
                canon(self.fills[int(a.get("fillId", 0))]), canon(self.borders[int(a.get("borderId", 0))]),
                canon(xf.find(q("alignment"))), canon(xf.find(q("protection"))), a.get("quotePrefix", "0"))


class Merger:
    """Master styles = styles file pertama; xf dari file lain ditambahkan hanya bila belum ada (dedup per signature)."""
    def __init__(self, data):
        self.m = Styles(data)
        self.font = {canon(e): i for i, e in reversed(list(enumerate(self.m.fonts)))}
        self.fill = {canon(e): i for i, e in reversed(list(enumerate(self.m.fills)))}
        self.border = {canon(e): i for i, e in reversed(list(enumerate(self.m.borders)))}
        self.codeid = {c: i for i, c in self.m.codes.items()}
        self.xf = {}
        for i in range(len(self.m.xfs) - 1, -1, -1): self.xf[self.m.sig(i)] = i
        self.cache = {}

    def _add(self, sec, d, el):
        k = canon(el)
        if k not in d: sec.append(copy.deepcopy(el)); d[k] = len(sec) - 1
        return d[k]

    def _numfmt(self, src, nid):
        if nid < 164 and nid not in src.codes: return nid
        code = src.codes.get(nid)
        if code is None: return nid
        if nid < 164 and self.m.codes.get(nid) == code: return nid
        if code in self.codeid: return self.codeid[code]
        nfs = self.m.root.find(q("numFmts"))
        if nfs is None:
            nfs = etree.Element(q("numFmts")); self.m.root.insert(0, nfs)
        new = max([163] + list(self.m.codes)) + 1
        etree.SubElement(nfs, q("numFmt"), numFmtId=str(new), formatCode=code)
        self.m.codes[new] = code; self.codeid[code] = new
        return new

    def mapping(self, key, data):
        if key in self.cache: return self.cache[key]
        src = Styles(data); out = []
        for i, xf in enumerate(src.xfs):
            s = src.sig(i)
            if s in self.xf: out.append(self.xf[s]); continue
            new = copy.deepcopy(xf); a = new.attrib
            a["numFmtId"] = str(self._numfmt(src, int(a.get("numFmtId", 0))))
            a["fontId"] = str(self._add(self.m.fonts, self.font, src.fonts[int(a.get("fontId", 0))]))
            a["fillId"] = str(self._add(self.m.fills, self.fill, src.fills[int(a.get("fillId", 0))]))
            a["borderId"] = str(self._add(self.m.borders, self.border, src.borders[int(a.get("borderId", 0))]))
            a["xfId"] = "0"
            self.m.xfs.append(new); self.xf[s] = len(self.m.xfs) - 1; out.append(self.xf[s])
        self.cache[key] = out
        return out

    def add_xf(self, font_xml, fill_xml, align=None):
        f = self._add(self.m.fonts, self.font, etree.fromstring(font_xml))
        fi = self._add(self.m.fills, self.fill, etree.fromstring(fill_xml)) if fill_xml else 0
        xf = etree.SubElement(self.m.xfs, q("xf"), numFmtId="0", fontId=str(f), fillId=str(fi), borderId="0", xfId="0",
                              applyFont="1", applyFill="1" if fill_xml else "0")
        if align: etree.SubElement(xf, q("alignment"), **align); xf.set("applyAlignment", "1")
        return len(self.m.xfs) - 1

    def finalize(self):
        for sec in (self.m.fonts, self.m.fills, self.m.borders, self.m.xfs, self.m.root.find(q("numFmts"))):
            if sec is not None: sec.set("count", str(len(sec)))
        return xml_bytes(self.m.root)


# ------------------------------------------------------------------ sumber
def rels_of(z, part):
    rp = posixpath.join(posixpath.dirname(part), "_rels", posixpath.basename(part) + ".rels")
    if rp not in z.namelist(): return {}
    out = {}
    for r in etree.fromstring(z.read(rp)):
        t = r.get("Target"); mode = r.get("TargetMode")
        if mode != "External" and not t.startswith("/"): t = posixpath.normpath(posixpath.join(posixpath.dirname(part), t))
        elif t.startswith("/") and mode != "External": t = t[1:]
        out[r.get("Id")] = (r.get("Type"), t, mode)
    return out


class Src:
    def __init__(self, path):
        self.path = path; self.z = zipfile.ZipFile(path)
        wb = etree.fromstring(self.z.read("xl/workbook.xml")); self.wb = wb
        rel = rels_of(self.z, "xl/workbook.xml"); self.sheets = []
        for i, s in enumerate(wb.find(q("sheets"))):
            rid = s.get("{%s}id" % RNS)
            self.sheets.append({"idx": i, "name": s.get("name"), "state": s.get("state", "visible"), "part": rel[rid][1]})
        dn = wb.find(q("definedNames"))
        self.defined = list(dn) if dn is not None else []
        self.names = {d.get("name").lower() for d in self.defined if not d.get("name").startswith("_xlnm.")
                      and not (d.text or "").strip().startswith("#REF")}
        self.hidden_names = len(self.defined)
        self._sst = None

    def sst(self):
        if self._sst is None:
            self._sst = []
            if "xl/sharedStrings.xml" in self.z.namelist():
                self._sst = list(etree.fromstring(self.z.read("xl/sharedStrings.xml")))
        return self._sst

    def styles_bytes(self): return self.z.read("xl/styles.xml")


def find_sheets(src, keyword):
    k = keyword.lower().strip()
    return [s for s in src.sheets if k in s["name"].lower().strip()]


def date_key(name, keyword):
    m = re.match(r"\s*(\d+)", re.sub(re.escape(keyword.strip()), "", name, flags=re.I))
    return int(m.group(1)) if m else 0


# ------------------------------------------------------------------ proses satu sheet
def process_sheet(src, sh, new_name, xmap, drawing_ctx):
    z = src.z; root = etree.fromstring(z.read(sh["part"])); own = sh["name"]
    rels = rels_of(z, sh["part"]); st = collections.Counter(); notes = []
    sst = src.sst()
    sd = root.find(q("sheetData"))
    # --- kelompok shared formula
    shared = {}
    for c in sd.iter(q("c")):
        f = c.find(q("f"))
        if f is not None and f.get("t") == "shared" and f.text: shared[f.get("si")] = f.text
    cross_si = {si for si, t in shared.items() if is_cross(t, own, src.names)}
    for c in sd.iter(q("c")):
        st["cells"] += 1
        a = c.attrib; s = int(a.get("s", 0))
        if "s" in a: a["s"] = str(xmap[s])
        elif xmap[0] != 0: a["s"] = str(xmap[0])
        f = c.find(q("f")); v = c.find(q("v")); t = a.get("t")
        if f is not None:
            st["formulas"] += 1
            text = f.text or shared.get(f.get("si"), "")
            conv = (f.get("t") == "shared" and f.get("si") in cross_si) or (f.text and is_cross(f.text, own, src.names)) \
                   or (f.get("t") == "shared" and not f.text and f.get("si") not in shared)
            if f.get("t") == "shared" and f.get("si") in cross_si: conv = True
            if conv:
                st["converted"] += 1
                if len(notes) < 3: notes.append(f"{a.get('r')}: ={text[:40]}")
                c.remove(f)
                if t == "str":
                    txt = v.text if v is not None and v.text else ""
                    if v is not None: c.remove(v)
                    a["t"] = "inlineStr"; is_ = etree.SubElement(c, q("is")); tt = etree.SubElement(is_, q("t")); tt.text = txt
                    tt.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
                elif t == "e": st["error_values"] += 1
            else:
                if f.text and own != new_name: f.text = rename_refs(f.text, own, new_name)
                st["kept"] += 1
        if t == "s" and v is not None:
            si = sst[int(v.text)]; c.remove(v); a["t"] = "inlineStr"; is_ = etree.SubElement(c, q("is"))
            for ch in si: is_.append(copy.deepcopy(ch))
    for r in sd.iter(q("row")):
        if "s" in r.attrib: r.set("s", str(xmap[int(r.get("s"))]))
    cols = root.find(q("cols"))
    if cols is not None:
        for c in cols:
            if "style" in c.attrib: c.set("style", str(xmap[int(c.get("style"))]))
    # --- elemen yang tidak dibawa
    dropped = []
    for tag in ("legacyDrawingHF", "controls", "extLst", "conditionalFormatting", "tableParts", "picture", "oleObjects"):
        for el in root.findall(q(tag)):
            dropped.append(tag); root.remove(el)
    vml_part = None
    ld = root.find(q("legacyDrawing"))
    if ld is not None:
        rid = ld.get("{%s}id" % RNS)
        if rid in rels: vml_part = rels[rid][1]; ld.set("{%s}id" % RNS, "rIdVml")
        else: root.remove(ld); dropped.append("legacyDrawing")
    ps = root.find(q("pageSetup"))
    if ps is not None and "{%s}id" % RNS in ps.attrib: del ps.attrib["{%s}id" % RNS]
    hf = root.find(q("headerFooter"))
    for sv in root.iter(q("sheetView")):
        if "tabSelected" in sv.attrib: del sv.attrib["tabSelected"]
    # --- hyperlink
    ext_rels = []
    hl = root.find(q("hyperlinks"))
    if hl is not None:
        for h in list(hl):
            rid = h.get("{%s}id" % RNS); loc = h.get("location")
            if rid and rid in rels and rels[rid][2] == "External":
                ext_rels.append((rid, rels[rid][1])); 
            elif loc and (SHEETREF.match(loc) is None or SHEETREF.match(loc).group(1).strip("'") .replace("''", "'") == own):
                if SHEETREF.match(loc) and own != new_name: h.set("location", rename_refs(loc, own, new_name))
            else:
                hl.remove(h); st["links_removed"] += 1
        if len(hl) == 0: root.remove(hl)
    # --- drawing
    drawing_part = None
    dr = root.find(q("drawing"))
    sheet_rels = []
    if dr is not None:
        rid = dr.get("{%s}id" % RNS); drawing_part = rels[rid][1]
        dr.set("{%s}id" % RNS, "rId1")
    for i, (rid, target) in enumerate(ext_rels, 2):
        for h in root.iter(q("hyperlink")):
            if h.get("{%s}id" % RNS) == rid: h.set("{%s}id" % RNS, f"rId{i}")
        sheet_rels.append((f"rId{i}", T_LINK, target, "External"))
    st["dropped"] = sorted(set(dropped)); st["conv_examples"] = notes
    st["vml_part"] = vml_part
    if vml_part: st["vml_xml"] = z.read(vml_part); st["vml_rels"] = rels_of(z, vml_part)
    # --- gambar/shape
    st["images"] = 0; st["shapes"] = 0
    if drawing_part:
        st["drawing_xml"] = z.read(drawing_part); st["drawing_rels"] = rels_of(z, drawing_part)
        d = st["drawing_xml"].decode("utf8", "ignore")
        st["images"] = d.count("<xdr:pic>") + d.count("<xdr:pic "); st["shapes"] = d.count("<xdr:sp ") + d.count("<xdr:sp>")
        st["charts"] = d.count("graphicFrame") // 2
    st["dim"] = (root.find(q("dimension")).get("ref") if root.find(q("dimension")) is not None else "")
    st["merges"] = len(root.find(q("mergeCells"))) if root.find(q("mergeCells")) is not None else 0
    return xml_bytes(root), st, drawing_part is not None, sheet_rels


# ------------------------------------------------------------------ scan
def list_files(inp):
    fs = [f for f in glob.glob(os.path.join(inp, "**", "*.xlsx"), recursive=True) + glob.glob(os.path.join(inp, "**", "*.xlsm"), recursive=True)
          if not os.path.basename(f).startswith("~$")]
    return sorted(set(fs), key=lambda p: (os.path.basename(p).lower()))


def short_id(path):
    m = re.match(r"\s*(\d+)", os.path.basename(path)); return m.group(1) if m else os.path.splitext(os.path.basename(path))[0][:8]


def scan(inp, keyword):
    files = list_files(inp); entries, problems, nomatch = [], [], []
    for f in files:
        try:
            s = Src(f)
        except zipfile.BadZipFile:
            problems.append({"file": os.path.basename(f), "masalah": "bukan .xlsx valid (rusak atau berpassword)"}); continue
        except Exception as e:
            problems.append({"file": os.path.basename(f), "masalah": f"tidak terbaca ({type(e).__name__}: {e})"}); continue
        m = find_sheets(s, keyword)
        if not m: nomatch.append({"file": os.path.basename(f), "sheets": [x["name"] for x in s.sheets]}); continue
        for sh in m:
            entries.append({"file": f, "fname": os.path.basename(f), "sheet": sh["name"], "state": sh["state"], "order": date_key(sh["name"], keyword)})
    for i, e in enumerate(entries): e["seq"] = i
    entries.sort(key=lambda e: (0 if e["order"] > 0 else 1, e["order"], e["seq"]))
    used = {"index"}
    for e in entries:
        name = e["sheet"].strip() if e["sheet"].strip() else "Sheet"
        base = re.sub(r"[\\/*?:\[\]]", "_", name)[:31]; new = base
        if new.lower() in used:
            suf = f" ({short_id(e['file'])})"; new = base[:31 - len(suf)] + suf; e["renamed"] = True
            k = 2
            while new.lower() in used: suf = f" ({short_id(e['file'])}-{k})"; new = base[:31 - len(suf)] + suf; k += 1
        used.add(new.lower()); e["out_name"] = new
    warn = []
    seen = collections.Counter(e["order"] for e in entries if e["order"] > 0)
    for e in entries:
        if e["order"] == 0: warn.append(f"sheet '{e['sheet']}' ({e['fname']}) tidak punya angka tanggal di nama; ditaruh di urutan akhir")
        if e["state"] != "visible": warn.append(f"sheet '{e['sheet']}' ({e['fname']}) berstatus {e['state']}")
    for n, c in seen.items():
        if c > 1: warn.append(f"angka tanggal {n} muncul {c}x (nama sheet kembar atau file ganda)")
    for e in entries:
        if e.get("renamed"): warn.append(f"nama kembar: '{e['sheet']}' dari {e['fname']} dinamai '{e['out_name']}'")
    return {"keyword": keyword, "files": len(files), "entries": entries, "problems": problems, "nomatch": nomatch, "warnings": warn}


def print_scan_result(res):
    print(f"## DRY-RUN gabung sheet (belum ada file dibuat)\n\nKata kunci: {res['keyword']!r} | file dipindai: {res['files']} | sheet cocok: {len(res['entries'])} | file bermasalah: {len(res['problems'])} | file tanpa sheet cocok: {len(res['nomatch'])}\n")
    print("| No | Sheet hasil | Sheet asal | File sumber |\n|---|---|---|---|")
    for i, e in enumerate(res["entries"], 1): print(f"| {i} | {e['out_name']} | {e['sheet']} | {e['fname']} |")
    for p in res["problems"]: print(f"\n- BERMASALAH {p['file']}: {p['masalah']}")
    for n in res["nomatch"]: print(f"- Tanpa sheet cocok: {n['file']} (sheet: {', '.join(n['sheets'])})")
    if res["warnings"]:
        print("\nPeringatan:"); [print(f" - {w}") for w in res["warnings"]]


# ------------------------------------------------------------------ build
def index_sheet(rows, title, hdr, link, wrapped):
    def c(ref, val, s=None):
        sa = f' s="{s}"' if s is not None else ""
        if isinstance(val, (int, float)): return f'<c r="{ref}"{sa}><v>{val}</v></c>'
        return f'<c r="{ref}"{sa} t="inlineStr"><is><t xml:space="preserve">{escape(str(val))}</t></is></c>'
    head = ["No", "Sheet", "File sumber", "Rentang sel", "Rumus utuh", "Rumus jadi nilai", "Gambar", "Shape", "Catatan"]
    out = [f'<row r="1">{c("A1", title, hdr[1])}</row>', '<row r="3">' + "".join(c(f"{chr(65 + i)}3", h, hdr[0]) for i, h in enumerate(head)) + "</row>"]
    links = []
    for n, r in enumerate(rows, 1):
        rr = n + 3; cells = [c(f"A{rr}", n), c(f"B{rr}", r["out"], link), c(f"C{rr}", r["file"]), c(f"D{rr}", r["dim"]),
                             c(f"E{rr}", r["kept"]), c(f"F{rr}", r["converted"]), c(f"G{rr}", r["images"]), c(f"H{rr}", r["shapes"]), c(f"I{rr}", r["note"], wrapped)]
        out.append(f'<row r="{rr}">' + "".join(cells) + "</row>")
        links.append(f'<hyperlink ref="B{rr}" location="{escape(quote_sheet(r["out"]))}!A1" display="{escape(r["out"])}"/>')
    widths = [5, 18, 70, 14, 12, 16, 9, 9, 70]
    cols = "".join(f'<col min="{i + 1}" max="{i + 1}" width="{w}" customWidth="1"/>' for i, w in enumerate(widths))
    return (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<worksheet xmlns="{NS}"><sheetPr><pageSetUpPr fitToPage="1"/></sheetPr><sheetViews><sheetView tabSelected="1" workbookViewId="0">'
            f'<pane ySplit="3" topLeftCell="A4" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews><sheetFormatPr defaultRowHeight="15"/>'
            f'<cols>{cols}</cols><sheetData>{"".join(out)}</sheetData><hyperlinks>{"".join(links)}</hyperlinks>'
            f'<pageMargins left="0.7" right="0.7" top="0.75" bottom="0.75" header="0.3" footer="0.3"/><pageSetup orientation="landscape" fitToHeight="0"/></worksheet>').encode("utf-8")


def build(inp, keyword, out_path):
    plan = scan(inp, keyword)
    if not plan["entries"]: sys.exit("Tidak ada sheet yang cocok; tidak ada file dibuat.")
    if os.path.exists(out_path): sys.exit(f"Menolak menimpa file yang sudah ada: {out_path}. Pakai nama keluaran baru.")
    entries = plan["entries"]; os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    tmp = out_path + ".part"; srcs = {}
    first = Src(entries[0]["file"]); merger = Merger(first.styles_bytes()); theme = first.z.read("xl/theme/theme1.xml")
    zo = zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED)
    media = {}; ctypes = set(); sheets_meta = []; drawing_n = 0; vml_total = 0; names_out = []; report = []
    for n, e in enumerate(entries, 2):                              # sheet1 = Index
        key = e["file"]
        if key not in srcs:
            srcs.clear(); srcs[key] = Src(key)                      # hanya satu file sumber terbuka pada satu waktu
        s = srcs[key]; sh = next(x for x in s.sheets if x["name"] == e["sheet"])
        xmap = merger.mapping(key, s.styles_bytes())
        data, st, has_dr, sheet_rels = process_sheet(s, sh, e["out_name"], xmap, None)
        rel_xml = []; idmap = {}
        def add_media(src_z, tgt):
            b = src_z.read(tgt); h = hashlib.sha1(b).hexdigest(); ext = tgt.rsplit(".", 1)[-1].lower()
            if h not in media:
                media[h] = f"image{len(media) + 1}.{ext}"; zo.writestr(f"xl/media/{media[h]}", b); ctypes.add(ext)
            return f"../media/{media[h]}"
        def rels_xml(items):
            return (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<Relationships xmlns="{PNS}">' +
                    "".join(f'<Relationship Id="{r}" Type="{t}" Target="{g}"/>' for r, t, g in items) + "</Relationships>")
        if st.get("vml_part"):                                  # VML lama (mis. gambar kamera Excel) wajib ikut, id shape dibuat unik per sheet
            vml = st.pop("vml_xml").decode("utf8", "ignore"); vrels = st.pop("vml_rels")
            m = re.search(r'<o:idmap[^>]*data="(\d+)"', vml); d_old = int(m.group(1)) if m else 1; d_new = 100 + n
            for sid in set(re.findall(r"_x0000_s(\d+)", vml)): idmap[sid] = str(int(sid) - d_old * 1024 + d_new * 1024)
            vml = re.sub(r'(<o:idmap[^>]*data=")\d+(")', lambda mm: mm.group(1) + str(d_new) + mm.group(2), vml)
            vml = re.sub(r"_x0000_s(\d+)", lambda mm: "_x0000_s" + idmap[mm.group(1)], vml)
            zo.writestr(f"xl/drawings/vmlDrawing{n}.vml", vml.encode("utf8"))
            vr = [(r, T_IMG, add_media(s.z, tgt)) for r, (typ, tgt, mode) in vrels.items() if typ == T_IMG and mode != "External"]
            if vr: zo.writestr(f"xl/drawings/_rels/vmlDrawing{n}.vml.rels", rels_xml(vr))
            rel_xml.append(f'<Relationship Id="rIdVml" Type="{RNS}/vmlDrawing" Target="../drawings/vmlDrawing{n}.vml"/>'); vml_total += 1
        else: st.pop("vml_xml", None); st.pop("vml_rels", None)
        if has_dr:
            drawing_n += 1; d = st.pop("drawing_xml").decode("utf8"); drels = st.pop("drawing_rels"); newrel = []
            for sid, new_id in idmap.items(): d = d.replace(f"_x0000_s{sid}", f"_x0000_s{new_id}")
            for rid, (typ, tgt, mode) in drels.items():
                if typ == T_IMG and mode != "External": newrel.append((rid, T_IMG, add_media(s.z, tgt)))
                else: st.setdefault("dropped", []).append(f"relasi drawing {typ.rsplit('/', 1)[-1]}")
            zo.writestr(f"xl/drawings/drawing{drawing_n}.xml", d.encode("utf8"))
            zo.writestr(f"xl/drawings/_rels/drawing{drawing_n}.xml.rels", rels_xml(newrel))
            rel_xml.append(f'<Relationship Id="rId1" Type="{T_DRAW}" Target="../drawings/drawing{drawing_n}.xml"/>')
        else: st.pop("drawing_xml", None); st.pop("drawing_rels", None)
        for rid, typ, tgt, mode in sheet_rels: rel_xml.append(f'<Relationship Id="{rid}" Type="{typ}" Target="{escape(tgt)}" TargetMode="{mode}"/>')
        zo.writestr(f"xl/worksheets/sheet{n}.xml", data)
        if rel_xml: zo.writestr(f"xl/worksheets/_rels/sheet{n}.xml.rels", f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<Relationships xmlns="{PNS}">' + "".join(rel_xml) + "</Relationships>")
        for dn in s.defined:
            if dn.get("name") in KEEP_NAMES and dn.get("localSheetId") == str(sh["idx"]):
                names_out.append((dn.get("name"), n - 1, rename_refs(dn.text or "", e["sheet"], e["out_name"])))
        note = []
        if st["converted"]: note.append(f"{st['converted']} rumus ke luar sheet dijadikan nilai ({'; '.join(st['conv_examples'])})")
        if st.get("links_removed"): note.append(f"{st['links_removed']} hyperlink ke luar sheet dihapus")
        if st.get("dropped"): note.append("tidak dibawa: " + ", ".join(st["dropped"]))
        if st.get("charts"): note.append(f"{st['charts']} chart TIDAK dibawa")
        if st.get("error_values"): note.append(f"{st['error_values']} nilai error di sumber")
        if e.get("renamed"): note.append(f"nama kembar, asal '{e['sheet']}'")
        report.append({"file": e["fname"], "src_sheet": e["sheet"], "out": e["out_name"], "dim": st["dim"], "kept": st["kept"], "converted": st["converted"],
                       "images": st["images"], "shapes": st["shapes"], "note": "; ".join(note), "cells": st["cells"], "merges": st["merges"],
                       "dropped": st.get("dropped", []), "links_removed": st.get("links_removed", 0), "n": n})
        sheets_meta.append((n, e["out_name"]))
    hdr_font = '<font xmlns="%s"><b/><sz val="11"/><color rgb="FFFFFFFF"/><name val="Arial"/><family val="2"/></font>' % NS
    hdr_fill = '<fill xmlns="%s"><patternFill patternType="solid"><fgColor rgb="FF305496"/><bgColor indexed="64"/></patternFill></fill>' % NS
    ttl_font = '<font xmlns="%s"><b/><sz val="13"/><name val="Arial"/><family val="2"/></font>' % NS
    lnk_font = '<font xmlns="%s"><u/><sz val="11"/><color rgb="FF0563C1"/><name val="Arial"/><family val="2"/></font>' % NS
    txt_font = '<font xmlns="%s"><sz val="10"/><name val="Arial"/><family val="2"/></font>' % NS
    hdr = (merger.add_xf(hdr_font, hdr_fill, {"horizontal": "center", "vertical": "center"}), merger.add_xf(ttl_font, None))
    link = merger.add_xf(lnk_font, None); wrapped = merger.add_xf(txt_font, None, {"wrapText": "1", "vertical": "top"})
    title = f"Index - gabungan {len(entries)} sheet dari {len({e['file'] for e in entries})} file (kata kunci: {keyword})"
    zo.writestr("xl/worksheets/sheet1.xml", index_sheet(report, title, hdr, link, wrapped))
    zo.writestr("xl/styles.xml", merger.finalize()); zo.writestr("xl/theme/theme1.xml", theme)
    all_sheets = [(1, "Index")] + sheets_meta
    wbx = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<workbook xmlns="{NS}" xmlns:r="{RNS}"><workbookPr defaultThemeVersion="166925"/>'
           f'<bookViews><workbookView activeTab="0"/></bookViews><sheets>' + "".join(f'<sheet name="{escape(nm, {chr(34): "&quot;"})}" sheetId="{i}" r:id="rId{i}"/>' for i, nm in all_sheets) + "</sheets>")
    if names_out:
        wbx += "<definedNames>" + "".join(f'<definedName name="{n}" localSheetId="{i}">{escape(t)}</definedName>' for n, i, t in names_out) + "</definedNames>"
    wbx += '<calcPr calcId="191028" fullCalcOnLoad="1"/></workbook>'
    zo.writestr("xl/workbook.xml", wbx)
    nS = len(all_sheets)
    zo.writestr("xl/_rels/workbook.xml.rels", f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<Relationships xmlns="{PNS}">' +
                "".join(f'<Relationship Id="rId{i}" Type="{RNS}/worksheet" Target="worksheets/sheet{i}.xml"/>' for i, _ in all_sheets) +
                f'<Relationship Id="rId{nS + 1}" Type="{RNS}/styles" Target="styles.xml"/><Relationship Id="rId{nS + 2}" Type="{RNS}/theme" Target="theme/theme1.xml"/></Relationships>')
    zo.writestr("_rels/.rels", f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<Relationships xmlns="{PNS}"><Relationship Id="rId1" Type="{RNS}/officeDocument" Target="xl/workbook.xml"/></Relationships>')
    ct = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
          '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/>' +
          "".join(f'<Default Extension="{x}" ContentType="{CT_EXT.get(x, "application/octet-stream")}"/>' for x in sorted(ctypes)) +
          ('<Default Extension="vml" ContentType="application/vnd.openxmlformats-officedocument.vmlDrawing"/>' if vml_total else "") +
          '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>' +
          "".join(f'<Override PartName="/xl/worksheets/sheet{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>' for i, _ in all_sheets) +
          "".join(f'<Override PartName="/xl/drawings/drawing{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.drawing+xml"/>' for i in range(1, drawing_n + 1)) +
          '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
          '<Override PartName="/xl/theme/theme1.xml" ContentType="application/vnd.openxmlformats-officedocument.theme+xml"/></Types>')
    zo.writestr("[Content_Types].xml", ct); zo.close(); os.replace(tmp, out_path)
    res = {"keyword": keyword, "out": os.path.basename(out_path), "plan": {k: v for k, v in plan.items() if k != "entries"},
           "entries": [{k: e[k] for k in ("fname", "sheet", "out_name", "order")} for e in entries], "report": report,
           "dropped_defined_names": sum(len(Src(f).defined) for f in {e["file"] for e in entries[:1]})}
    with open(out_path + ".report.json", "w", encoding="utf-8") as fh: json.dump(res, fh, ensure_ascii=False, indent=1)
    return plan, report


# ------------------------------------------------------------------ verify
def sheet_cells(root, sst, styles):
    out = {}
    for c in root.iter(q("c")):
        t = c.get("t", "n"); v = c.find(q("v")); f = c.find(q("f")); i = c.find(q("is"))
        if t == "s": val = ("s", "".join(sst[int(v.text)].itertext()))
        elif t == "inlineStr": val = ("s", "".join(i.itertext()) if i is not None else "")
        elif t == "str": val = ("s", (v.text or "") if v is not None else "")
        elif v is None: val = None
        else: val = (t, v.text)
        out[c.get("r")] = (val, styles.sig(int(c.get("s", 0))), f is not None)
    return out


def sheet_attrs(root):
    cols = [tuple(sorted((k, v) for k, v in c.attrib.items() if k != "style")) for c in (root.find(q("cols")) if root.find(q("cols")) is not None else [])]
    rows = [(r.get("r"), r.get("ht"), r.get("hidden"), r.get("customHeight")) for r in root.find(q("sheetData")).iter(q("row"))]
    mc = sorted(m.get("ref") for m in (root.find(q("mergeCells")) if root.find(q("mergeCells")) is not None else []))
    ps = root.find(q("pageSetup")); ps = tuple(sorted((k, v) for k, v in ps.attrib.items() if "}" not in k)) if ps is not None else ()
    return {"cols": cols, "rows": rows, "merges": mc, "pageSetup": ps}


def drawing_sig(z, part_sheet):
    rel = rels_of(z, part_sheet)
    for rid, (typ, tgt, mode) in rel.items():
        if typ == T_DRAW:
            d = z.read(tgt)
            imgs = sorted(hashlib.sha1(z.read(t)).hexdigest() for _, (ty, t, m) in rels_of(z, tgt).items() if ty == T_IMG)
            anchors = len(re.findall(rb"<xdr:(?:twoCellAnchor|oneCellAnchor|absoluteAnchor)", d))
            # urutan/posisi anchor dibandingkan tanpa atribut rId
            pos = sorted(re.findall(rb"<xdr:from>.*?</xdr:from>", d, re.S))
            vml = [hashlib.sha1(z.read(t)).hexdigest() for _, (ty, t, m) in rel.items() if ty.endswith("/vmlDrawing")]
            vimg = sorted(hashlib.sha1(z.read(t)).hexdigest() for _, (ty, t, m) in rels_of(z, next(t for _, (ty, t, m) in rel.items() if ty.endswith("/vmlDrawing"))).items() if ty == T_IMG) if vml else []
            return {"anchors": anchors, "images": imgs, "pos": pos, "vml_images": vimg, "vml": len(vml)}
    return {"anchors": 0, "images": [], "pos": [], "vml_images": [], "vml": 0}


def verify(inp, out_path):
    rep = json.load(open(out_path + ".report.json", encoding="utf-8")); errs = []; ok = 0
    zo = zipfile.ZipFile(out_path); bad = zo.testzip()
    if bad: errs.append(f"zip rusak: {bad}")
    out_styles = Styles(zo.read("xl/styles.xml")); wb = etree.fromstring(zo.read("xl/workbook.xml")); rel = rels_of(zo, "xl/workbook.xml")
    parts = {s.get("name"): rel[s.get("{%s}id" % RNS)][1] for s in wb.find(q("sheets"))}
    files = {os.path.basename(f): f for f in list_files(inp)}
    if len(parts) != len(rep["report"]) + 1: errs.append(f"jumlah sheet hasil {len(parts)} != {len(rep['report'])} + Index")
    if any(d.get("name") not in KEEP_NAMES for d in (wb.find(q("definedNames")) if wb.find(q("definedNames")) is not None else [])): errs.append("ada defined name selain Print_Area/Print_Titles")
    if any("externalLink" in n for n in zo.namelist()): errs.append("masih ada externalLink")
    srcs = {}; conv_total = 0; lines = []
    for r in rep["report"]:
        f = files.get(r["file"]); s = srcs.get(f) or Src(f); srcs.clear(); srcs[f] = s
        sh = next(x for x in s.sheets if x["name"] == r["src_sheet"])
        sroot = etree.fromstring(s.z.read(sh["part"])); oroot = etree.fromstring(zo.read(parts[r["out"]]))
        a = sheet_cells(sroot, s.sst(), Styles(s.styles_bytes())); b = sheet_cells(oroot, [], out_styles)
        local = []
        if set(a) != set(b): local.append(f"daftar sel beda ({len(set(a) ^ set(b))} sel)")
        conv = 0
        for k in a.keys() & b.keys():
            if a[k][0] != b[k][0]: local.append(f"nilai beda di {k}: {a[k][0]} vs {b[k][0]}") if len(local) < 5 else None
            if a[k][1] != b[k][1]: local.append(f"gaya beda di {k}") if len(local) < 5 else None
            if a[k][2] and not b[k][2]: conv += 1
            if not a[k][2] and b[k][2]: local.append(f"rumus muncul di {k}") if len(local) < 5 else None
        if conv != r["converted"]: local.append(f"rumus dijadikan nilai {conv} != laporan {r['converted']}")
        conv_total += conv
        if sheet_attrs(sroot) != sheet_attrs(oroot): local.append("lebar kolom/tinggi baris/merge/page setup beda")
        da, db = drawing_sig(s.z, sh["part"]), drawing_sig(zo, parts[r["out"]])
        if da != db: local.append(f"gambar/shape beda: sumber {da['anchors']} objek/{len(da['images'])} gambar vs hasil {db['anchors']}/{len(db['images'])}")
        if not local: ok += 1
        else: errs += [f"{r['out']}: {x}" for x in local]
    lines.append(f"Sheet diperiksa: {len(rep['report'])} | lolos penuh: {ok} | rumus dijadikan nilai: {conv_total}")
    return errs, lines


def print_report(plan, report, errs, lines, out_path):
    print(f"## Hasil gabung\n\nFile: {out_path} ({os.path.getsize(out_path) / 1e6:.2f} MB) | sheet: {len(report)} + Index\n")
    print("| No | Sheet | File sumber | Rumus utuh | Rumus jadi nilai | Gambar | Shape |\n|---|---|---|---|---|---|---|")
    for i, r in enumerate(report, 1): print(f"| {i} | {r['out']} | {r['file'][:42]} | {r['kept']} | {r['converted']} | {r['images']} | {r['shapes']} |")
    notes = [f"{r['out']}: {r['note']}" for r in report if r["note"]]
    if plan["problems"] or plan["nomatch"] or plan["warnings"] or notes: print("\nCatatan:")
    for p in plan["problems"]: print(f" - BERMASALAH {p['file']}: {p['masalah']}")
    for n in plan["nomatch"]: print(f" - tanpa sheet cocok: {n['file']}")
    for w in plan["warnings"]: print(f" - {w}")
    for n in notes[:40]: print(f" - {n}")
    print("\n## Verifikasi otomatis"); [print(l) for l in lines]
    print("Status: " + ("LULUS" if not errs else "GAGAL")); [print(" - " + e) for e in errs[:30]]


def main():
    ap = argparse.ArgumentParser(); sp = ap.add_subparsers(dest="cmd", required=True)
    for n in ("scan", "build", "verify"):
        s = sp.add_parser(n); s.add_argument("--input", required=True); s.add_argument("--keyword", required=True)
        if n != "scan": s.add_argument("--out", required=True)
        if n == "build": s.add_argument("--confirm", action="store_true")
    a = ap.parse_args()
    if a.cmd == "scan": print_scan_result(scan(a.input, a.keyword)); return
    if a.cmd == "build":
        if not a.confirm: sys.exit("Ditolak: build hanya setelah user menyetujui hasil scan (tambahkan --confirm).")
        plan, report = build(a.input, a.keyword, a.out); errs, lines = verify(a.input, a.out); print_report(plan, report, errs, lines, a.out)
        sys.exit(1 if errs else 0)
    errs, lines = verify(a.input, a.out); [print(l) for l in lines]; print("Status: " + ("LULUS" if not errs else "GAGAL")); [print(" - " + e) for e in errs]
    sys.exit(1 if errs else 0)


if __name__ == "__main__": main()
