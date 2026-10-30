"""K2: parser nominal rupiah, jenis transaksi, dan kategori dari kalimat bebas."""
import re
from decimal import Decimal, InvalidOperation

UNCATEGORIZED = "Belum dikategorikan"
INCOME_WORDS = ("gaji", "terima", "transfer masuk", "pemasukan")
MULT = {"k": 1_000, "rb": 1_000, "ribu": 1_000, "jt": 1_000_000, "juta": 1_000_000}

# [Rp] angka [satuan]; satuan tidak boleh disambung huruf lain ("50kg" bukan 50k)
_AMOUNT = re.compile(
    r"(?<![\w.,])(?P<rp>rp\.?\s*)?(?P<num>\d+(?:[.,]\d+)*)\s*(?P<unit>juta|jt|ribu|rb|k)?(?![a-z\d])",
    re.IGNORECASE,
)
_THOUSANDS = re.compile(r"^\d{1,3}([.,]\d{3})+$")


def _number(num, has_unit):
    """Teks angka -> Decimal, atau None bila ambigu."""
    if _THOUSANDS.match(num) and not has_unit:
        return Decimal(re.sub(r"[.,]", "", num))
    if re.fullmatch(r"\d+", num):
        return Decimal(num)
    if has_unit and re.fullmatch(r"\d+[.,]\d{1,2}", num):
        return Decimal(num.replace(",", "."))
    if has_unit and _THOUSANDS.match(num):  # "1.500 rb" = 1.500.000
        return Decimal(re.sub(r"[.,]", "", num))
    return None  # mis. "1,5" tanpa satuan: tidak ditebak


def parse_amount(text):
    """Nominal rupiah (int) dari kalimat, atau None. Kandidat bersatuan/Rp/ribuan diutamakan."""
    best = None  # (skor, nilai)
    ambiguous = False  # dua nominal berbeda dengan skor tertinggi sama: tidak ditebak
    for m in _AMOUNT.finditer(text):
        unit = (m.group("unit") or "").lower()
        num = m.group("num")
        try:
            val = _number(num, bool(unit))
        except InvalidOperation:
            continue
        if val is None:
            continue
        if unit:
            val *= MULT[unit]
        score = 3 if unit else 2 if (m.group("rp") or _THOUSANDS.match(num)) else 1 if val >= 1000 else 0
        if score == 0:
            continue  # angka kecil telanjang ("2 botol") bukan nominal
        if best is None or score > best[0]:
            best, ambiguous = (score, int(val)), False
        elif score == best[0] and int(val) != best[1]:
            ambiguous = True
    return None if ambiguous or best is None else best[1]


def transaction_type(text):
    t = text.strip().lower()
    if t.startswith("+") or any(w in t for w in INCOME_WORDS):
        return "pemasukan"
    return "pengeluaran"


def categorize(text, categories):
    """categories: {kategori: [kata kunci]} dari config. Tidak cocok = UNCATEGORIZED."""
    t = text.lower()
    for cat, words in categories.items():
        for w in words:
            if re.search(rf"\b{re.escape(w.lower())}\b", t):
                return cat
    return UNCATEGORIZED


def parse_entry(text, categories):
    amount = parse_amount(text)
    return {
        "amount": amount,
        "type": transaction_type(text),
        "category": categorize(text, categories),
        "ok": amount is not None,
    }
