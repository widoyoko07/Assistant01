import tempfile
import unittest
from unittest import mock
from pathlib import Path

from automation_hub.pribadi.entries import Queue, make_entry
from automation_hub.pribadi.graph import Graph, GraphError, excel_serial, row_values
from automation_hub.pribadi.sync import sync_queue

CATS = {"Listrik": ["listrik"]}
ACC = ["Cash", "JAGO"]
TS = 1_790_000_000


class FakeGraph:
    def __init__(self, fail_first=False):
        self.calls, self.fail_first = [], fail_first

    def send(self, rows):
        if self.fail_first and not self.calls:
            self.calls.append("failed")
            raise GraphError("423 locked")
        self.calls.append(rows)


class RowTest(unittest.TestCase):
    def test_serial(self):
        self.assertEqual(excel_serial("1900-03-01"), 61)  # nilai acuan Excel

    def test_expense_and_income_rows(self):
        e = make_entry("cash listrik 350rb", TS, 1, CATS, ACC)
        r = row_values(e)
        self.assertEqual(r[1:5], ["Cash", "listrik", 350_000, 0])
        self.assertEqual((r[6], r[5], r[7:]), ("Listrik", None, [None] * 4))
        inc = row_values(make_entry("+jago gaji 5jt", TS, 1, {"Gaji": ["gaji"]}, ACC))
        self.assertEqual((inc[3], inc[4], inc[6]), (0, 5_000_000, "Gaji"))
        self.assertEqual(len(r), 11)


class SyncTest(unittest.TestCase):
    def setUp(self):
        d = Path(tempfile.mkdtemp())
        self.q, self.sent = Queue(d / "queue.jsonl"), d / "sent.json"
        for t in ("cash listrik 350rb", "jago listrik 100rb"):
            self.q.add(make_entry(t, TS, 1, CATS, ACC))

    def test_sync_sends_once_and_clears(self):
        g = FakeGraph()
        self.assertEqual(sync_queue(g.send, self.q, self.sent), 2)
        self.assertEqual(len(g.calls[0]), 2)
        self.assertEqual(self.q.all(), [])
        self.assertEqual(sync_queue(g.send, self.q, self.sent), 0)

    def test_failure_keeps_queue_and_retry_has_no_duplicate(self):
        g = FakeGraph(fail_first=True)
        with self.assertRaises(GraphError):
            sync_queue(g.send, self.q, self.sent)
        self.assertEqual(len(self.q.all()), 2)
        self.assertEqual(sync_queue(g.send, self.q, self.sent), 2)
        self.assertEqual(len(g.calls[-1]), 2)

    def test_crash_after_send_before_clear_does_not_duplicate(self):
        g = FakeGraph()
        sync_queue(g.send, self.q, self.sent)
        for t in ("cash listrik 350rb", "jago listrik 100rb"):  # antrean muncul lagi (clear gagal)
            self.q.add(make_entry(t, TS, 1, CATS, ACC))
        self.assertEqual(sync_queue(g.send, self.q, self.sent), 0)
        self.assertEqual(len(g.calls), 1)


class CallTest(unittest.TestCase):
    def test_retry_on_locked_then_ok(self):
        seq = iter([(423, {"error": {"message": "locked"}}), (200, {"index": 7})])
        g = Graph("cid", Path(tempfile.mkdtemp()) / "t.json", http=lambda *a: next(seq))
        g._access, g._exp = "tok", 1e12
        with mock.patch("automation_hub.pribadi.graph.time.sleep"):
            self.assertEqual(g.add_rows("a b.xlsx", "_transaction", [[1]]), 7)


if __name__ == "__main__":
    unittest.main()
