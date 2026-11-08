"""K9a: bensin motor. Baca liter/harsat/km dari pesan, cek km, hitung kisaran km saat bensin habis.
Hitungan memakai N pengisian terakhir saja (data lama diabaikan). Titik km yang melenceng (salah ketik) dibuang
dengan deret km naik terpanjang, liter di antara dua titik sah dijumlahkan, jadi isian kecil tidak merusak rata-rata."""
import bisect
import re
from statistics import median


# kata penanda BBM; "vivo"/"bp" saja bukan penanda (merek HP / singkatan lain)
FUEL_WORDS = re.compile(
    r"\b(?:bensin|bbm|pertalite|pertamax|pertamina|dexlite|bio ?solar|solar|bp ?9[25]|bp ultimate|vivo ?9\d|revvo ?\d+|shell|v-?power)\b",
    re.IGNORECASE)
_KM = re.compile(r"(?<![\w.])km\.?\s*[:=]?\s*(?P<v>\d[\d.,]*)", re.IGNORECASE)
_LITER = re.compile(r"(?<![\w.,])(?P<v>\d+(?:[.,]\d+)?)\s*(?:liter|ltr|lt|l)(?![a-z\d])", re.IGNORECASE)
_HARSAT = re.compile(r"(?:harsat|@)\s*(?P<v>\d[\d.,]*)(?:\s*/\s*(?:l|liter))?", re.IGNORECASE)
_FORCE = re.compile(r"\bpaksa\b", re.IGNORECASE)
MIN_KM = 1000        # km di bawah ini dianggap kosong/salah ketik
MAX_LITER = 4.5      # satu isian motor tidak mungkin lebih
MOTOR_CATEGORY, OTHER_CATEGORY = "BBM Motor", "BBM Lainnya"


class FuelError(ValueError):
    """Pesan BBM motor tidak lengkap atau tidak wajar; isi pesan = alasan untuk pengguna."""


def _decimal(s):  # liter: titik/koma = desimal ("3.050" = 3,05 liter)
    return float(s.strip(".,").replace(",", "."))


def _thousands(s):  # km/harsat: "39.200,1" dan "16.130" = ribuan Indonesia; "39200.1" = desimal
    s = s.strip(".,")
    if re.fullmatch(r"\d{1,3}(\.\d{3})+(,\d+)?", s):
        s = s.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"\d{1,3}(,\d{3})+(\.\d+)?", s):
        s = s.replace(",", "")
    else:
        s = s.replace(",", ".")
    return float(s)


def detect_motor(text, motors):
    t = text.lower()
    return next((m for m in motors if re.search(rf"\b{re.escape(m.lower())}\b", t)), None)


def extract(text, motors):
    """(info | None, teks tanpa liter/harsat/km). None = bukan pesan BBM (teks tidak diubah).
    info = {'motor': nama | None, 'liter', 'harsat', 'km'}; yang tidak disebut bernilai None."""
    motor = detect_motor(text, motors)
    km_m, lit_m, har_m = _KM.search(text), _LITER.search(text), _HARSAT.search(text)
    if not (FUEL_WORDS.search(text) or (motor and (lit_m or har_m))):
        return None, text
    info = {"motor": motor, "liter": None, "harsat": None, "km": None, "force": bool(_FORCE.search(text))}
    spans = [m.span() for m in _FORCE.finditer(text)]
    try:
        if lit_m:
            info["liter"] = _decimal(lit_m.group("v"))
            spans.append(lit_m.span())
        if har_m:
            info["harsat"] = int(round(_thousands(har_m.group("v"))))
            spans.append(har_m.span())
        if km_m:
            info["km"] = _thousands(km_m.group("v"))
            spans.append(km_m.span())
    except ValueError:
        raise FuelError("angka liter/harsat/km tidak terbaca") from None
    for a, b in sorted(spans, reverse=True):
        text = text[:a] + " " + text[b:]
    return info, re.sub(r"\s+", " ", text).strip(" ,-:;")


