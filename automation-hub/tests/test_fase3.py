import tempfile
import unittest
import zipfile
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from automation_hub.common import config
from automation_hub.pribadi import fuel, inbox, ledger, listrik
from automation_hub.pribadi.entries import Ctx, Queue, handle_message
from automation_hub.pribadi.sync import entry_id

TZ = ZoneInfo("Asia/Jakarta")
TS = int(datetime(2026, 11, 7, 9, 0, tzinfo=TZ).timestamp())
CFG = config.load()
PR = CFG["pribadi"]
CATS, ACC = CFG["categories"], CFG["accounts"]
MOTORS = PR["bbm"]["motors"]


def fill(d, liter, km, motor="Supra", seq=0):
    return {"date": d, "motor": motor, "liter": liter, "km": km, "row": seq, "seq": seq}


class FakeTables:
    def __init__(self, bbm=None, listrik=None):
        self._bbm, self._listrik = bbm or [], listrik or []

    def bbm(self):
        return self._bbm

    def listrik(self):
        return self._listrik


def run(text, tables=None, ts=TS):
    q = Queue(Path(tempfile.mkdtemp()) / "queue.jsonl")
    ctx = Ctx(PR, tables or FakeTables())
    return handle_message(text, ts, 1, CATS, q, ACC, None, None, ctx), q


class ExtractTest(unittest.TestCase):
    def test_full_message(self):
        info, rest = fuel.extract("Jago BP 92 Supra 40rb 3.05L km39200.1", MOTORS)
        self.assertEqual((info["motor"], info["liter"], info["km"]), ("Supra", 3.05, 39200.1))
        self.assertEqual(rest, "Jago BP 92 Supra 40rb")

    def test_harsat_and_thousands(self):
        info, _ = fuel.extract("cash bensin vario 50rb @16.130 km 50.320,5", MOTORS)
        self.assertEqual((info["harsat"], info["km"]), (16130, 50320.5))
        info, _ = fuel.extract("bensin supra 40rb 2.728 liter harsat 16130 km39200", MOTORS)
        self.assertEqual((info["liter"], info["harsat"]), (2.728, 16130))

    def test_not_fuel_untouched(self):
        text = "beli 2 liter minyak goreng 30rb"
        self.assertEqual(fuel.extract(text, MOTORS), (None, text))
        text = "servis supra 150rb km 32000"
        self.assertEqual(fuel.extract(text, MOTORS), (None, text))

    def test_finish(self):
        info, _ = fuel.extract("bensin supra 44003 2.728L km32784.4", MOTORS)
        b = fuel.finish(info, 44003)
        self.assertEqual((b["harsat"], b["liter"]), (16130, 2.728))
        info, _ = fuel.extract("bensin supra 44003 harsat 16130 km32784.4", MOTORS)
        self.assertEqual(fuel.finish(info, 44003)["liter"], 2.728)
        info, _ = fuel.extract("bensin supra 44003 2.728L", MOTORS)
        with self.assertRaisesRegex(fuel.FuelError, "perlu km"):
            fuel.finish(info, 44003)
        info, _ = fuel.extract("bensin supra 44003 km32784.4", MOTORS)
        with self.assertRaisesRegex(fuel.FuelError, "perlu liter"):
            fuel.finish(info, 44003)
        info, _ = fuel.extract("bensin ertiga 50rb", MOTORS)
        self.assertIsNone(fuel.finish(info, 50000))


