import unittest

from automation_hub.common import config
from automation_hub.common.money import UNCATEGORIZED, strip_amount, categorize, parse_amount, parse_entry, transaction_type

AMOUNTS = [
    ("50k", 50_000), ("50rb", 50_000), ("50 ribu", 50_000), ("1,5jt", 1_500_000),
    ("1.5 jt", 1_500_000), ("50.000", 50_000), ("Rp50.000", 50_000), ("50000", 50_000),
    ("Rp 1.500.000", 1_500_000), ("1.500", 1_500), ("1,500", 1_500), ("2 juta", 2_000_000),
    ("bensin 50rb", 50_000), ("beli galon 2 botol 40rb", 40_000), ("listrik Rp. 350.000", 350_000),
    ("gaji 5jt", 5_000_000), ("+2,5jt transfer", 2_500_000), ("parkir 5k", 5_000),
    ("tol 1.5k", 1_500), ("makan 25.500", 25_500), ("RP75000", 75_000), ("1.500 rb", 1_500_000),
    ("wifi 350RB", 350_000), ("10jt", 10_000_000),
    ("Rp 50.000,-", 50_000), ("bensin 50 rb", 50_000), ("1,2jt", 1_200_000), ("0,5jt", 500_000),
    ("+1jt bonus", 1_000_000), ("transfer masuk 750.000", 750_000), ("beli 3 galon 60rb", 60_000),
    ("2.5jt", 2_500_000), ("pulsa 100.000 rupiah", 100_000), ("tgl 15 listrik 350rb", 350_000),
]
NONE = ["beli galon", "2 botol", "1,5", "50kg beras", "abc", "makan siang 35k kopi 15k"]


class AmountTest(unittest.TestCase):
    def test_amounts(self):
        for text, want in AMOUNTS:
            with self.subTest(text=text):
                self.assertEqual(parse_amount(text), want)

    def test_sample_count(self):
        self.assertGreaterEqual(len(AMOUNTS) + len(NONE), 30)

    def test_same_amount_twice_is_not_ambiguous(self):
        self.assertEqual(parse_amount("kopi 15k teh 15k"), 15_000)

    def test_unparseable_is_none_not_guess(self):
        for text in NONE:
            with self.subTest(text=text):
                self.assertIsNone(parse_amount(text))


class StripAmountTest(unittest.TestCase):
    def test_amount_removed_other_numbers_kept(self):
        for text, want in [
            ("Jajan Indomaret 4002", "Jajan Indomaret"), ("cemilan kantor 15rb", "cemilan kantor"),
            ("pulsa 0851 7993 1140 50rb", "pulsa 0851 7993 1140"), ("kopi 15k teh 15k", "kopi teh"),
            ("galon 2 botol 40rb", "galon 2 botol"), ("Rp 50.000 parkir", "parkir"),
            ("bensin bp 92 supra 50rb", "bensin bp 92 supra"), ("makan - 25.500", "makan"),
            ("beli galon", "beli galon"), ("50rb", "50rb"),
        ]:
            with self.subTest(text=text):
                self.assertEqual(strip_amount(text), want)


class TypeCategoryTest(unittest.TestCase):
    cats = config.load()["categories"]

    def test_type(self):
        self.assertEqual(transaction_type("+500rb"), "pemasukan")
        self.assertEqual(transaction_type("gaji oktober 5jt"), "pemasukan")
        self.assertEqual(transaction_type("terima 200rb"), "pemasukan")
        self.assertEqual(transaction_type("bensin 50rb"), "pengeluaran")
        self.assertEqual(transaction_type("-gaji art 500rb"), "pengeluaran")

    def test_category(self):
        self.assertEqual(categorize("bayar listrik 350rb", self.cats), "Listrik")
        self.assertEqual(categorize("tol 20rb", self.cats), "Transportasi")
        self.assertEqual(categorize("beli sesuatu 20rb", self.cats), UNCATEGORIZED)

    def test_entry(self):
        e = parse_entry("galon 20rb", self.cats)
        self.assertEqual((e["amount"], e["category"], e["ok"]), (20_000, "Air Minum", True))
        self.assertFalse(parse_entry("galon", self.cats)["ok"])


if __name__ == "__main__":
    unittest.main()