def finish(info, amount):
    """Lengkapi liter/harsat dari nominal; kembalikan dict untuk tabel _bbmmotor, atau None (BBM selain motor tercatat).
    Liter, harsat, dan nominal yang ketiganya disebut harus saling cocok (selisih maks 2%) kecuali ada kata 'paksa'."""
    if info["motor"] is None:
        return None
    liter, harsat, km = info["liter"], info["harsat"], info["km"]
    if km is None:
        raise FuelError(f"BBM {info['motor']} perlu km odometer (contoh: km50400.1)")
    if liter is None and harsat:
        liter = round(amount / harsat, 3)
    if liter is None:
        raise FuelError(f"BBM {info['motor']} perlu liter (contoh: 3.05L) atau harga per liter (contoh: @16130)")
    if not 0.2 <= liter <= MAX_LITER:
        raise FuelError(f"liter {liter:g} tidak wajar")
    if km < MIN_KM:
        raise FuelError(f"km {km:g} tidak wajar")
    if info["liter"] is not None and harsat and not info.get("force"):
        expected = info["liter"] * harsat
        if abs(expected - amount) > 0.02 * amount:
            rp = lambda n: "Rp" + f"{round(n):,}".replace(",", ".")
            raise FuelError(f"nominal tidak cocok: {str(info['liter']).replace('.', ',')} L x {rp(harsat)} = {rp(expected)}, bukan {rp(amount)}. "
                            "Cek liter/harsat/nominal, atau tambahkan kata 'paksa'")
    return {"motor": info["motor"], "liter": round(liter, 3), "harsat": harsat or int(round(amount / liter)), "km": km}


def check_km(km, date_, rows, max_jump):
    """Alasan penolakan (str) bila km baru tidak masuk akal dibanding isian sah terakhir motor itu, selain itu None.
    Isian bertanggal lebih lama dari isian terakhir tidak dicek."""
    kept = _kept(rows)
    if not kept or date_ < kept[-1]["date"]:
        return None
    last = kept[-1]["km"]
    if km <= last:
        return f"km {fmt_km(km)} tidak lebih besar dari km terakhir {fmt_km(last)}"
    if km - last > max_jump:
        return f"km {fmt_km(km)} terlalu jauh dari km terakhir {fmt_km(last)} (selisih {fmt_km(km - last)})"
    return None


def fmt_km(x):
    return f"{x:,.1f}".replace(",", "_").replace(".", ",").replace("_", ".")


def _lis(xs):
    """Indeks deret naik (ketat) terpanjang."""
    tails, idx, prev = [], [], [-1] * len(xs)
    for i, x in enumerate(xs):
        k = bisect.bisect_left(tails, x)
        if k == len(tails):
            tails.append(x)
            idx.append(i)
        else:
            tails[k], idx[k] = x, i
        prev[i] = idx[k - 1] if k else -1
    out, i = [], idx[-1] if idx else -1
    while i != -1:
        out.append(i)
        i = prev[i]
    return out[::-1]


def _points(rows):
    return sorted((r for r in rows if r.get("km") and r["km"] >= MIN_KM and r.get("liter")),
                  key=lambda r: (r["date"], r.get("seq", 0)))


def _kept(rows):
    pts = _points(rows)
    return [pts[i] for i in _lis([p["km"] for p in pts])]


def analyze(rows, window_fills=12, tank=None):
    """rows: isian SATU motor [{date, liter, km, row?, seq?}]. None bila titik sah kurang dari dua.
    Jendela = window_fills isian sah terakhir (segmen jarak antar isian); bila data lebih sedikit, semuanya dipakai."""
    pts = _points(rows)
    keep = _lis([p["km"] for p in pts])
    if len(keep) < 2:
        return None
    last = pts[keep[-1]]
    first = max(0, len(keep) - 1 - window_fills)  # titik dasar jarak untuk isian pertama di jendela
    segs = [(pts[b]["km"] - pts[a]["km"], sum(p["liter"] for p in pts[a + 1:b + 1])) for a, b in zip(keep[first:], keep[first + 1:])]
    dist, lit = sum(d for d, _ in segs), sum(x for _, x in segs)
    km_per_l = dist / lit
    span = pts[keep[first] + 1:keep[-1] + 1]
    typical = median(p["liter"] for p in span)
    tank = tank or max(p["liter"] for p in pts if p["liter"] <= MAX_LITER)
    kept_idx = set(keep)
    skipped = [p for i, p in enumerate(pts) if keep[first] < i < keep[-1] and i not in kept_idx]
    return {"last_km": last["km"], "last_date": last["date"], "km_per_l": km_per_l, "l_per_km": 1 / km_per_l,
            "fills": len(segs), "short": len(segs) < window_fills, "from": pts[keep[first]]["date"],
            "typical": typical, "tank": tank, "low": last["km"] + typical * km_per_l, "high": last["km"] + tank * km_per_l,
            "skipped": skipped}