class AnalyzeTest(unittest.TestCase):
    def rows(self):
        # isian tiap 2 hari ~150 km @ 3 L (50 km/L); satu km salah ketik dan satu isian kecil
        out, km = [], 30000.0
        for i in range(20):
            km += 150
            out.append(fill(date(2026, 10, 1 + i), 3.0, km, seq=i))
        out[10]["km"] = 300075.5   # salah ketik
        out[14]["liter"] = 1.0     # isian kecil
        return out

    def test_outlier_dropped_and_cumulative(self):
        st = fuel.analyze(self.rows(), window_fills=30, tank=3.7)
        self.assertEqual([p["km"] for p in st["skipped"]], [300075.5])
        self.assertAlmostEqual(st["km_per_l"], 2850 / 55, places=3)   # 19 segmen x 150 km; liter 19x3 - 2 (isian kecil)
        self.assertLess(st["low"], st["high"])
        self.assertAlmostEqual(st["high"], st["last_km"] + st["tank"] * st["km_per_l"])

    def test_window_counts_fills(self):
        rows = [fill(date(2026, 9, 1) + __import__("datetime").timedelta(days=7 * i), 3.0 + (i % 2) * 0.4, 40000 + 150 * i, "Vario", i) for i in range(10)]
        st = fuel.analyze(rows, window_fills=4)
        self.assertEqual((st["fills"], st["short"]), (4, False))
        self.assertEqual(st["from"], rows[5]["date"])           # titik dasar = satu sebelum 4 isian terakhir
        st = fuel.analyze(rows, window_fills=30)
        self.assertEqual((st["fills"], st["short"]), (9, True))  # data kurang dari jendela: semua dipakai
        self.assertIsNone(fuel.analyze(rows[:1]))

    def test_check_km(self):
        rows = [fill(date(2026, 11, 1), 3.0, 1000.0 + 150 * i, seq=i) for i in range(1, 6)]
        self.assertIsNone(fuel.check_km(1900.0, date(2026, 11, 7), rows, 1000))
        self.assertIn("tidak lebih besar", fuel.check_km(1500.0, date(2026, 11, 7), rows, 1000))
        self.assertIn("terlalu jauh", fuel.check_km(300075.5, date(2026, 11, 7), rows, 1000))
        self.assertIsNone(fuel.check_km(5.0, date(2026, 10, 1), rows, 1000))  # isian lama tidak dicek


class BbmMessageTest(unittest.TestCase):
    def history(self):
        return [fill(date(2026, 11, 2), 3.0, 39000.0, seq=1), fill(date(2026, 11, 4), 3.0, 39150.0, seq=2)]

    def test_motor_entry_goes_to_both_tables(self):
        out, q = run("Jago BP 92 Supra 40rb 3.05L km39200.1", FakeTables(self.history()))
        (e,) = q.all()
        self.assertEqual((e["category"], e["account"], e["amount"], e["note"]), ("BBM Motor", "JAGO", 40000, "BP 92 Supra"))
        self.assertEqual(e["bbm"], {"motor": "Supra", "liter": 3.05, "harsat": 13115, "km": 39200.1})
        self.assertIn("Supra: 3,05 L @Rp13.115", out)
        self.assertIn("km 39.200,1", out)

    def test_other_vehicle_is_bbm_lainnya_without_table_row(self):
        out, q = run("cash bensin pertalite ertiga 50rb")
        (e,) = q.all()
        self.assertEqual(e["category"], "BBM Lainnya")
        self.assertNotIn("bbm", e)

    def test_amount_liter_harsat_must_agree(self):
        t = FakeTables(self.history())
        out, q = run("jago BP 92 Supra 40rb 3.05L km39200.1 @16130", t)   # contoh salah: 3,05 L x 16.130 = 49.197
        self.assertIn("nominal tidak cocok", out)
        self.assertEqual(q.all(), [])
        out, q = run("jago BP 92 Supra 40rb 2.48L km39200.1 @16130 paksa", t)
        self.assertEqual(len(q.all()), 1)
        out, q = run("jago BP 92 Supra 40rb 2.48L km39150.5 @16130", t)
        self.assertEqual(q.all()[0]["bbm"]["harsat"], 16130)
        out, q = run("jago BP 92 Supra 40rb @16130 km39150.5", t)       # liter dihitung dari nominal / harsat
        self.assertEqual(q.all()[0]["bbm"]["liter"], 2.48)

    def test_missing_km_or_liter_not_recorded(self):
        out, q = run("jago bensin vario 30rb 2.5L")
        self.assertIn("perlu km", out)
        self.assertEqual(q.all(), [])
        out, q = run("jago bensin vario 30rb km50400")
        self.assertIn("perlu liter", out)

    def test_bad_km_rejected_unless_forced(self):
        t = FakeTables(self.history())
        out, q = run("jago bensin supra 40rb 3L km300075.5", t)
        self.assertIn("terlalu jauh", out)
        self.assertEqual(q.all(), [])
        out, q = run("jago bensin supra 40rb 3L km300075.5 paksa", t)
        self.assertEqual(len(q.all()), 1)
        self.assertNotIn("paksa", q.all()[0]["note"])

    def test_other_motor_history_not_mixed(self):
        t = FakeTables(self.history() + [fill(date(2026, 10, 30), 3.0, 50320.0, "Vario", 3)])
        out, q = run("jago bensin vario 40rb 3L km50470", t)
        self.assertEqual(len(q.all()), 1, out)

    def test_without_ctx_old_behaviour(self):
        q = Queue(Path(tempfile.mkdtemp()) / "queue.jsonl")
        handle_message("cash bensin supra 40rb", TS, 1, CATS, q, ACC)
        self.assertNotIn("bbm", q.all()[0])

    def test_multiline_mixed(self):
        out, q = run("kemarin\njago bensin supra 40rb 3L km39200\ncash parkir 5rb", FakeTables(self.history()))
        self.assertIn("Tercatat 2 dari 2", out)
        self.assertEqual([bool(e.get("bbm")) for e in q.all()], [True, False])


