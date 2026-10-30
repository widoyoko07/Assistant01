"""Tambah satu sheet ke xlsx yang sudah ada lewat edit XML (zip), tanpa memuat ulang workbook.

openpyxl load+save membuang bagian yang tidak dikenalnya (gambar, shape, format kustom) dan sangat lambat pada
file besar. Di sini hanya empat bagian zip yang disentuh; semua bagian lain disalin byte-per-byte.
"""
import re
import zipfile
from xml.sax.saxutils import escape

_NS_R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_REL_TYPE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet"
_CT_SHEET = "application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"
_ILLEGAL = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f]")


def _col(n):
    s = ""
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def sheet_xml(rows, widths=()):
    """rows: list of list (str/int/None). Baris pertama = judul kolom, dibekukan dan diberi filter."""
    out = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
           '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">']
    ncol = max((len(r) for r in rows), default=1)
    out.append('<sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/>'
               '</sheetView></sheetViews>')
    if widths:
        out.append("<cols>" + "".join(f'<col min="{i}" max="{i}" width="{w}" customWidth="1"/>' for i, w in enumerate(widths, 1)) + "</cols>")
    out.append("<sheetData>")
    for i, row in enumerate(rows, 1):
        cells = []
        for j, v in enumerate(row, 1):
            if v is None or v == "":
                continue
            ref = f"{_col(j)}{i}"
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                cells.append(f'<c r="{ref}"><v>{v}</v></c>')
            else:
                cells.append(f'<c r="{ref}" t="inlineStr"><is><t xml:space="preserve">{escape(_ILLEGAL.sub("", str(v)))}</t></is></c>')
        out.append(f'<row r="{i}">{"".join(cells)}</row>')
    out.append("</sheetData>")
    out.append(f'<autoFilter ref="A1:{_col(ncol)}{max(len(rows), 1)}"/></worksheet>')
    return "".join(out)


def add_sheet(src, dst, name, rows, widths=()):
    """Salin src ke dst dengan sheet baru `name`. Nama yang sudah ada ditolak (tidak menimpa)."""
    if len(name) > 31 or re.search(r"[\[\]:*?/\\]", name):
        raise ValueError(f"nama sheet tidak valid: {name!r}")
    with zipfile.ZipFile(src) as zin:
        names = zin.namelist()
        wb = zin.read("xl/workbook.xml").decode("utf-8")
        rels = zin.read("xl/_rels/workbook.xml.rels").decode("utf-8")
        ct = zin.read("[Content_Types].xml").decode("utf-8")
        if re.search(rf'<sheet\b[^>]*\bname="{re.escape(escape(name))}"', wb):
            raise ValueError(f"sheet {name!r} sudah ada")
        n = 1
        while f"xl/worksheets/sheet{n}.xml" in names:
            n += 1
        part = f"worksheets/sheet{n}.xml"
        rid_n = 1 + max([int(x) for x in re.findall(r'\bId="rId(\d+)"', rels)] or [0])
        sid = 1 + max([int(x) for x in re.findall(r'\bsheetId="(\d+)"', wb)] or [0])
        prefix = re.search(r'<(?:(\w+):)?sheets\b', wb).group(1)
        tag = f"{prefix}:sheet" if prefix else "sheet"
        new_sheet = f'<{tag} name="{escape(name)}" sheetId="{sid}" xmlns:r="{_NS_R}" r:id="rId{rid_n}"/>'
        wb = re.sub(r"(</(?:\w+:)?sheets>)", lambda m: new_sheet + m.group(1), wb, count=1)
        rels = rels.replace("</Relationships>", f'<Relationship Id="rId{rid_n}" Type="{_REL_TYPE}" Target="{part}"/></Relationships>')
        ct = ct.replace("</Types>", f'<Override PartName="/xl/{part}" ContentType="{_CT_SHEET}"/></Types>')
        with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zout:
            for info in zin.infolist():
                data = zin.read(info.filename)
                if info.filename == "xl/workbook.xml":
                    data = wb.encode("utf-8")
                elif info.filename == "xl/_rels/workbook.xml.rels":
                    data = rels.encode("utf-8")
                elif info.filename == "[Content_Types].xml":
                    data = ct.encode("utf-8")
                zout.writestr(info, data)
            zout.writestr(f"xl/{part}", sheet_xml(rows, widths))
