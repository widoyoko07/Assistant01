"""K5: tanggal mundur di awal atau akhir pesan: kemarin, kamis, 29/10, tgl 29, 29 okt, 2 hari lalu."""
import re
from datetime import date, timedelta

DAYS = {"senin": 0, "selasa": 1, "rabu": 2, "kamis": 3, "jumat": 4, "jum'at": 4, "sabtu": 5, "minggu": 6, "ahad": 6}
MONTHS = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "mei": 5, "jun": 6, "jul": 7, "agu": 8, "agt": 8, "sep": 9,
          "okt": 10, "nov": 11, "des": 12}
_DAY = "|".join(sorted((d.replace("'", "'?") for d in DAYS), key=len, reverse=True))
_EXPR = (rf"hari ini|kemarin lusa|kemarin|\d+\s+hari\s+lalu|(?:hari\s+)?(?:{_DAY})|(?:tgl|tanggal)\.?\s*\d{{1,2}}"
         rf"|\d{{1,2}}[/-]\d{{1,2}}(?:[/-]\d{{2,4}})?|\d{{1,2}}\s*(?:{'|'.join(MONTHS)})[a-z]*")
_HEAD = re.compile(rf"^(?P<sign>[+-]?)\s*(?P<d>{_EXPR})\s*[,:]?\s+(?P<rest>\S.*)$", re.IGNORECASE)
_TAIL = re.compile(rf"^(?P<rest>\S.*?)\s+(?P<d>{_EXPR})$", re.IGNORECASE)


class FutureDate(ValueError):
    pass


def _resolve(expr, base):
    e = re.sub(r"\s+", " ", expr.lower().strip())
    if e == "hari ini":
        return base
    if e == "kemarin lusa":
        return base - timedelta(days=2)
    if e == "kemarin":
        return base - timedelta(days=1)
    if m := re.fullmatch(r"(\d+) hari lalu", e):
        return base - timedelta(days=int(m.group(1)))
    if m := re.fullmatch(r"(?:hari )?([a-z']+)", e):
        if m.group(1) not in DAYS:
            raise ValueError(expr)
        wd = DAYS[m.group(1)]
        return base - timedelta(days=(base.weekday() - wd) % 7)   # hari itu yang terakhir, termasuk hari ini
    if m := re.fullmatch(r"(?:tgl|tanggal)\.? ?(\d{1,2})", e):
        day = int(m.group(1))
        y, mo = (base.year, base.month) if day <= base.day else ((base.year, base.month - 1) if base.month > 1 else (base.year - 1, 12))
        return date(y, mo, day)
    if m := re.fullmatch(r"(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?", e):
        d, mo, y = int(m.group(1)), int(m.group(2)), m.group(3)
        y = base.year if not y else (int(y) + 2000 if len(y) == 2 else int(y))
        return _check(date(y, mo, d), base)
    if m := re.fullmatch(r"(\d{1,2}) ?([a-z]+)", e):
        return _check(date(base.year, MONTHS[m.group(2)[:3]], int(m.group(1))), base)
    raise ValueError(expr)


def _check(d, base):
    if d > base:
        raise FutureDate(d.isoformat())
    return d


_ONLY = re.compile(rf"^(?:{_EXPR})$", re.IGNORECASE)


def only_date(text, base):
    """Tanggal bila seluruh teks hanya ungkapan tanggal ('kemarin', 'kamis:', '29/10'); selain itu None."""
    t = text.strip().rstrip(":,")
    if not _ONLY.match(t):
        return None
    try:
        return _resolve(t, base)
    except FutureDate:
        raise
    except (ValueError, KeyError):
        return None


def extract_date(text, base):
    """(tanggal | None, teks tanpa ungkapan tanggal). Hanya di awal atau akhir pesan; tanggal masa depan = FutureDate."""
    t = text.strip()
    for pat in (_HEAD, _TAIL):
        m = pat.match(t)
        if m:
            try:
                d = _resolve(m.group("d"), base)
            except FutureDate:
                raise
            except (ValueError, KeyError):
                continue
            sign = m.groupdict().get("sign") or ""
            return d, (sign + m.group("rest")).strip()
    return None, t