class BbmCommandTest(unittest.TestCase):
    def rows(self):
        out = []
        for i in range(12):
            out.append(fill(date(2026, 10, 10) + __import__("datetime").timedelta(days=2 * i), 3.0, 32000.0 + 150 * i, "Supra", i))
        for i in range(5):
            out.append(fill(date(2026, 10, 1) + __import__("datetime").timedelta(days=7 * i), 3.6 if i == 2 else 3.0, 50000.0 + 150 * i, "Vario", 100 + i))
        return out

    def test_both_motors_with_model_and_plate(self):
        out, _ = run("/bbm", FakeTables(self.rows()))
        self.assertIn("SUPRA X 125 (B 3132 KGW)", out)
        self.assertIn("VARIO 110 (B 4807 KBK)", out)
        self.assertIn("Perkiraan habis saat km", out)

    def test_km_picks_motor_and_shows_remaining(self):
        out, _ = run("/bbm 33700", FakeTables(self.rows()))
        self.assertIn("SUPRA", out)
        self.assertNotIn("VARIO", out)
        self.assertIn("Dari km 33.700,0", out)
        out, _ = run("/bbm vario 50800", FakeTables(self.rows()))
        self.assertIn("VARIO", out)
        self.assertIn("melewati", out)

    def test_bad_arg_and_no_tables(self):
        self.assertIn("Pakai: /bbm", run("/bbm abc", FakeTables(self.rows()))[0])
        q = Queue(Path(tempfile.mkdtemp()) / "queue.jsonl")
        self.assertIn("butuh file Excel", handle_message("/bbm", TS, 1, CATS, q, ACC, None, None, Ctx(PR, None)))


def rd(t, sisa):
    return {"t": t, "sisa": sisa, "topup": None}


