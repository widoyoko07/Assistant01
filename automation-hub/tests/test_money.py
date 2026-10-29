import unittest

from automation_hub.common import config
from automation_hub.common.money import UNCATEGORIZED, categorize, parse_amount, parse_entry, transaction_type

AMOUNTS = [
    ("50k", 50_000), ("50rb", 50_000), ("50 ribu", 50_000), ("1,5jt", 1_500_000),
    ("1.5 jt", 1_500_000), ("50.000", 50_000), ("Rp50.000", 50_000), ("50000", 50_000),
    ("Rp 1.500.000", 1_500_000), ("1.500", 1_500), ("1,500", 1_500), ("2 juta", 2_000_000),
    ("bensin 50rb", 50_000), ("beli galon 2 botol 40rb", 40_000), ("listrik Rp. 350.000", 350_000),
    ("gaji 5jt", 5_000_000), ("+2,5jt transfer", 2_500_000), ("parkir 5k", 5_000),
    ("tol 1.5k", 1_500), ("makan 25.500", 25_500), ("RP75000", 75_000), ("1.500 rb", 1_500_000),
    ("wifi 350RB", 350_000), ("10jt", 10_000_000),
]
NONE = ["beli galon", "2 botol", "1,5", "50kg beras", "abc"]


class AmountTest(unittest.TestCase):
    def test_amounts(self):
        for text, want in AMOUNTS:
            with self.subTest(text=text):
                self.assertEqual(parse_amount(text), want)

    def test_unparseable_is_none_not_guess(self):
        for text in NONE:
            with self.subTest(text=text):
                self.assertIsNone(parse_amount(text))


class TypeCategoryTest(unittest.TestCase):
    cats = config.load()["categories"]

    def test_type(self):
        self.assertEqual(transaction_type("+500rb"), "pemasukan")
        self.assertEqual(transaction_type("gaji oktober 5jt"), "pemasukan")
        self.assertEqual(transaction_type("terima 200rb"), "pemasukan")
        self.assertEqual(transaction_type("bensin 50rb"), "pengeluaran")

    def test_category(self):
        self.assertEqual(categorize("bayar listrik 350rb", self.cats), "Rumah Tangga")
        self.assertEqual(categorize("tol 20rb", self.cats), "Transportasi")
        self.assertEqual(categorize("jajan 20rb", self.cats), UNCATEGORIZED)

    def test_entry(self):
        e = parse_entry("galon 20rb", self.cats)
        self.assertEqual((e["amount"], e["category"], e["ok"]), (20_000, "Rumah Tangga", True))
        self.assertFalse(parse_entry("galon", self.cats)["ok"])


if __name__ == "__main__":
    unittest.main()
