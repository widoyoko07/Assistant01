"""K8g/K8h: teks balasan /saldo dan /rekap dari baris buku besar (lihat ledger.py)."""
from collections import defaultdict
from datetime import timedelta

TRANSFER = "Pindah Kas"
PERIODS = {"hari": "hari ini", "minggu": "minggu ini", "bulan": "bulan ini"}


def rp(n):
    n = round(n)
    return ("-" if n < 0 else "") + "Rp" + f"{abs(n):,}".replace(",", ".")


def _note(pending):
    return f"\n(termasuk {pending} entri yang belum masuk Excel)" if pending else ""


def saldo_text(rows, pending, accounts, arg, today):
    bal = defaultdict(float)
    for r in rows:
        bal[r["account"].lower()] += r["credit"] - r["debit"]
    names = {a.lower(): a for a in accounts or []}
    for r in rows:
        names.setdefault(r["account"].lower(), r["account"])
    arg = arg.strip()
    if arg:
        key = arg.lower()
        if key not in names:
            return "Akun tidak dikenal. Akun: " + ", ".join(sorted(names.values(), key=str.lower))
        last = [r for r in rows if r["account"].lower() == key][-5:]
        lines = [f"Saldo {names[key]}: {rp(bal[key])}", "5 mutasi terakhir:"]
        lines += [f"{r['date']} {rp(r['credit'] - r['debit'])} {r['desc']}" for r in reversed(last)]
        return "\n".join(lines) + _note(pending)
    shown = sorted(((names[k], v) for k, v in bal.items() if round(v)), key=lambda x: -x[1])
    if not shown:
        return "Semua saldo Rp0."
    lines = [f"SALDO per {today}"] + [f"{n}: {rp(v)}" for n, v in shown]
    lines.append(f"Total: {rp(sum(v for _, v in shown))}")
    zero = [n for k, n in names.items() if not round(bal.get(k, 0))]
    if zero:
        lines.append("Saldo 0: " + ", ".join(sorted(zero, key=str.lower)))
    return "\n".join(lines) + _note(pending)


def period_start(kind, today):
    if kind == "hari":
        return today
    if kind == "minggu":
        return today - timedelta(days=today.weekday())
    return today.replace(day=1)


def rekap_text(rows, pending, arg, today):
    kind = (arg.strip().lower().removesuffix(" ini") or "bulan")
    if kind not in PERIODS:
        return "Pakai: /rekap [hari|minggu|bulan], mis. /rekap minggu"
    start = period_start(kind, today)
    sel = [r for r in rows if start <= r["date"] <= today and r["sub"] != TRANSFER and r["ctype"] != "Not Reported"]
    if not sel:
        return f"REKAP {PERIODS[kind]} ({start} s/d {today})\nBelum ada transaksi." + _note(pending)
    income, spend = sum(r["credit"] for r in sel), sum(r["debit"] for r in sel)
    cats = defaultdict(float)
    for r in sel:
        cats[r["sub"] or "(tanpa kategori)"] += r["debit"]
    top = sorted(((c, v) for c, v in cats.items() if v > 0), key=lambda x: -x[1])[:5]
    lines = [f"REKAP {PERIODS[kind]} ({start} s/d {today}, {len(sel)} transaksi, tanpa pindah kas)",
             f"Masuk: {rp(income)}", f"Keluar: {rp(spend)}", f"Selisih: {rp(income - spend)}"]
    if top:
        lines.append("Pengeluaran terbesar:")
        lines += [f"{i}. {c}: {rp(v)} ({v / spend:.0%})" for i, (c, v) in enumerate(top, 1)]
    return "\n".join(lines) + _note(pending)
