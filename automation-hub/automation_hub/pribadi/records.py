"""K2c: baca (Description, Subcategory, Account) dari tabel _transaction di salinan lokal xlsx (hanya baca)."""
import re
import zipfile
from xml.etree import ElementTree as ET

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"


def _shared(z):
    root = ET.fromstring(z.read("xl/sharedStrings.xml"))
    return ["".join(t.text or "" for t in si.iter(f"{{{NS['m']}}}t")) for si in root.findall("m:si", NS)]


def _sheet_path(z, name):
    wb = ET.fromstring(z.read("xl/workbook.xml"))
    rid = next(s.get(R) for s in wb.find("m:sheets", NS) if s.get("name") == name)
    rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
    tgt = next(r.get("Target") for r in rels if r.get("Id") == rid)
    return "xl/" + tgt.lstrip("/").removeprefix("xl/")


def read_records(xlsx, sheet="04.record", header_row=11):
    """List dict {account, description, subcategory} dari baris data di bawah header."""
    z = zipfile.ZipFile(xlsx)
    ss = _shared(z)
    out = []
    for row in ET.fromstring(z.read(_sheet_path(z, sheet))).iter(f"{{{NS['m']}}}row"):
        if int(row.get("r")) <= header_row:
            continue
        cells = {}
        for c in row.findall("m:c", NS):
            col = re.match(r"[A-Z]+", c.get("r")).group()
            v = c.find("m:v", NS)
            if v is not None:
                cells[col] = ss[int(v.text)] if c.get("t") == "s" else v.text
        if cells.get("E") and cells.get("I"):
            out.append({"account": cells.get("D"), "description": cells["E"], "subcategory": cells["I"]})
    return out
