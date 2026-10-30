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


def work_description(parts, sc, date):
    """Butir kerja satu SC pada satu tanggal: laporan harian dan lembur digabung, urutan chat, tanpa duplikat.
    Baris 'MP: n' dibuang (angka manpower diambil dari Daily MP, bukan dari narasi)."""
    seen, out = set(), []
    for p in parts:
        if p["sc"] != sc or p["date"] != date:
            continue
        for line in p["lines"]:
            key = _BULLET.sub("", line).strip().lower()
            if not key or re.match(r"mp\s*:", key) or _LABEL.match(key) or key in seen:
                continue
            seen.add(key)
            out.append(line)
    return out


def write_csv(messages, cfg, root=None, log=None):
    """Draf narasi ME: satu baris per (tanggal, SC) ke data/03_me/narasi_<dari>_<sampai>.csv.
    Kolom jam sudah mengikuti aturan OT (21.00 / 12 jam). Draf ini untuk dicek manual sebelum masuk DPR."""
    log = log or RunLog("me_report", root=root)
    parts, daily = collect(messages, cfg, log)
    if not daily:
        log.warn("tidak ada laporan ME ditemukan")
        return None
    out_dir = cfgmod.data_dir(root=root) / "03_me"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"narasi_{daily[0]['date'].replace('-', '')}_{daily[-1]['date'].replace('-', '')}.csv"
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date", "sc", "overtime", "start", "finish", "total_hours", "work_description"])
        for r in daily:
            w.writerow([r["date"], r["sc"], "Y" if r["ot"] else "", r["start"], r["finish"], r["total"],
                        "\n".join(work_description(parts, r["sc"], r["date"]))])
    log.done(path.name)
    return path
