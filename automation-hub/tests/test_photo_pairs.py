import unittest

from automation_hub.proyek import photo_pairs as P


class PairTest(unittest.TestCase):
    def test_pair_by_order_and_gaps(self):
        items = [("2026-10-10", "TODJO", "a"), ("2026-10-10", "TODJO", "b"), ("2026-10-06", "DHJ", "c")]
        photos = {("2026-10-10", "TODJO"): ["p1", "p2", "p3"]}
        rows = P.pair(items, photos)
        self.assertEqual([r[4] for r in rows], ["", "p1", "p2", "p3"])
        self.assertEqual(rows[0][5], "tidak ada foto di ekspor")
        self.assertEqual(rows[3][5], "foto sisa (belum dipasangkan)")

    def test_more_items_than_photos(self):
        rows = P.pair([("d", "S", "a"), ("d", "S", "b")], {("d", "S"): ["p1"]})
        self.assertEqual(rows[1][5], "foto kurang dari butir")


if __name__ == "__main__":
    unittest.main()
