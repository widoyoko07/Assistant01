"""M5: DPR harian format final untuk satu tanggal, dibuat dari salinan DPR final hari sebelumnya (file asli tidak diubah).

Yang dikerjakan (edit XML, bukan openpyxl load+save, supaya logo, gambar, sheet Photo dan format tetap utuh):
  1. blok SUB ME (baris 146-185) disusun ulang dari sheet ME (manpower) dan WD Kandidat ('x' + Butir Final);
  2. isian SUB CIVIL dikosongkan: kolom file Civil berbeda dari DPR final (tanpa kolom Skilled Workers dan Total
     Manpower, equipment lain), jadi isinya belum bisa dipindah otomatis;
  3. tanggal sampul ('DPR '!AA15), nama sheet harian, dan teks hasil rumus di-set ke tanggal baru; Excel menghitung ulang saat dibuka.
Hasilnya untuk di-review, bukan file terbit.
"""
import copy
import re
import zipfile
from datetime import date
from pathlib import Path

from lxml import etree

from ..common import config as cfgmod
from . import dpr_me_block as B
from .xlsx_sheet import _col, _col_num, _sheet_part

NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
Q = lambda t: f"{{{NS}}}{t}"
ME_FIRST, ME_LAST = 146, 185
ME_SAFE_LAST = 182            # subtotal baris 145 hanya menjumlah sampai 182
MERGE_COLS = ["C", "G", "H", "I"] + [_col(c) for c in range(10, 50)]     # C, G, H, I, J..AW
_DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def _split(ref):
    m = re.match(r"([A-Z]+)(\d+)$", ref)
    return m.group(1), int(m.group(2))


def _blank(row):
    for c in row.findall(Q("c")):
        for t in ("v", "f", "is"):
            for e in c.findall(Q(t)):
                c.remove(e)
        c.attrib.pop("t", None)


def _put(row, col, value, formula=None):
    ref = f"{col}{row.get('r')}"
    c = next((x for x in row.findall(Q("c")) if x.get("r") == ref), None)
    if c is None:
        c = etree.Element(Q("c"), r=ref)
        after = [x for x in row.findall(Q("c")) if _col_num(_split(x.get("r"))[0]) < _col_num(col)]
        (after[-1].addnext(c) if after else row.insert(0, c))
    for t in ("v", "f", "is"):
        for e in c.findall(Q(t)):
            c.remove(e)
    c.attrib.pop("t", None)
    if formula:
        etree.SubElement(c, Q("f")).text = formula
    if value is None or value == "":
        return
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        etree.SubElement(c, Q("v")).text = str(value)
    else:
        c.set("t", "inlineStr")
        etree.SubElement(etree.SubElement(c, Q("is")), Q("t")).text = str(value)


def layout(blocks):
    """blocks: [{'name','cat','items','start','finish','jam','mp','equip'}] -> baris awal tiap blok. Satu baris kosong antar blok."""
    r, out = ME_FIRST, []
    for b in blocks:
        h = max(len(b["items"]), 1)
        out.append((r, h))
        r += h + 1
    if r - 1 > ME_SAFE_LAST:
        raise ValueError(f"blok SUB ME butuh baris {ME_FIRST}-{r - 1}, melebihi batas {ME_SAFE_LAST} di template")
    return out


def me_blocks(me_xlsx, wd_xlsx, day, template_xlsx, template_sheet, cfg):
    roles, info = B.template_info(template_xlsx, template_sheet, cfg)
    import openpyxl
    me = openpyxl.load_workbook(me_xlsx)["ME"]
    wd = B.items_by_sc(wd_xlsx, day)
    blocks, notes = [], []
    for name in B.ORDER:
        mp = B.manpower(me, cfg, day, name, roles, cfg.get("dpr_role_map", {}))
        sc = next(k for k, v in B.WD_SC.items() if name in v)
        items, start, finish, jam = wd.get(sc, ([], None, None, None)) if (sc != "TODJO" or name == "DJK DCIP") else ([], None, None, None)
        if not mp and not items:
            continue
        dn = B.DPR_NAME[name]
        cat, equip = (info.get(dn) or [None, {}])
        if not items:
            notes.append(f"{dn}: ada manpower ({sum(mp.values())}) tetapi belum ada butir ber-x")
        if sc == "TODJO" and name == "DJK DCIP" and items:
            notes.append("TODJO: butir ditaruh di blok DJK; pembagian Tohoma/DJK manual")
        blocks.append({"name": dn, "cat": cat, "items": items, "start": start or "08.00", "finish": finish or "17.00",
                       "jam": jam or 8, "mp": mp, "equip": equip or {"AK": 1, "AL": 1, "AN": 1}, "roles": roles})
    return blocks, notes


