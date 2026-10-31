import unittest

from automation_hub.proyek import photo_pairs as P


class PairTest(unittest.TestCase):
    def test_pair_by_order_and_gaps(self):
        items = [("2026-10-10", "TODJO", "a"), ("2026-10-10", "TODJO", "b"), ("2026-10-06", "DHJ", "c")]
        photos = {("2026-10-10", "TODJO"): ["p1", "p2", "p3"]}
        rows = P.pair(items, photos)
        self.assertEqual([r[4] for r in rows], ["", "p1", "p2", "p3"])
        self.assertEqual(rows[0][5], "tanpa foto")
        self.assertEqual(rows[3][5], "foto sisa (belum dipasangkan)")

    def test_more_items_than_photos(self):
        rows = P.pair([("d", "S", "a"), ("d", "S", "b")], {("d", "S"): ["p1"]})
        self.assertEqual(rows[1][5], "tanpa foto")


class GapTest(unittest.TestCase):
    def test_drive_counts_and_gaps(self):
        drive = P.drive_counts(["261001 a.jpg", "261001 b.jpg", "261002 c.png", "catatan.txt"])
        self.assertEqual(drive, {"2026-10-01": 2, "2026-10-02": 1})
        self.assertEqual(P.gaps(["2026-10-01", "2026-10-02"], {"2026-10-01": 6}, {"2026-10-02": 4}),
                         [])

    def test_gap_needs_both_low(self):
        self.assertEqual(P.gaps(["d1", "d2", "d3"], {"d1": 6, "d2": 3}, {"d1": 0, "d2": 4, "d3": 1}), [("d3", 0, 1)])


if __name__ == "__main__":
    unittest.main()
