"""K8g/K8h: teks balasan /saldo dan /rekap dari baris buku besar (lihat ledger.py)."""
from collections import defaultdict
from datetime import timedelta

from . import fuel, listrik
from .fuel import fmt_km
from .listrik import dec, fmt_kwh, fmt_time

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


MON = listrik.MONTHS


def _day(d):
    return f"{d.day} {MON[d.month - 1]}"


def _pick_motor(motors, toks, km, stats, jump):
    """Nama motor dari kata di perintah, atau dari km (motor yang km terakhirnya tepat di bawahnya); None bila tak jelas."""
    named = [m for m in motors if m.lower() in toks]
    if named:
        return named[0]
    if km is None:
        return None
    near = [m for m, st in stats.items() if st and st["last_km"] <= km <= st["last_km"] + jump]
    return near[0] if len(near) == 1 else None


def bbm_text(rows, cfg, arg, today):
    """/bbm [motor] [km sekarang]: kisaran km saat bensin habis per motor, dari window_fills isian terakhir."""
    motors = cfg["motors"]
    toks = arg.lower().replace("km", " ").split()
    km = None
    for t in toks:
        if t not in {m.lower() for m in motors}:
            try:
                km = fuel._thousands(t)
            except ValueError:
                return "Pakai: /bbm [supra|vario] [km sekarang], mis. /bbm supra 32900"
    stats = {m: fuel.analyze([r for r in rows if r["motor"] == m], cfg.get("window_fills", 12), (motors[m] or {}).get("tank")) for m in motors}
    chosen = _pick_motor(motors, toks, km, stats, 1500)
    if km is not None and chosen is None:
        return f"Motor tidak jelas dari km itu. Tulis motornya, mis. /bbm {next(iter(motors)).lower()} {fmt_km(km)}"
    blocks = []
    for m in ([chosen] if chosen else motors):
        info = motors[m] or {}
        head = f"{info.get('model', m.upper())} ({info.get('plat', '-')})"
        st = stats[m]
        if not st:
            blocks.append(f"{head}\nBelum cukup data isian (butuh minimal 2 isian dengan liter dan km).")
            continue
        lines = [head,
                 f"Isi terakhir: km {fmt_km(st['last_km'])} ({_day(st['last_date'])})",
                 f"Rata-rata: {dec(st['km_per_l'], 1)} km/L ({dec(st['l_per_km'], 4)} L/km), {st['fills']} isian terakhir (sejak {_day(st['from'])})"
                 + (f" (baru ada {st['fills']}, belum {cfg.get('window_fills', 12)})" if st["short"] else ""),
                 f"Perkiraan habis saat km {fmt_km(st['low'])}~{fmt_km(st['high'])}"]
        if chosen and km is not None:
            lines.append(_remaining(km, st))
        if st["skipped"]:
            lines.append("Diabaikan (km tidak wajar): " + ", ".join(f"baris {p['row']} ({fmt_km(p['km'])})" if p.get("row") else f"km {fmt_km(p['km'])}" for p in st["skipped"]))
        blocks.append("\n".join(lines))
    return f"BBM per {_day(today)}\n\n" + "\n\n".join(blocks)


def _remaining(km, st):
    if km < st["last_km"]:
        return f"Km {fmt_km(km)} lebih kecil dari km isi terakhir; cek lagi."
    if km >= st["high"]:
        return f"Dari km {fmt_km(km)}: sudah melewati perkiraan, isi bensin sekarang."
    if km >= st["low"]:
        return f"Dari km {fmt_km(km)}: sudah masuk kisaran habis, sisa paling banyak {st['high'] - km:.0f} km."
    return f"Dari km {fmt_km(km)}: sisa sekitar {st['low'] - km:.0f}~{st['high'] - km:.0f} km."


def _in(delta):
    if delta.total_seconds() <= 0:
        return "sudah lewat"
    hours = int(delta.total_seconds() // 3600)
    return f"{hours // 24} hari {hours % 24} jam lagi"


def listrik_text(readings, cfg, arg, now):
    """/listrik [kWh sekarang]: kapan sisa 20 kWh dan 0 kWh. Dengan angka = hitung dari bacaan itu (tidak disimpan)."""
    sisa = None
    if arg.strip():
        try:
            sisa = float(arg.strip().replace(",", "."))
        except ValueError:
            return "Pakai: /listrik [kWh di meter sekarang], mis. /listrik 95,3"
    window = cfg.get("window_days")
    est = listrik.estimate(readings, sisa, now, cfg.get("low_kwh", 20), window)
    if not est:
        return "Belum cukup data bacaan meter untuk menghitung pemakaian."
    low = fmt_kwh(est["low"])
    head = (f"LISTRIK, bacaan Anda sekarang: {fmt_kwh(sisa)} kWh" if sisa is not None
            else f"LISTRIK, bacaan terakhir {fmt_time(est['base_t'], now)}: {fmt_kwh(est['base_sisa'])} kWh")
    lines = [head,
             f"Pemakaian rata-rata {dec(est['rate'], 4)} kWh/jam ({est['n']} interval, " + (f"{window} hari terakhir" if window else "seluruh riwayat") + ")",
             f"Sisa {low} kWh: {fmt_time(est['t_low'], now)} ({_in(est['t_low'] - now)})",
             f"Sisa 0 kWh: {fmt_time(est['t_zero'], now)} ({_in(est['t_zero'] - now)})"]
    if sisa is not None:
        lines.append("Hanya dihitung, tidak disimpan. Simpan dengan: meter " + fmt_kwh(sisa))
    return "\n".join(lines)