def fill_me(root, blocks):
    ns = {"m": NS}
    data = root.find(Q("sheetData"))
    rows = {int(r.get("r")): r for r in data.findall(Q("row"))}
    tpl_first, tpl_cont, tpl_blank = rows[146], rows[147], rows[149]
    pos = layout(blocks)
    new = {}
    for r in range(ME_FIRST, ME_LAST + 1):
        row = copy.deepcopy(tpl_blank)
        row.set("r", str(r))
        for c in row.findall(Q("c")):
            c.set("r", f"{_split(c.get('r'))[0]}{r}")
        _blank(row)
        new[r] = row
    merges = []
    for b, (r0, h) in zip(blocks, pos):
        for i in range(h):
            r = r0 + i
            row = copy.deepcopy(tpl_first if i == 0 else tpl_cont)
            row.set("r", str(r))
            for c in row.findall(Q("c")):
                c.set("r", f"{_split(c.get('r'))[0]}{r}")
            _blank(row)
            if i == 0:
                _put(row, "B", b["name"])
                _put(row, "C", b["cat"])
                _put(row, "G", b["start"])
                _put(row, "H", b["finish"])
                _put(row, "I", b["jam"])
                for col_i, role in enumerate(b["roles"]):
                    if b["mp"].get(role):
                        _put(row, _col(10 + col_i), b["mp"][role])
                _put(row, "AJ", None, formula=f"SUM(J{r}:AI{r})")
                for col, v in b["equip"].items():
                    _put(row, col, v)
                _put(row, "AX", sum(b["mp"].values()))
                _put(row, "BN", b["name"].lower())
                _put(row, "BP", None, formula=f"SUM(N{r},R{r},U{r},AH{r})")
            if i < len(b["items"]):
                _put(row, "D", b["items"][i])
            new[r] = row
        if h > 1:
            merges += [f"{c}{r0}:{c}{r0 + h - 1}" for c in MERGE_COLS]
    for r in range(ME_FIRST, ME_LAST + 1):
        old = rows.get(r)
        if old is not None:
            old.addprevious(new[r])
            data.remove(old)
        else:
            data.append(new[r])
    mc = root.find(Q("mergeCells"))
    for m in list(mc):
        a, b2 = m.get("ref").split(":")
        r1, r2 = _split(a)[1], _split(b2)[1]
        if r1 <= ME_LAST and r2 >= ME_FIRST:
            mc.remove(m)
    for ref in merges:
        etree.SubElement(mc, Q("mergeCell"), ref=ref)
    mc.set("count", str(len(mc)))
    return pos


def clear_civil(root):
    """Kosongkan isian SUB CIVIL (baris 32-144): nilai konstanta dihapus, rumus dan format tetap."""
    n = 0
    for row in root.find(Q("sheetData")).findall(Q("row")):
        if 32 <= int(row.get("r")) <= 144:
            for c in row.findall(Q("c")):
                if c.find(Q("f")) is None and (c.find(Q("v")) is not None or c.find(Q("is")) is not None):
                    col = _split(c.get("r"))[0]
                    if _col_num(col) <= _col_num("AX"):
                        for t in ("v", "is"):
                            for e in c.findall(Q(t)):
                                c.remove(e)
                        c.attrib.pop("t", None)
                        n += 1
    return n


def build(template_xlsx, src_sheet, me_xlsx, wd_xlsx, day, out_path, cfg=None):
    cfg = cfg or cfgmod.load()
    new_sheet = f"{day.day} {day.strftime('%b')}"
    serial = (day - date(1899, 12, 30)).days
    old_day = None
    blocks, notes = me_blocks(me_xlsx, wd_xlsx, day, template_xlsx, src_sheet, cfg)
    with zipfile.ZipFile(template_xlsx) as zin:
        part = _sheet_part(zin, src_sheet)
        cover = _sheet_part(zin, "DPR ")
        root = etree.fromstring(zin.read(part))
        cleared = clear_civil(root)
        pos = fill_me(root, blocks)
        a11 = next((c for c in root.iter(Q("c")) if c.get("r") == "A11"), None)
        if a11 is not None and a11.find(Q("v")) is not None:
            old_serial = int(float(a11.find(Q("v")).text))
            old_day = date(1899, 12, 30).toordinal() + old_serial
            a11.find(Q("v")).text = str(serial)
        sheet_xml = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
        old = date.fromordinal(old_day) if old_day else None

        def retext(text):
            if old:
                text = text.replace(f"{_DAYS[old.weekday()]}, {old.day:02d} {old.strftime('%B %Y')}", f"{_DAYS[day.weekday()]}, {day.day:02d} {day.strftime('%B %Y')}")
                text = text.replace(f"{old.day:02d} {old.strftime('%B %Y')}", f"{day.day:02d} {day.strftime('%B %Y')}")
            return text

        out = {}
        for info in zin.infolist():
            data = zin.read(info.filename)
            n = info.filename
            if n == "xl/calcChain.xml":
                continue
            if n == part:
                data = sheet_xml
            elif n == cover:
                t = data.decode("utf-8")
                t = re.sub(r'(<c r="AA15"[^>]*>)<v>\d+</v>', rf"\g<1><v>{serial}</v>", t)
                data = retext(t).encode("utf-8")
            elif n.startswith("xl/worksheets/") and n.endswith(".xml"):
                data = retext(data.decode("utf-8")).encode("utf-8")
            elif n == "xl/workbook.xml":
                t = data.decode("utf-8").replace(f"'{src_sheet}'", f"'{new_sheet}'").replace(f'name="{src_sheet}"', f'name="{new_sheet}"')
                t = re.sub(r"<calcPr ([^>]*?)/>", r'<calcPr \1 fullCalcOnLoad="1"/>', t)
                data = t.encode("utf-8")
            elif n == "docProps/app.xml":
                data = data.decode("utf-8").replace(src_sheet, new_sheet).encode("utf-8")
            elif n == "xl/_rels/workbook.xml.rels":
                data = re.sub(r'<Relationship [^>]*calcChain[^>]*/>', "", data.decode("utf-8")).encode("utf-8")
            elif n == "[Content_Types].xml":
                data = re.sub(r'<Override [^>]*calcChain[^>]*/>', "", data.decode("utf-8")).encode("utf-8")
            out[n] = (info, data)
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zout:
        for n, (info, data) in out.items():
            zout.writestr(info, data)
    return {"sheet": new_sheet, "blocks": [(b["name"], r0, h) for b, (r0, h) in zip(blocks, pos)], "civil_cleared": cleared, "notes": notes}
