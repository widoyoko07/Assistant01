"""Tes sheetdetail (sintetis). Jalankan: python3 -m unittest discover -s tests"""
import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import sheetdetail as S
import takeoff as T


class SheetDetail(unittest.TestCase):
    def test_grid_skala_dari_jarak_garis(self):
        g = 6000 / (150 * T.PT_MM)
        xs = [100 + i * g for i in range(5)] + [333.3]
        self.assertEqual(S.dim_scale(xs).most_common(1)[0][0], 150)
        g = 7500 / (100 * T.PT_MM)
        self.assertEqual(S.dim_scale([50, 50 + g, 50 + 2 * g]).most_common(1)[0][0], 100)

    def test_orientasi_miring_pakai_hipotenusa(self):
        self.assertEqual(
            (S.orient((0, 0, 10, 0)), S.orient((0, 0, 0, 5)), S.orient((0, 0, 3, 4))),
            ("h", "v", "d"),
        )

    def test_kode_support(self):
        match = S.SUP_RE.match("SUV-28EC")
        self.assertIsNotNone(match)
        self.assertEqual(
            (match.group(1), match.group(2), match.group(3), match.group(4)),
            ("V", "28", "E", "C"),
        )
        self.assertEqual(S.LETTER_W["D"], 400)

if __name__ == "__main__":
    unittest.main()
