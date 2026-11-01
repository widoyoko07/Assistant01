import tempfile
import unittest
from pathlib import Path

from automation_hub.common import config
from automation_hub.pribadi.entries import Queue, handle_message, make_entry

TS = 1_790_000_000  # 2026-09-21 ~ Asia/Jakarta


class EntriesTest(unittest.TestCase):
    def setUp(self):
        self.cats = config.load()["categories"]
        self.q = Queue(Path(tempfile.mkdtemp()) / "queue.jsonl")

    def test_entry_uses_message_time(self):
        e = make_entry("bensin 50rb", TS, 1, self.cats)
        self.assertEqual((e["amount"], e["category"], e["type"]), (50_000, "BBM Motor", "pengeluaran"))
        self.assertTrue(e["ts"].endswith("+07:00"))

    def test_income_and_unknown_category(self):
        e = make_entry("+2,5jt bonus", TS, 1, self.cats)
        self.assertEqual((e["type"], e["amount"], e["category"]), ("pemasukan", 2_500_000, "Belum dikategorikan"))

    def test_unparseable_not_queued(self):
        reply = handle_message("beli galon", TS, 1, self.cats, self.q)
        self.assertIn("tidak terbaca", reply)
        self.assertEqual(self.q.all(), [])

    def test_last_n_survives_clear(self):
        for x in ("a 1rb", "b 2rb", "c 3rb", "d 4rb"):
            handle_message(x, TS, 1, self.cats, self.q)
        self.q.clear(4)
        out = handle_message("3 terakhir", TS, 1, self.cats, self.q)
        self.assertEqual(len(out.splitlines()), 3)
        self.assertNotIn(" a\n", out + "\n")
        self.assertIn(" d", handle_message("/terakhir", TS, 1, self.cats, self.q))
        self.assertEqual(len(self.q.last(10)), 4)

    def test_last_backfills_from_old_queue(self):
        self.q._write([make_entry("lama 5rb", TS, 1, self.cats)])  # antrean tanpa arsip
        self.assertIn("lama", handle_message("/terakhir", TS, 1, self.cats, self.q))

    def test_account_required_and_removed_from_note(self):
        acc = config.load()["accounts"]
        self.assertIn("Akun belum disebut", handle_message("bensin 50rb", TS, 1, self.cats, self.q, acc))
        self.assertEqual(self.q.all(), [])
        e = make_entry("jago ART gaji art 500rb", TS, 1, self.cats, acc)
        self.assertEqual((e["account"], e["note"]), ("Jago ART", "gaji art"))
        e = make_entry("JAGO sayur 20rb", TS, 1, self.cats, acc)
        self.assertEqual((e["account"], e["category"]), ("JAGO", "Belanja Dapur"))

    def test_transfer_makes_two_rows(self):
        acc = config.load()["accounts"]
        handle_message("pindah kas BSI ke cash 100rb", TS, 1, self.cats, self.q, acc)
        a, b = self.q.all()
        self.assertEqual((a["account"], a["type"], a["amount"], a["category"]), ("BSI", "pengeluaran", 100_000, "Pindah Kas"))
        self.assertEqual((b["account"], b["type"]), ("Cash", "pemasukan"))
        self.assertIn("Pindah kas tidak terbaca", handle_message("pindah kas BSI ke xyz 100rb", TS, 1, self.cats, self.q, acc))

    def test_clear_sent(self):
        for t in ("a 1rb", "b 2rb", "c 3rb"):
            handle_message(t, TS, 1, self.cats, self.q)
        self.q.clear(2)
        self.assertEqual([r["note"] for r in self.q.all()], ["c"])


if __name__ == "__main__":
    unittest.main()


class AccountPriorityTest(unittest.TestCase):
    ACC = ["Cash", "Mandiri", "JAGO", "Jago ART"]

    def test_leading_account_wins_over_account_word_in_description(self):
        e = make_entry("+cash Refund Saldo Mandiri 55rb", TS, 1, {}, self.ACC)
        self.assertEqual((e["account"], e["note"], e["type"]), ("Cash", "Refund Saldo Mandiri", "pemasukan"))

    def test_account_in_middle_still_found(self):
        e = make_entry("parkir cash 5rb", TS, 1, {}, self.ACC)
        self.assertEqual((e["account"], e["note"]), ("Cash", "parkir"))

    def test_sign_not_in_note(self):
        e = make_entry("-cash sabun 10rb", TS, 1, {}, self.ACC)
        self.assertEqual((e["note"], e["type"]), ("sabun", "pengeluaran"))


class SingleInstanceTest(unittest.TestCase):
    def test_second_instance_exits_with_code_3(self):
        from automation_hub.pribadi.bot import single_instance
        p = Path(tempfile.mkdtemp()) / "bot.lock"
        first = single_instance(p)
        try:
            import fcntl  # noqa: F401
        except ImportError:
            self.skipTest("tanpa fcntl")
        with self.assertRaises(SystemExit) as cm:
            single_instance(p)
        self.assertEqual(cm.exception.code, 3)
        first.close()
