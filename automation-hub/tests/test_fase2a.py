import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from automation_hub.common import config
from automation_hub.pribadi.entries import TZ, Queue, handle_message, make_transfer

CFG = config.load()
CATS, ACC = CFG["categories"], CFG["accounts"]
TS = int(datetime(2026, 11, 2, 9, 0, tzinfo=TZ).timestamp())  # Senin


class Base(unittest.TestCase):
    def setUp(self):
        self.q = Queue(Path(tempfile.mkdtemp()) / "q.jsonl")

    def send(self, text):
        return handle_message(text, TS, 1, CATS, self.q, ACC)


class TransferFormatTest(Base):
    def test_new_order_with_amount_after_words(self):
        pair, att = make_transfer("BSI ke JAGO Pindah kas 2jt", TS, 1, ACC)
        self.assertTrue(att)
        a, b = pair
        self.assertEqual((a["account"], a["type"], a["amount"]), ("BSI", "pengeluaran", 2_000_000))
        self.assertEqual((b["account"], b["type"], b["amount"], b["note"], b["category"]),
                         ("JAGO", "pemasukan", 2_000_000, "Pindah kas", "Pindah Kas"))

    def test_old_order_and_optional_words(self):
        for t in ("pindah kas JAGO ke cash 100rb", "JAGO ke CAsh pindah kas 100rb", "jago ke cash 100rb", "JAGO ke cash 100rb pindah kas"):
            with self.subTest(t=t):
                pair, _ = make_transfer(t, TS, 1, ACC)
                self.assertEqual([(e["account"], e["type"], e["amount"]) for e in pair],
                                 [("JAGO", "pengeluaran", 100_000), ("Cash", "pemasukan", 100_000)])

    def test_multiword_account(self):
        pair, _ = make_transfer("Jago ART ke Kas Profit 50rb", TS, 1, ACC)
        self.assertEqual([e["account"] for e in pair], ["Jago ART", "Kas Profit"])

    def test_invalid_transfer_not_recorded_half(self):
        for t in ("pindah kas BSI ke xyz 100rb", "BSI ke BSI 100rb", "BSI ke JAGO pindah kas", "pindah kas 100rb"):
            with self.subTest(t=t):
                self.assertIn("Pindah kas tidak terbaca", self.send(t))
        self.assertEqual(self.q.all(), [])

    def test_normal_expense_not_mistaken_for_transfer(self):
        self.assertEqual(make_transfer("cash makan ke warung 20rb", TS, 1, ACC), (None, False))

    def test_backdated_transfer_via_handle(self):
        self.send("kemarin BSI ke JAGO pindah kas 2jt")
        self.assertEqual({e["date"] for e in self.q.all()}, {"2026-11-01"})


class MultiLineTest(Base):
    def test_user_example(self):
        out = self.send("cash parkir 2001\ncash cemilan di kantor 5002\njago ART 150001")
        rows = self.q.all()
        self.assertEqual([(r["account"], r["amount"], r["note"]) for r in rows],
                         [("Cash", 2001, "parkir"), ("Cash", 5002, "cemilan di kantor"), ("JAGO", 150001, "ART")])
        self.assertIn("Tercatat 3 dari 3 baris", out)

    def test_account_prefers_shorter_when_longer_leaves_no_description(self):
        self.send("jago ART 150001\nJago ART ke JAGO 50rb\ncash 5rb")
        r = self.q.all()
        self.assertEqual((r[0]["account"], r[0]["note"]), ("JAGO", "ART"))
        self.assertEqual([e["account"] for e in r[1:3]], ["Jago ART", "JAGO"])
        self.assertEqual((r[3]["account"], r[3]["note"]), ("Cash", ""))

    def test_partial_success_reports_failures(self):
        out = self.send("cash parkir 5rb\nparkir 5rb\ncash beli sesuatu\ncash tol 20rb")
        self.assertEqual(len(self.q.all()), 2)
        self.assertIn("Tercatat 2 dari 4 baris", out)
        self.assertIn("GAGAL: parkir 5rb -> akun belum disebut", out)
        self.assertIn("GAGAL: cash beli sesuatu -> nominal tidak terbaca", out)

    def test_date_header_applies_to_all_lines_and_line_date_overrides(self):
        self.send("kemarin\ncash parkir 5rb\ncash tol 20rb 29/10\nBSI ke JAGO pindah kas 1jt")
        self.assertEqual([r["date"] for r in self.q.all()], ["2026-11-01", "2026-10-29", "2026-11-01", "2026-11-01"])

    def test_bullets_and_numbers_stripped_dash_means_expense(self):
        self.send("1. cash parkir 5rb\n- cash tol 20rb\n+ jago gaji 1jt")
        self.assertEqual([(r["note"], r["type"]) for r in self.q.all()],
                         [("parkir", "pengeluaran"), ("tol", "pengeluaran"), ("gaji", "pemasukan")])

    def test_future_date_header_rejected(self):
        self.assertIn("belum terjadi", self.send("29/12\ncash parkir 5rb"))
        self.assertEqual(self.q.all(), [])

    def test_single_line_behaviour_unchanged(self):
        self.assertIn("Tercatat 2026-11-02: Cash pengeluaran Rp5.000", self.send("cash parkir 5rb"))


class CommandTest(Base):
    def test_bantuan_lists_commands_and_accounts(self):
        for c in ("/bantuan", "/help", "/start"):
            out = self.send(c)
            self.assertIn("/cek", out)
            self.assertIn("/terakhir", out)
            self.assertIn("Kas Profit", out)
            self.assertNotIn("/undo", out)

    def test_undo_removed_and_unknown_command(self):
        self.send("cash parkir 5rb")
        self.assertIn("Perintah tidak dikenal", self.send("/undo"))
        self.assertEqual(len(self.q.all()), 1)

    def test_cek_does_not_record(self):
        out = self.send("/cek kemarin cash bensin 50rb")
        self.assertIn("SIMULASI", out)
        self.assertIn("Akan dicatat 2026-11-01", out)
        self.assertIn("BBM Motor", out)
        self.assertEqual(self.q.all(), [])

    def test_cek_multiline_and_errors(self):
        out = self.send("/cek cash parkir 2rb\nparkir 3rb")
        self.assertIn("Tercatat 1 dari 2", out.replace("Akan dicatat", "Tercatat"))
        self.assertEqual(self.q.all(), [])
        self.assertIn("Pakai: /cek", self.send("/cek"))
        self.assertIn("Pakai: /cek", self.send("/cek /terakhir"))

    def test_terakhir_still_works(self):
        self.send("cash parkir 5rb")
        self.assertIn("parkir", self.send("/terakhir"))
        self.assertIn("parkir", self.send("1 terakhir"))


if __name__ == "__main__":
    unittest.main()
