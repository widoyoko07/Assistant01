"""K9b: token listrik. Baca bacaan meter/kWh dari pesan dan perkirakan kapan sisa 20 kWh dan 0 kWh.
Rumus mengikuti tabel _listrik: kWh/jam = |selisih kWh| / total jam (dibulatkan) per interval yang sisanya turun,
dirata-rata; waktu = pembacaan terakhir + sisa / rata-rata."""
import math
import re
from datetime import datetime, timedelta

_NUM = r"\d+(?:[.,]\d+)?"
_TIME = re.compile(r"\bjam\s*(\d{1,2})[.:](\d{2})\b", re.IGNORECASE)
_READING = re.compile(rf"^(?:meter|kwh)\s*[:=]?\s*({_NUM})$", re.IGNORECASE)
_TOPUP = re.compile(rf"(?<![\w.,])({_NUM})\s*kwh\b", re.IGNORECASE)
_SISA = re.compile(rf"\b(?:meter|sisa)\s*[:=]?\s*({_NUM})", re.IGNORECASE)
LISTRIK_WORDS = re.compile(r"\b(?:token|listrik|pln)\b", re.IGNORECASE)
MONTHS = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"]
EPOCH = datetime(1899, 12, 30)


class ListrikError(ValueError):
    """Pesan listrik tidak lengkap atau tidak wajar; isi pesan = alasan untuk pengguna."""


def _num(s):
    return float(s.replace(",", "."))


def relevant(text):
    """Pesan menyangkut listrik (kata token/listrik/pln, atau diawali 'meter'/'kwh'): hanya pesan ini yang dicek 'jam hh.mm'."""
    return bool(LISTRIK_WORDS.search(text) or re.match(r"^\s*(?:meter|kwh)\b", text, re.IGNORECASE))


def extract_time(text):
    """(jam, menit) | None, teks tanpa 'jam 05.48'."""
    m = _TIME.search(text)
    if not m:
        return None, text
    h, mi = int(m.group(1)), int(m.group(2))
    if h > 23 or mi > 59:
        raise ListrikError(f"jam {m.group(0)[3:].strip()} tidak valid")
    return (h, mi), re.sub(r"\s+", " ", text[:m.start()] + " " + text[m.end():]).strip()


def parse_reading(text):
    """Bacaan meter bila seluruh pesan hanya 'meter 95,3' / 'kwh 95,3'; selain itu None."""
    m = _READING.match(text.strip())
    return _num(m.group(1)) if m else None


def extract_topup(text):
    """(info | None, teks bersih). Hanya untuk pesan token listrik: '128,2kwh' = isi ulang, 'meter 141,14' = sisa sesudahnya.
    info = {'topup': kWh | None, 'sisa': kWh}; sisa wajib bila topup disebut."""
    if not LISTRIK_WORDS.search(text):
        return None, text
    top, sisa = _TOPUP.search(text), _SISA.search(text)
    if not (top or sisa):
        return None, text
    if top and not sisa:
        raise ListrikError("sisa meter belum disebut (tambahkan 'meter 141,14')")
    for m in sorted([m for m in (top, sisa) if m], key=lambda m: m.start(), reverse=True):
        text = text[:m.start()] + " " + text[m.end():]
    return {"topup": _num(top.group(1)) if top else None, "sisa": _num(sisa.group(1))}, re.sub(r"\s+", " ", text).strip(" ,-:;")


def check_sisa(sisa):
    if not 0 <= sisa <= 2000:
        raise ListrikError(f"kWh {sisa:g} tidak wajar")


def stamp(date_, hm, ts):
    """Waktu pembacaan: tanggal pesan (atau tanggal mundur) + jam dari 'jam hh.mm' atau jam pesan."""
    h, m = hm if hm else (ts.hour, ts.minute)
    return datetime(date_.year, date_.month, date_.day, h, m)


def _half_up(x):
    return math.floor(x + 0.5)


def rates(readings):
    """[(waktu, kWh/jam)] per interval yang sisanya turun, mengikuti kolom Selisih/kWh-per-Jam di tabel."""
    out = []
    for a, b in zip(readings, readings[1:]):
        diff = b["sisa"] - a["sisa"]
        days = (b["t"] - a["t"]).total_seconds() / 86400
        g = int((days * 24) // 1)
        h = _half_up((days * 1440) % 60)
        total_hours = _half_up(g + h / 60)
        if diff < 0 and total_hours > 0:
            out.append((b["t"], round(abs(diff) / total_hours, 3)))
    return out


def estimate(readings, sisa=None, now=None, low=20.0, window_days=None):
    """readings: [{t: datetime, sisa}] urut waktu. sisa+now = bacaan meter sekarang (tidak disimpan).
    None bila belum ada interval pemakaian."""
    rs = rates(readings)
    if window_days and readings:
        cut = readings[-1]["t"] - timedelta(days=window_days)
        rs = [r for r in rs if r[0] >= cut]
    if not rs or not readings:
        return None
    rate = round(sum(r for _, r in rs) / len(rs), 4)  # seperti sel rata-rata di tabel (ROUND ..., 4)
    base_t, base_s = (now, sisa) if sisa is not None else (readings[-1]["t"], readings[-1]["sisa"])
    at = lambda kwh: base_t + timedelta(hours=round(max(base_s - kwh, 0) / rate, 2))  # jam dibulatkan 2 desimal seperti tabel
    return {"rate": rate, "n": len(rs), "base_t": base_t, "base_sisa": base_s, "t_low": at(low), "t_zero": at(0), "low": low}


def fmt_time(t, today=None):
    t = t + timedelta(seconds=30)  # dibulatkan ke menit terdekat
    year = "" if today and t.year == today.year else f" {t.year}"
    return f"{t.day} {MONTHS[t.month - 1]}{year} {t:%H:%M}"


def dec(x, n):
    """Angka desimal gaya Indonesia: 51,6."""
    return f"{x:.{n}f}".replace(".", ",")


def fmt_kwh(x):
    return f"{x:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".").rstrip("0").rstrip(",")


def from_serial(x):
    return EPOCH + timedelta(days=float(x))
