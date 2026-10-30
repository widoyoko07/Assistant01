"""M3: ambil pesan Posting TBM tiap SC dari chat grup SC -> data/02_mp/<SC> TBM <YYYYMMDD> Posting.txt.

Persis format yang dibaca Daily MP v10. Pengenal pesan per SC ada di config.tbm; SC yang belum
dikonfigurasi dilaporkan, bukan ditebak.
"""
import re
from datetime import date, datetime

from ..common import config as cfgmod
from ..common.runlog import RunLog

_LEAD_MEDIA = re.compile(r"^(?:\[Forwarded\]\s*)?<(?:image|video|document) omitted>\s*", re.I)


def posting_text(msg, rule):
    """Isi Posting.txt dari satu pesan: buang penanda media di depan, potong di bagian penutup."""
    text = _LEAD_MEDIA.sub("", msg["text"]).strip("\n")
    lines = text.splitlines()
    end = re.compile(rule["end"], re.I) if rule.get("end") else None
    if end:
        for i, line in enumerate(lines):
            if end.search(line.strip()):
                lines = lines[:i]
                break
    return "\n".join(lines).rstrip() + "\n"


_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "mei": 5, "may": 5, "jun": 6, "jul": 7, "agu": 8, "aug": 8,
    "sep": 9, "okt": 10, "oct": 10, "nov": 11, "des": 12, "dec": 12,
}
_TEXT_DATE = re.compile(r"(\d{1,2})\s*[-/ ]?\s*(\d{1,2}|[A-Za-z]{3,9})\s*[-/ ]?\s*(\d{4})")


def text_date(text):
    """Tanggal yang ditulis di teks pesan ('27 Okt 2026', '28-10-2026', '14-October-2026'); None bila tidak ada."""
    for d, mo, y in _TEXT_DATE.findall(text):
        mo = int(mo) if mo.isdigit() else _MONTHS.get(mo[:3].lower())
        try:
            return date(int(y), mo, int(d)).isoformat()
        except (TypeError, ValueError):
            continue
    return None


def is_posting(msg, rule):
    text = msg["text"]
    if msg.get("system"):
        return False
    if rule.get("header_re"):
        if not re.search(rule["header_re"], text, re.I):
            return False
    elif rule["header"].upper() not in text.upper():
        return False
    return not (rule.get("skip") and rule["skip"].upper() in text.upper())


def pick_postings(messages, rule, log=None):
    """{tanggal: pesan}. Bila ada 2+ posting di hari yang sama dipakai yang terakhir, dengan peringatan 'revisi'."""
    by_date = {}
    for m in messages:
        if not is_posting(m, rule):
            continue
        sent = datetime.fromisoformat(m["ts"]).date().isoformat()
        written = text_date(m["text"])
        if rule.get("date") == "text" and written:
            d = written  # SC yang sering kirim terlambat: tanggal di teks lebih benar daripada waktu kirim
        else:
            d = sent
            if written and written != sent and log:
                log.warn(f"{sent}: teks bertanggal {written} (salah ketik?), dipakai tanggal kirim")
        if d in by_date and log:
            log.warn(f"{d}: lebih dari satu posting, dipakai yang terakhir (revisi)")
        by_date[d] = m
    return by_date


def split_all(messages, sc, cfg, root=None, log=None):
    """Tulis Posting.txt untuk semua tanggal SC ini. Kembalikan daftar path yang ditulis."""
    log = log or RunLog("tbm_split", root=root)
    rule = cfg.get("tbm", {}).get(sc)
    if not rule:
        log.warn(f"{sc}: pengenal Posting belum ada di config.tbm, dilewati")
        return []
    out_dir = cfgmod.data_dir(root=root) / "02_mp"
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for d, m in sorted(pick_postings(messages, rule, log).items()):
        path = out_dir / f"{sc} TBM {d.replace('-', '')} Posting.txt"
        path.write_text(posting_text(m, rule), encoding="utf-8", newline="\n")
        log.done(f"{path.name}")
        written.append(path)
    if not written:
        log.warn(f"{sc}: tidak ada pesan Posting ditemukan")
    return written