class ListrikTest(unittest.TestCase):
    def test_rates_like_table(self):
        r = [rd(datetime(2025, 10, 4, 12, 0), 80.64)]
        r.append(rd(datetime(2025, 10, 5, 7, 8) , 76.97))
        r.append(rd(datetime(2025, 10, 8, 21, 3), 52.62))
        rates = listrik.rates(r)
        self.assertEqual([x for _, x in rates], [round(3.67 / 19, 3), round(24.35 / 86, 3)])

    def test_topup_interval_has_no_rate(self):
        r = [rd(datetime(2026, 1, 1, 0, 0), 10.0), rd(datetime(2026, 1, 1, 0, 2), 138.0), rd(datetime(2026, 1, 2, 0, 0), 120.0)]
        self.assertEqual(len(listrik.rates(r)), 1)

    def test_estimate_formula(self):
        r = [rd(datetime(2026, 1, 1, 0, 0), 100.0), rd(datetime(2026, 1, 2, 0, 0), 90.0)]   # 10 kWh / 24 jam
        est = listrik.estimate(r)
        self.assertEqual(est["rate"], 0.417)   # 10/24 dibulatkan 3 desimal per interval, seperti kolom kWh/Jam
        self.assertEqual(est["t_zero"], datetime(2026, 1, 2) + __import__("datetime").timedelta(hours=round(90 / 0.417, 2)))
        est = listrik.estimate(r, sisa=50.0, now=datetime(2026, 1, 5, 12, 0))
        self.assertEqual(est["base_t"], datetime(2026, 1, 5, 12, 0))
        self.assertLess(est["t_low"], est["t_zero"])
        self.assertIsNone(listrik.estimate(r[:1]))

    def test_window_days_limits_intervals(self):
        r = [rd(datetime(2026, 1, 1), 100.0), rd(datetime(2026, 1, 2), 90.0), rd(datetime(2026, 3, 1), 80.0), rd(datetime(2026, 3, 2), 60.0)]
        self.assertEqual(listrik.estimate(r)["n"], 3)
        self.assertEqual(listrik.estimate(r, window_days=10)["n"], 2)

    def test_parse(self):
        self.assertEqual(listrik.parse_reading("meter 95,3"), 95.3)
        self.assertEqual(listrik.parse_reading("kwh 95.3"), 95.3)
        self.assertIsNone(listrik.parse_reading("token listrik 95rb"))
        self.assertEqual(listrik.extract_time("meter 95,3 jam 5.48"), ((5, 48), "meter 95,3"))
        info, rest = listrik.extract_topup("jago token listrik 201rb 128,2kwh meter 141,14")
        self.assertEqual((info["topup"], info["sisa"], rest), (128.2, 141.14, "jago token listrik 201rb"))
        with self.assertRaises(listrik.ListrikError):
            listrik.extract_topup("jago token listrik 201rb 128,2kwh")
        self.assertEqual(listrik.extract_topup("jago token listrik 201rb"), (None, "jago token listrik 201rb"))


class ListrikMessageTest(unittest.TestCase):
    READINGS = [rd(datetime(2026, 11, 1, 6, 0), 150.0), rd(datetime(2026, 11, 3, 6, 0), 120.0)]

    def test_reading_only(self):
        out, q = run("meter 95,3", FakeTables(listrik=self.READINGS))
        (e,) = q.all()
        self.assertEqual((e["kind"], e["listrik"]), ("meter", {"t": "2026-11-07T09:00", "topup": None, "sisa": 95.3}))
        self.assertTrue(out.startswith("Tercatat meter 7 Nov 09:00: 95,3 kWh"))
        self.assertIn("Sisa 20 kWh", out)

    def test_reading_with_time_and_date(self):
        _, q = run("kemarin meter 95,3 jam 20.15")
        self.assertEqual(q.all()[0]["listrik"]["t"], "2026-11-06T20:15")
        self.assertEqual(q.all()[0]["date"], "2026-11-06")

    def test_future_time_rejected(self):
        out, q = run("meter 95,3 jam 23.00")
        self.assertIn("belum terjadi", out)
        self.assertEqual(q.all(), [])

    def test_token_with_meter_goes_to_both(self):
        out, q = run("jago token listrik 201rb 128,2kwh meter 141,14")
        (e,) = q.all()
        self.assertEqual((e["category"], e["amount"], e["listrik"]["topup"], e["listrik"]["sisa"]), ("Listrik", 201000, 128.2, 141.14))
        self.assertIn("Meter 141,14 kWh", out)

    def test_token_without_meter_unchanged(self):
        _, q = run("jago token listrik 201rb")
        self.assertNotIn("listrik", q.all()[0])

    def test_jam_elsewhere_not_touched(self):
        _, q = run("cash parkir jam 5.30 5rb")
        self.assertIn("jam 5.30", q.all()[0]["note"])

    def test_listrik_command(self):
        out, _ = run("/listrik", FakeTables(listrik=self.READINGS))
        self.assertIn("bacaan terakhir 3 Nov 06:00: 120 kWh", out)
        self.assertIn("Sisa 0 kWh", out)
        out, _ = run("/listrik 95,3", FakeTables(listrik=self.READINGS))
        self.assertIn("tidak disimpan", out)

    def test_terakhir_and_cek_with_meter(self):
        q = Queue(Path(tempfile.mkdtemp()) / "queue.jsonl")
        ctx = Ctx(PR, FakeTables())
        handle_message("meter 95,3", TS, 1, CATS, q, ACC, None, None, ctx)
        self.assertIn("meter 95,3 kWh", handle_message("/terakhir", TS, 1, CATS, q, ACC, None, None, ctx))
        res = handle_message("/cek meter 80", TS, 1, CATS, q, ACC, None, None, ctx)
        self.assertTrue(res.startswith("SIMULASI"))
        self.assertEqual(len(q.all()), 1)


