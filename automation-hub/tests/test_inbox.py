import tempfile
import unittest
from pathlib import Path

from automation_hub.pribadi.entries import Queue, make_entry
from automation_hub.pribadi.inbox import HEADER, append_entries
from automation_hub.pribadi.sync import sync_queue

CATS = {"Listrik": ["listrik"]}
TS = 1_790_000_000


class InboxTest(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())
        self.path = self.d / "Inbox.tsv"
        self.q = Queue(self.d / "queue.jsonl")

    def rows(self):
        return [l.split("\t") for l in self.path.read_text(encoding="utf-8").splitlines()]

    def test_header_once_and_columns(self):
        self.q.add(make_entry("cash listrik 350rb", TS, 7, CATS, ["Cash"]))
        send = lambda es: append_entries(self.path, es)
        sync_queue(send, self.q, self.d / "sent.json")
        self.q.add(make_entry("+cash gaji 1jt", TS, 7, {"Gaji": ["gaji"]}, ["Cash"]))
        sync_queue(send, self.q, self.d / "sent.json")
        r = self.rows()
        self.assertEqual(r[0], HEADER)
        self.assertEqual(len(r), 3)
        self.assertEqual(r[1][2:8], ["Cash", "listrik", "350000", "0", "Listrik", "7"])
        self.assertEqual(r[2][4:6], ["0", "1000000"])

    def test_tabs_and_newlines_in_text_do_not_break_rows(self):
        e = make_entry("cash listrik\t350rb\nbulan ini", TS, 1, CATS, ["Cash"])
        append_entries(self.path, [e])
        self.assertTrue(all(len(x) == 8 for x in self.rows()))

    def test_no_duplicate_after_requeue(self):
        e = make_entry("cash listrik 350rb", TS, 1, CATS, ["Cash"])
        send = lambda es: append_entries(self.path, es)
        self.q.add(e)
        sync_queue(send, self.q, self.d / "sent.json")
        self.q.add(e)  # antrean muncul lagi karena clear gagal
        sync_queue(send, self.q, self.d / "sent.json")
        self.assertEqual(len(self.rows()), 2)


if __name__ == "__main__":
    unittest.main()


class LegacyEntryTest(unittest.TestCase):
    def test_entry_without_account_does_not_block_sync(self):
        d = Path(tempfile.mkdtemp())
        q = Queue(d / "queue.jsonl")
        q.add({"ts": "2026-10-31T10:00:00+07:00", "date": "2026-10-31", "type": "pengeluaran", "category": "Listrik",
               "amount": 5000, "note": "lama", "sender": 1})  # entri sebelum fitur akun
        sync_queue(lambda es: append_entries(d / "i.tsv", es), q, d / "sent.json")
        self.assertEqual(q.all(), [])
        self.assertEqual((d / "i.tsv").read_text(encoding="utf-8").splitlines()[1].split("\t")[2], "")
