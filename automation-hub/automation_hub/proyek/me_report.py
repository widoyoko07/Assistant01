"""Laporan ME dari grup WA: pecah pesan per subcon, tandai lembur, hitung jam DPR.

Penanda subcon tidak seragam ("24/10/26 TPE", "Silog - 24 Oct 2026", "TOHOMA Activity ..."),
jadi nama dicocokkan lewat config.sc_aliases. Satu pesan boleh memuat beberapa subcon.
"""
import csv
import re
from datetime import datetime

from ..common import config as cfgmod
from ..common.runlog import RunLog

_OT = re.compile(r"\b(?:overtime|ot)\b", re.I)
_WORD = re.compile(r"[a-z]+")
_BULLET = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s*")
_LABEL = re.compile(r"activity\s*:?$")  # baris label 'Activity:' tanpa isi
MAX_HEADER_WORDS = 10


def header_scs(line, aliases):
    """Kode SC yang disebut di baris judul; [] bila baris bukan judul (butir kerja / terlalu panjang)."""
    if _BULLET.match(line) or len(_WORD.findall(line.lower())) > MAX_HEADER_WORDS:
        return []
    found = []
    for w in _WORD.findall(line.lower()):
        sc = aliases.get(w)
        if sc and sc not in found:
            found.append(sc)
    return found


def split_message(msg, aliases):
    """Pesan -> [{'date','sc','ot','lines','msg_id'}]. SC ganda di satu judul ("Thm-Dwj") diberi 'sc' None
    dan 'candidates' berisi semua kemungkinannya, supaya dilaporkan, bukan ditebak."""
    date = datetime.fromisoformat(msg["ts"]).date().isoformat()
    sections, cur, ot_seen = [], None, False
    for line in (msg.get("caption") or "").splitlines():
        scs = header_scs(line, aliases)
        is_ot = bool(_OT.search(line)) and not _BULLET.match(line)
        ot_seen = ot_seen or is_ot
        if scs:
            cur = {"date": date, "sc": scs[0] if len(scs) == 1 else None, "candidates": scs,
                   "ot": ot_seen, "lines": [], "msg_id": msg["id"]}
            sections.append(cur)
        elif is_ot and len(_WORD.findall(line.lower())) <= 2:
            cur = None  # judul 'Overtime 29/10/2026' tanpa nama SC: bukan isi section sebelumnya
        elif cur is not None and line.strip():
            cur["lines"].append(line.strip())
    return sections


def dpr_hours(ot, cfg):
    """(start, finish, total) untuk satu subcon; lembur memakai jam OT dari config."""
    h = cfg["dpr"]["hours"]["overtime" if ot else "normal"]
    return h["start"], h["finish"], h["total"]


def collect(messages, cfg, log=None):
    """Semua bagian laporan per subcon dari daftar pesan; gabungkan OT per (tanggal, SC)."""
    aliases = cfg.get("sc_aliases", {})
    parts, by_key = [], {}
    for m in messages:
        if m.get("system"):
            continue
        for sec in split_message(m, aliases):
            if sec["sc"] is None:
                if log:
                    log.warn(f"{sec['date']}: judul menyebut beberapa SC {sec['candidates']}, tidak dipisah otomatis")
                continue
            parts.append(sec)
            key = (sec["date"], sec["sc"])
            by_key.setdefault(key, {"date": sec["date"], "sc": sec["sc"], "ot": False})
            by_key[key]["ot"] = by_key[key]["ot"] or sec["ot"]
    for rec in by_key.values():
        rec["start"], rec["finish"], rec["total"] = dpr_hours(rec["ot"], cfg)
    return parts, sorted(by_key.values(), key=lambda r: (r["date"], r["sc"]))


def _keyed(lines):
    """(konteks, butir, baris): konteks = judul area terakhir (baris tanpa tanda butir). Butir yang sama di area
    berbeda ("- Touch up painting" di STB dan di LPS) adalah pekerjaan berbeda, jadi bukan duplikat."""
    ctx = ""
    for line in lines:
        if not _BULLET.match(line):
            ctx = line.lower().strip(" :-")
        yield ctx, _BULLET.sub("", line).strip().lower(), line


def merge_items(*sources):
    """Gabung beberapa daftar butir, urutan sumber dipertahankan. Duplikat = butir dan area sama.
    Kembalikan [(baris, nomor_sumber)]."""
    seen, out = set(), []
    for n, lines in enumerate(sources):
        for ctx, key, line in _keyed(lines):
            if not key or (ctx, key) in seen:
                continue
            seen.add((ctx, key))
            out.append((line, n))
    return out


def work_description(parts, sc, date):
    """Butir kerja satu SC pada satu tanggal dari narasi grup ME: laporan harian dan lembur digabung.
    Baris 'MP: n' dan label 'Activity:' dibuang (angka manpower diambil dari Daily MP, bukan dari narasi)."""
    lines = []
    for p in parts:
        if p["sc"] == sc and p["date"] == date:
            lines += [l for l in p["lines"] if not re.match(r"mp\s*:", l.strip().lower()) and not _LABEL.match(l.strip().lower())]
    return [l for l, _ in merge_items(lines)]