class InboxFilesTest(unittest.TestCase):
    def test_three_files(self):
        d = Path(tempfile.mkdtemp())
        _, q = run("jago BP 92 Supra 40rb 3.05L km39200.1")
        bbm = q.all()[0]
        _, q2 = run("meter 95,3")
        meter = q2.all()[0]
        _, q3 = run("cash parkir 5rb")
        plain = q3.all()[0]
        inbox.append_entries(d / "Inbox Transaksi.tsv", [bbm, meter, plain], d / "Inbox BBM.tsv", d / "Inbox Listrik.tsv")
        trx = (d / "Inbox Transaksi.tsv").read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(trx), 3)  # header + bbm + plain; meter bukan transaksi
        b = (d / "Inbox BBM.tsv").read_text(encoding="utf-8").splitlines()
        self.assertEqual(b[0].split("\t"), inbox.HEADER_BBM)
        self.assertEqual(b[1].split("\t"), [entry_id(bbm) + "b", bbm["date"], "BBM Motor", "40000", "JAGO", "BP 92 Supra", "3.05", "13115", "39200.1"])
        li = (d / "Inbox Listrik.tsv").read_text(encoding="utf-8").splitlines()
        self.assertEqual(li[1].split("\t"), [entry_id(meter) + "l", "2026-11-07 09:00", "", "95.3"])
        self.assertEqual(ledger.read_tsv(d / "Inbox BBM.tsv")[entry_id(bbm) + "b"][8], "39200.1")

    def test_ids_differ_and_old_ids_unchanged(self):
        a = {"ts": "t", "sender": 1, "account": "Cash", "type": "pengeluaran", "amount": 5, "category": "x", "note": "n"}
        base = entry_id(a)
        self.assertEqual(entry_id(dict(a)), base)
        self.assertNotEqual(entry_id(dict(a, bbm={"km": 1})), base)


