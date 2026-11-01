"""M5 (prototipe): blok SUB ME satu tanggal untuk DPR, sebagai workbook pratinjau BARU (file DPR dan Civil tidak disentuh).

Isi tiap SC mengikuti blok SUB ME di DPR final: nama SC, butir kerja ('Butir Final' yang diberi "x" di WD Kandidat), jam,
manpower per role (dari sheet ME, kolom tanggal itu), total, dan equipment (default = hari DPR template). Kategori kerja (kolom C)
tidak ada di data -> diambil dari DPR template bila SC itu ada di sana, selain itu dikosongkan untuk diisi manual.
Pratinjau ini dicek dulu; menyambungkannya ke DPR final (sisip baris, sel gabungan, rumus) belum dikerjakan.
"""
from datetime import date
from pathlib import Path

from ..common import config as cfgmod
from .me_sheet import _blocks, date_col

DPR_NAME = {"Tohoma": "Tohoma", "DJK DCIP": "DJK", "DHJ": "DHJ", "WKP": "WKP", "TPE": "TPE", "WME": "WME", "SILOG": "SILOG", "BCP": "BCP"}
WD_SC = {"TODJO": ["Tohoma", "DJK DCIP"], "DHJ": ["DHJ"], "WKP": ["WKP"], "TPE": ["TPE"], "WME": ["WME"], "SILOG": ["SILOG"], "BCP": ["BCP"]}
ORDER = ["Tohoma", "DJK DCIP", "DHJ", "WKP", "TPE", "WME", "SILOG", "BCP"]


def manpower(ws_me, cfg, day, block, roles, extra_map):
    """{kolom DPR (nama role): jumlah} dari blok sheet ME pada tanggal day."""
    ms = cfg["me_sheet"]
    col = date_col(ms, day)
    r0, r1 = _blocks(ws_me, ms)[block]
    out = {}
    for r in range(r0, r1 + 1):
        label, v = ws_me.cell(r, 4).value, ws_me.cell(r, col).value
        if not label or label == "Total Manpower" or not isinstance(v, (int, float)) or v <= 0:
            continue
        label = extra_map.get(label, label)
        if label not in roles:
            raise ValueError(f"role '{label}' di blok {block} tidak punya kolom di DPR")
        out[label] = out.get(label, 0) + int(v)
    return out


def items_by_sc(wd_xlsx, day):
    """{SC di WD Kandidat: ([butir], mulai, selesai, jam)} untuk baris ber-x pada tanggal day."""
    import openpyxl
    out = {}
    for r in openpyxl.load_workbook(wd_xlsx, read_only=True)["WD Kandidat"].iter_rows(min_row=2, values_only=True):
        if r[0] == "x" and r[1] == day.isoformat():
            butir = (r[9] or r[8] or "").strip()
            lst = out.setdefault(r[2], ([], r[4], r[5], r[6]))[0]
            lst.append(butir if butir.startswith("-") else "- " + butir)
    return out


def template_info(dpr_xlsx, sheet, cfg):
    """(nama role di kolom J..AI, {SC: (kategori, {equipment kolom: nilai})}) dari blok SUB ME DPR template."""
    import openpyxl
    from openpyxl.utils import get_column_letter as L
    ws = openpyxl.load_workbook(dpr_xlsx)[sheet]
    roles = [ws.cell(15, c).value for c in range(10, 36)]
    start = next(r for r in range(30, 200) if ws.cell(r, 2).value == "SUB ME")
    info, cur = {}, None
    for r in range(start + 1, start + 45):
        name = ws.cell(r, 2).value
        if name:
            cur = name
            info.setdefault(cur, [ws.cell(r, 3).value, {L(c): ws.cell(r, c).value for c in range(37, 50) if ws.cell(r, c).value}])
        elif cur and ws.cell(r, 3).value and not info[cur][0]:
            info[cur][0] = ws.cell(r, 3).value
    return roles, info


def build(me_xlsx, wd_xlsx, dpr_template, template_sheet, day, out_path, cfg=None):
    import openpyxl
    from openpyxl.utils import get_column_letter as L
    cfg = cfg or cfgmod.load()
    me = openpyxl.load_workbook(me_xlsx)["ME"]
    roles, info = template_info(dpr_template, template_sheet, cfg)
    extra_map = cfg.get("dpr_role_map", {})
    wd = items_by_sc(wd_xlsx, day)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = f"{day.day} {day.strftime('%b')} SUB ME"
    ws.append(["", "SUBCONT.", "WORK CATEGORY", "WORK DESCRIPTION", "", "", "START", "FINISH", "TOTAL (hour)"] + roles + ["Total Manpower"])
    notes = []
    for name in ORDER:
        mp = manpower(me, cfg, day, name, roles, extra_map)
        sc = next(k for k, v in WD_SC.items() if name in v)
        if sc == "TODJO":                # butir TODJO tidak dipisah Tohoma/DJK di data: ditaruh di DJK, dibagi manual
            lst = wd.get("TODJO", ([], None, None, None)) if name == "DJK DCIP" else ([], None, None, None)
        else:
            lst = wd.get(sc, ([], None, None, None))
        items, start, finish, jam = lst
        if not mp and not items:
            continue
        if not items:
            notes.append(f"{DPR_NAME[name]}: ada manpower ({sum(mp.values())}) tetapi belum ada butir ber-x")
        if sc == "TODJO" and name == "DJK DCIP" and items:
            notes.append("TODJO: butir ditaruh di blok DJK; pembagian Tohoma/DJK dilakukan manual")
        cat = (info.get(DPR_NAME[name]) or [None])[0]
        rows = max(len(items), 1)
        for i in range(rows):
            row = ["", DPR_NAME[name] if i == 0 else "", (cat or "") if i == 0 else "", items[i] if i < len(items) else ""]
            row += ["", "", start if i == 0 else "", finish if i == 0 else "", jam if i == 0 else ""]
            row += [mp.get(role, "") if i == 0 else "" for role in roles]
            row += [sum(mp.values()) if i == 0 else ""]
            ws.append(row)
    for n in notes:
        ws.append([])
        ws.append(["", "CATATAN: " + n])
    ws.column_dimensions["D"].width = 70
    wb.save(out_path)
    return notes