_INVISIBLE = re.compile("[\u200e\u200f\u2060\ufeff]")
_MP_NOTE = re.compile(r"\(\s*(?:mp\s*)?\d+\s*(?:mp|persons?|orang)?\s*\)", re.I)  # "(mp 29)", "(21 mp)"


def posting_items(text, rule):
    """Butir kerja dari satu Posting.txt SC. rule (config.wd[SC]): start = baris awal bagian kerja,
    stop = baris penutup, skip_first = buang N baris judul. Tanpa rule: [] (bukan ditebak)."""
    if not rule:
        return []
    lines = [_INVISIBLE.sub("", l).strip() for l in text.splitlines()]
    lines = lines[rule.get("skip_first", 0):]
    if rule.get("start"):
        start = re.compile(rule["start"], re.I)
        idx = next((i for i, l in enumerate(lines) if start.search(l)), None)
        if idx is None:
            return []
        lines = lines[idx + (0 if rule.get("keep_start") else 1):]
    if rule.get("stop"):
        stop = re.compile(rule["stop"], re.I)
        idx = next((i for i, l in enumerate(lines) if stop.search(l)), None)
        if idx is not None:
            lines = lines[:idx]
    out = []
    for l in lines:
        l = _MP_NOTE.sub("", l).strip()
        if l:
            out.append(l)
    return out


def posting_files(root=None):
    """{(tanggal, SC): isi} dari data/02_mp/<SC> TBM <YYYYMMDD> Posting.txt."""
    found = {}
    for path in cfgmod.data_dir(root=root).joinpath("02_mp").glob("* TBM ???????? Posting.txt"):
        sc, _, d, _ = path.name.split(" ")
        found[(f"{d[:4]}-{d[4:6]}-{d[6:]}", sc)] = path.read_text(encoding="utf-8")
    return found


def wd_rows(messages, cfg, root=None, log=None):
    """Butir Work Description per (tanggal, SC), terurut: [(rec, [(butir, 'SC'|'ME')])].
    Butir kerja = rencana kerja di Posting SC (config.wd) + narasi grup ME (laporan harian & lembur)."""
    log = log or RunLog("me_report", root=root)
    parts, daily = collect(messages, cfg, log)
    recs = {(r["date"], r["sc"]): r for r in daily}
    postings = posting_files(root)
    for key in postings:
        if key not in recs:
            recs[key] = {"date": key[0], "sc": key[1], "ot": False}
            recs[key]["start"], recs[key]["finish"], recs[key]["total"] = dpr_hours(False, cfg)
    wd_rules = cfg.get("wd", {})
    out = []
    for r in sorted(recs.values(), key=lambda r: (r["date"], r["sc"])):
        sc_items = posting_items(postings.get((r["date"], r["sc"]), ""), wd_rules.get(r["sc"]))
        me_items = work_description(parts, r["sc"], r["date"])
        merged = [(l, "SC" if k == 0 else "ME") for l, k in merge_items(sc_items, me_items)]
        if not merged:
            log.warn(f"{r['date']} {r['sc']}: tidak ada butir kerja (aturan wd untuk SC ini belum ada atau Posting kosong)")
        out.append((r, merged))
    if not out:
        log.warn("tidak ada laporan ME maupun Posting ditemukan")
    return out


WD_HEADER = ["Tanggal", "SC", "OT", "Start", "Finish", "Jam", "Sumber", "Butir"]


def wd_table(rows):
    """Satu baris per butir (mudah disaring dan disalin); baris pertama = judul kolom."""
    table = [WD_HEADER]
    for r, items in rows:
        for line, src in items:
            table.append([r["date"], r["sc"], "Y" if r["ot"] else "", r["start"], r["finish"], r["total"], src, line])
    return table


def write_sheet(messages, cfg, src_xlsx, dst_xlsx, root=None, log=None, name="WD Kandidat"):
    """Tambah sheet kandidat Work Description ke salinan workbook Subcontractor MP (file asli tidak diubah)."""
    from .xlsx_sheet import add_sheet
    log = log or RunLog("me_report", root=root)
    table = wd_table(wd_rows(messages, cfg, root, log))
    add_sheet(src_xlsx, dst_xlsx, name, table, widths=(11, 8, 5, 8, 8, 6, 8, 90))
    log.done(f"{dst_xlsx} ({len(table) - 1} butir)")
    return dst_xlsx


def write_csv(messages, cfg, root=None, log=None):
    """Draf Work Description ME: satu baris per (tanggal, SC) ke data/03_me/narasi_<dari>_<sampai>.csv.
    Jam mengikuti aturan OT (21.00 / 12 jam). Draf ini dicek manual sebelum masuk DPR."""
    log = log or RunLog("me_report", root=root)
    rows = wd_rows(messages, cfg, root, log)
    if not rows:
        return None
    out_dir = cfgmod.data_dir(root=root) / "03_me"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"narasi_{rows[0][0]['date'].replace('-', '')}_{rows[-1][0]['date'].replace('-', '')}.csv"
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date", "sc", "overtime", "start", "finish", "total_hours", "sumber", "work_description"])
        for r, items in rows:
            src = "+".join(n for n in ("SC", "ME") if any(x == n for _, x in items))
            w.writerow([r["date"], r["sc"], "Y" if r["ot"] else "", r["start"], r["finish"], r["total"], src,
                        "\n".join(l for l, _ in items)])
    log.done(path.name)
    return path
