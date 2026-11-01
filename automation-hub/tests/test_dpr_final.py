import unittest

from automation_hub.proyek import dpr_final as F


def blk(n):
    return {"items": ["- x"] * n}


class LayoutTest(unittest.TestCase):
    def test_blocks_stacked_with_blank_row_between(self):
        self.assertEqual(F.layout([blk(2), blk(0), blk(3)]), [(146, 2), (149, 1), (151, 3)])

    def test_overflow_is_an_error_not_silent_truncation(self):
        with self.assertRaises(ValueError):
            F.layout([blk(20), blk(20)])


class CivilMappingTest(unittest.TestCase):
    def test_columns_mapped_by_header_name_not_position(self):
        civil = {"AE": "commoun labor", "AF": "security", "AL": "excavator pc 400", "AI": "total station"}
        dpr = {"AE": "skilled workers", "AF": "commoun labor", "AG": "security", "AK": "total station"}
        self.assertEqual(F.column_map(civil, dpr), {"AE": "AF", "AF": "AG", "AI": "AK"})

    def test_row_kinds(self):
        self.assertEqual(F._row_kind({"B": "Sub", "D": "x"}), "a")
        self.assertEqual(F._row_kind({"D": "Area :", "G": "08.00", "Y": 1}), "b")
        self.assertEqual(F._row_kind({"D": "- item"}), "c")
        self.assertEqual(F._row_kind({"D": "- item", "E": 8, "F": "m3"}), "d")
        self.assertEqual(F._row_kind({}), "e")


if __name__ == "__main__":
    unittest.main()
