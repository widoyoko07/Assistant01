import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path

from automation_hub.common import config
from automation_hub.pribadi.dates import FutureDate, extract_date
from automation_hub.pribadi.entries import TZ, Queue, handle_message

BASE = date(2026, 11, 1)  # Minggu
CASES = [
    ("kemarin cash parkir 5rb", date(2026, 10, 31), "cash parkir 5rb"),
    ("-kamis, cemilan kantor 15rb", date(2026, 10, 29), "-cemilan kantor 15rb"),
    ("+jumat, Refund 55rb", date(2026, 10, 30), "+Refund 55rb"),
    ("cash parkir 5rb 29/10", date(2026, 10, 29), "cash parkir 5rb"),
    ("tgl 29 cash parkir 5rb", date(2026, 10, 29), "cash parkir 5rb"),
    ("tgl 5 parkir 5rb", date(2026, 10, 5), "parkir 5rb"),
    ("29 okt cash tol 20rb", date(2026, 10, 29), "cash tol 20rb"),
    ("2 hari lalu cash tol 20rb", date(2026, 10, 30), "cash tol 20rb"),
    ("kemarin lusa cash tol 5rb", date(2026, 10, 30), "cash tol 5rb"),
    ("minggu cash tol 5rb", BASE, "cash tol 5rb"),
    ("hari jumat cash bensin 50rb", date(2026, 10, 30), "cash bensin 50rb"),
    ("29/10/26 cash x 5rb", date(2026, 10, 29), "cash x 5rb"),
    ("cash parkir 5rb", None, "cash parkir 5rb"),
    ("cash pasar kamis 20rb", None, "cash pasar kamis 20rb"),  # di tengah kalimat bukan tanggal
]


class DatesTest(unittest.TestCase):
    def test_cases(self):
        for text, d, rest in CASES:
            with self.subTest(text=text):
                self.assertEqual(extract_date(text, BASE), (d, rest))

    def test_future_rejected(self):
        with self.assertRaises(FutureDate):
            extract_date("29/12 parkir 5rb", BASE)


class HandleTest(unittest.TestCase):
    def setUp(self):
        self.cats = config.load()["categories"]
        self.acc = config.load()["accounts"]
        self.q = Queue(Path(tempfile.mkdtemp()) / "q.jsonl")
        self.ts = int(datetime(2026, 11, 1, 9, 0, tzinfo=TZ).timestamp())

    def test_entry_gets_backdated(self):
        handle_message("kemarin cash parkir 5rb", self.ts, 1, self.cats, self.q, self.acc)
        e = self.q.all()[0]
        self.assertEqual((e["date"], e["note"]), ("2026-10-31", "parkir"))

    def test_transfer_backdated(self):
        handle_message("pindah kas BSI ke cash 100rb kamis", self.ts, 1, self.cats, self.q, self.acc)
        self.assertEqual({e["date"] for e in self.q.all()}, {"2026-10-29"})

    def test_future_not_recorded(self):
        self.assertIn("belum terjadi", handle_message("29/12 cash parkir 5rb", self.ts, 1, self.cats, self.q, self.acc))
        self.assertEqual(self.q.all(), [])


if __name__ == "__main__":
    unittest.main()
