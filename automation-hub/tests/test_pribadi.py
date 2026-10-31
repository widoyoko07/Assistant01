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
        self.assertEqual((e["amount"], e["category"], e["type"]), (50_000, "Transportasi", "pengeluaran"))
        self.assertTrue(e["ts"].endswith("+07:00"))

    def test_income_and_unknown_category(self):
        e = make_entry("+2,5jt bonus", TS, 1, self.cats)
        self.assertEqual((e["type"], e["amount"], e["category"]), ("pemasukan", 2_500_000, "Belum dikategorikan"))

    def test_unparseable_not_queued(self):
        reply = handle_message("beli galon", TS, 1, self.cats, self.q)
        self.assertIn("tidak terbaca", reply)
        self.assertEqual(self.q.all(), [])

    def test_queue_and_undo_per_sender(self):
        handle_message("bensin 50rb", TS, 1, self.cats, self.q)
        handle_message("wifi 350rb", TS, 2, self.cats, self.q)
        self.assertIn("Dibatalkan: bensin", handle_message("/undo", TS, 1, self.cats, self.q))
        self.assertEqual([r["note"] for r in self.q.all()], ["wifi 350rb"])
        self.assertIn("Tidak ada", handle_message("/undo", TS, 1, self.cats, self.q))

    def test_clear_sent(self):
        for t in ("a 1rb", "b 2rb", "c 3rb"):
            handle_message(t, TS, 1, self.cats, self.q)
        self.q.clear(2)
        self.assertEqual([r["note"] for r in self.q.all()], ["c 3rb"])


if __name__ == "__main__":
    unittest.main()