def build_xlsx(path, bbm_rows, listrik_rows, subs=(("Variable", "Indihome", "Expense"), ("Variable", "Pajak RIBA", "Expense"), ("Variable", "RIBA", "Expense"))):
    """xlsx minimal: sheet BBM dengan tabel _bbmmotor (C10:J..) dan sheet Listrik dengan tabel _listrik (B10:E..) + inbox_log."""
    ns = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
    strings = []

    def sst(s):
        if s not in strings:
            strings.append(s)
        return strings.index(s)

    def sheet(rows):
        out = []
        for r, cells in rows:
            cs = "".join(f'<c r="{ref}" t="s"><v>{sst(v)}</v></c>' if isinstance(v, str) else f'<c r="{ref}"><v>{v}</v></c>' for ref, v in cells)
            out.append(f'<row r="{r}">{cs}</row>')
        return f'<worksheet {ns}><sheetData>{"".join(out)}</sheetData></worksheet>'

    bh = ["TANGGAL", "SUB KATEGORI", "UANG KELUAR", "POSISI KAS", "KETERANGAN", "LITER", "HARSAT", "KM"]
    b_rows = [(10, [(f"{chr(67 + i)}10", h) for i, h in enumerate(bh)])]
    for n, row in enumerate(bbm_rows, 11):
        b_rows.append((n, [(f"{chr(67 + i)}{n}", v) for i, v in enumerate(row) if v is not None]))
    lh = ["Waktu", "kWH Topup", "kWH Sisa", "Selisih kWH"]
    l_rows = [(10, [(f"{chr(66 + i)}10", h) for i, h in enumerate(lh)])]
    for n, row in enumerate(listrik_rows, 11):
        l_rows.append((n, [(f"{chr(66 + i)}{n}", v) for i, v in enumerate(row) if v is not None]))
    log_rows = [(1, [("A1", "ID")]), (2, [("A2", "idsudah1b")])]
    ch = ["Category", "Subcategory", "Category Type"]
    c_rows = [(2, [(f"{chr(66 + i)}2", h) for i, h in enumerate(ch)])]
    for n, row in enumerate(subs, 3):
        c_rows.append((n, [(f"{chr(66 + i)}{n}", v) for i, v in enumerate(row)]))
    parts = {
        "xl/workbook.xml": f'<workbook {ns} xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'
                           '<sheet name="BBM" sheetId="1" r:id="rId1"/><sheet name="Listrik" sheetId="2" r:id="rId2"/>'
                           '<sheet name="inbox_log" sheetId="3" state="veryHidden" r:id="rId3"/><sheet name="02.category" sheetId="4" r:id="rId4"/></sheets></workbook>',
        "xl/_rels/workbook.xml.rels": '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                                      + "".join(f'<Relationship Id="rId{i}" Target="worksheets/sheet{i}.xml"/>' for i in (1, 2, 3, 4)) + "</Relationships>",
        "xl/worksheets/sheet1.xml": sheet(b_rows),
        "xl/worksheets/sheet2.xml": sheet(l_rows),
        "xl/worksheets/sheet3.xml": sheet(log_rows),
        "xl/worksheets/sheet4.xml": sheet(c_rows),
        "xl/tables/table3.xml": f'<table {ns} displayName="_catagories" ref="B2:D{2 + len(subs)}"><tableColumns count="3">'
                                + "".join(f'<tableColumn name="{h}"/>' for h in ch) + "</tableColumns></table>",
        "xl/tables/table1.xml": f'<table {ns} displayName="_bbmmotor" ref="C10:J{10 + len(bbm_rows)}"><tableColumns count="8">'
                                + "".join(f'<tableColumn name="{h}"/>' for h in bh) + "</tableColumns></table>",
        "xl/tables/table2.xml": f'<table {ns} displayName="_listrik" ref="B10:E{10 + len(listrik_rows)}"><tableColumns count="4">'
                                + "".join(f'<tableColumn name="{h}"/>' for h in lh) + "</tableColumns></table>",
    }
    parts["xl/sharedStrings.xml"] = f'<sst {ns}>' + "".join(f"<si><t>{s}</t></si>" for s in strings) + "</sst>"
    with zipfile.ZipFile(path, "w") as z:
        for k, v in parts.items():
            z.writestr(k, v)


SUBS = ["Indihome", "PDAM", "Jalan Makan", "Pajak RIBA", "RIBA", "Listrik", "Liburan", "Parkir"]


class SubTables(FakeTables):
    def subcategories(self):
        return SUBS


