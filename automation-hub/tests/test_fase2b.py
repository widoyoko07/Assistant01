import tempfile
import unittest
from datetime import date
from pathlib import Path

from automation_hub.pribadi import ledger
from automation_hub.pribadi.entries import Queue, handle_message
from automation_hub.pribadi.report import period_start, rekap_text, rp, saldo_text

TS = 1_793_500_000  # 2026-11-01/02 Asia/Jakarta
ACC = ["Cash", "JAGO", "Gopay"]
TODAY = date(2026, 11, 4)  # Rabu


def row(d, acc, debit=0, credit=0, sub="Jalan Makan", ctype="Expense"):
    return {"date": d, "account": acc, "desc": "x", "debit": debit, "credit": credit, "sub": sub, "ctype": ctype}


ROWS = [
    row(date(2026, 10, 30), "JAGO", credit=1_000_000, sub="Lainnya", ctype="Income"),
    row(date(2026, 11, 2), "JAGO", debit=40_000),
    row(date(2026, 11, 3), "Cash", debit=10_000, sub="Transportasi"),
    row(date(2026, 11, 3), "JAGO", debit=200_000, sub="Pindah Kas", ctype="Not Reported"),
    row(date(2026, 11, 3), "Cash", credit=200_000, sub="Pindah Kas", ctype="Not Reported"),
    row(date(2026, 11, 4), "cash", debit=5_000),  # beda huruf besar/kecil = akun yang sama
]


class ReportTest(unittest.TestCase):
    def test_rupiah_negative(self):
        self.assertEqual((rp(1234567), rp(-48500), rp(0.4)), ("Rp1.234.567", "-Rp48.500", "Rp0"))

    def test_saldo_all_accounts(self):
        out = saldo_text(ROWS, 0, ACC, "", TODAY)
        self.assertIn("JAGO: Rp760.000", out)
        self.assertIn("Cash: Rp185.000", out)
        self.assertIn("Total: Rp945.000", out)
        self.assertIn("Saldo 0: Gopay", out)
        self.assertNotIn("belum masuk Excel", out)

    def test_saldo_one_account_and_unknown(self):
        out = saldo_text(ROWS, 2, ACC, "jago", TODAY)
        self.assertTrue(out.startswith("Saldo JAGO: Rp760.000"))
        self.assertIn("(termasuk 2 entri yang belum masuk Excel)", out)
        self.assertIn("Akun tidak dikenal", saldo_text(ROWS, 0, ACC, "bca", TODAY))

    def test_periods(self):
        self.assertEqual(period_start("minggu", TODAY), date(2026, 11, 2))
        self.assertEqual(period_start("bulan", TODAY), date(2026, 11, 1))

    def test_rekap_skips_transfers(self):
        out = rekap_text(ROWS, 0, "bulan", TODAY)
        self.assertIn("Keluar: Rp55.000", out)
        self.assertIn("Masuk: Rp0", out)
        self.assertIn("1. Jalan Makan: Rp45.000 (82%)", out)
        self.assertIn("2. Transportasi: Rp10.000 (18%)", out)

    def test_rekap_default_and_invalid(self):
        self.assertIn("bulan ini", rekap_text(ROWS, 0, "", TODAY))
        self.assertIn("hari ini", rekap_text(ROWS, 0, "hari ini", TODAY))
        self.assertIn("Pakai: /rekap", rekap_text(ROWS, 0, "tahun", TODAY))
        self.assertIn("Belum ada transaksi", rekap_text([], 0, "hari", TODAY))


class HandleTest(unittest.TestCase):
    def setUp(self):
        self.q = Queue(Path(tempfile.mkdtemp()) / "queue.jsonl")

    def test_without_ledger(self):
        self.assertIn("butuh file Excel", handle_message("/saldo", TS, 1, {}, self.q, ACC))

    def test_with_ledger_and_error(self):
        out = handle_message("/saldo cash", TS, 1, {}, self.q, ACC, ledger=lambda: (ROWS, 0))
        self.assertIn("Saldo Cash", out)
        def boom():
            raise PermissionError("terkunci")
        self.assertIn("tidak bisa dibaca", handle_message("/rekap", TS, 1, {}, self.q, ACC, ledger=boom))

    def test_help_lists_new_commands(self):
        out = handle_message("/bantuan", TS, 1, {}, self.q, ACC)
        self.assertIn("/saldo", out)
        self.assertIn("/rekap", out)


class LedgerTest(unittest.TestCase):
    def test_pending_from_inbox_and_queue_dedup(self):
        d = Path(tempfile.mkdtemp())
        tsv = d / "Inbox.tsv"
        tsv.write_text("ID\tDate\tAccount\tDescription\tDebit (Spend)\tCredit (Income)\tSubcategory\tAdded By\r\n"
                       "aaa\t2026-11-02\tCash\tparkir\t5000\t0\tTransportasi\t1\r\n"
                       "bbb\t2026-11-02\tCash\tkopi\t7000\t0\tJalan Makan\t1\r\n", encoding="utf-8")
        inbox = ledger.read_inbox(tsv)
        self.assertEqual(set(inbox), {"aaa", "bbb"})
        self.assertEqual(inbox["aaa"]["debit"], 5000)
        e = {"ts": "2026-11-02T10:00:00+07:00", "date": "2026-11-02", "type": "pengeluaran", "category": "BBM Motor",
             "account": "Cash", "amount": 50_000, "note": "bensin", "sender": 1}
        r = ledger.from_entry(e)
        self.assertEqual((r["debit"], r["credit"], r["date"]), (50_000, 0, date(2026, 11, 2)))

    def test_missing_inbox_is_empty(self):
        self.assertEqual(ledger.read_inbox("/tidak/ada.tsv"), {})


if __name__ == "__main__":
    unittest.main()
