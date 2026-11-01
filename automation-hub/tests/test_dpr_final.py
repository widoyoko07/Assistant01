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


if __name__ == "__main__":
    unittest.main()