class SubcategoryTest(unittest.TestCase):
    def test_split(self):
        from automation_hub.pribadi.entries import split_subcategory as sp
        self.assertEqual(sp("internet magnolia Indihome", SUBS), ("Indihome", "internet magnolia"))
        self.assertEqual(sp("bulan Nov-26 pdam", SUBS), ("PDAM", "bulan Nov-26"))         # huruf kecil -> nama asli
        self.assertEqual(sp("bayar Pajak RIBA", SUBS), ("Pajak RIBA", "bayar"))           # yang terpanjang dulu
        self.assertEqual(sp("kopi susu jalan makan", SUBS), ("Jalan Makan", "kopi susu"))
        self.assertEqual(sp("Indihome", SUBS), (None, "Indihome"))                         # keterangan tidak boleh kosong
        self.assertEqual(sp("parkir motor", SUBS), (None, "parkir motor"))                 # hanya di akhir
        self.assertEqual(sp("tiket pesawat", SUBS), (None, "tiket pesawat"))
        self.assertEqual(sp("service ribas", SUBS), (None, "service ribas"))               # kata utuh

    def test_message_uses_and_strips_subcategory(self):
        out, q = run("jago internet magnolia 311575 Indihome", SubTables())
        (e,) = q.all()
        self.assertEqual((e["category"], e["note"], e["amount"]), ("Indihome", "internet magnolia", 311575))
        self.assertIn("[Indihome] - internet magnolia", out)

    def test_subcategory_before_amount_and_with_date(self):
        _, q = run("kemarin jago bulan Nov-26 PDAM 228300", SubTables())
        self.assertEqual((q.all()[0]["category"], q.all()[0]["note"], q.all()[0]["date"]), ("PDAM", "bulan Nov-26", "2026-11-06"))

    def test_subcategory_not_in_config_keywords(self):
        _, q = run("jago tiket pesawat 900rb Liburan", SubTables())
        self.assertEqual(q.all()[0]["category"], "Liburan")

    def test_without_subcategory_auto_classification_kept(self):
        _, q = run("cash parkir 5rb", SubTables())
        self.assertEqual((q.all()[0]["category"], q.all()[0]["note"]), ("Transportasi", "parkir"))

    def test_falls_back_to_config_keys_without_tables(self):
        _, q = run("jago internet magnolia 311575 Indihome", None)
        self.assertEqual((q.all()[0]["category"], q.all()[0]["note"]), ("Indihome", "internet magnolia"))


class TablesTest(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())
        serial = (date(2026, 11, 4) - ledger.EPOCH).days
        build_xlsx(self.d / "book.xlsx",
                   [[serial, "BBM Motor", 44003, "JAGO", "Bensin BP 92 Supra", 2.728, 16130, 32784.4],
                    [serial, "BBM Motor", 40000, "Cash", "Bensin Ertiga", None, None, None]],
                   [[46329.2403, None, 12.96], [46329.2417, 128.2, 141.14]])
        self.q = Queue(self.d / "queue.jsonl")
        self.t = ledger.Tables(self.d / "book.xlsx", self.d, PR, self.q)

    def test_reads_tables_by_definition(self):
        rows = self.t.bbm()
        self.assertEqual((rows[0]["motor"], rows[0]["km"], rows[0]["row"], rows[0]["date"]), ("Supra", 32784.4, 11, date(2026, 11, 4)))
        self.assertIsNone(rows[1]["motor"])
        li = self.t.listrik()
        self.assertEqual([x["sisa"] for x in li], [12.96, 141.14])
        self.assertEqual(li[1]["topup"], 128.2)
        self.assertEqual(li[1]["t"].year, 2026)

    def test_subcategories_from_table_cached_by_mtime(self):
        self.assertEqual(self.t.subcategories(), ["Indihome", "Pajak RIBA", "RIBA"])
        self.assertIs(self.t.subcategories(), self.t.subcategories())

    def test_pending_from_tsv_and_queue_not_duplicated(self):
        _, q = run("jago BP 92 Supra 40rb 3.05L km32900.1", self.t)
        e = q.all()[0]
        self.q.add(e)
        self.assertEqual(self.t.bbm()[-1]["km"], 32900.1)         # dari antrean
        inbox.append_entries(self.d / "t.tsv", [e], self.d / PR["inbox_bbm_file"], self.d / PR["inbox_listrik_file"])
        self.q.clear(1)
        self.assertEqual(self.t.bbm()[-1]["km"], 32900.1)         # dari TSV
        self.assertEqual(len(self.t.bbm()), 3)
        self.q.add(e)
        self.assertEqual(len(self.t.bbm()), 3)                    # antrean + TSV = satu baris


if __name__ == "__main__":
    unittest.main()
