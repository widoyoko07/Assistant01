import unittest

from automation_hub.common import config
from automation_hub.proyek import todjo_attendance as T


def row(nama, pos, pt, ttd):
    return {"Nama": nama, "Posisi": pos, "PT/CV": pt, "Tanda tangan": ttd}


class CountTest(unittest.TestCase):
    def test_only_signed_counted_and_split_by_company(self):
        rows = [row("a", "SM", "Dwidjo", "ya"), row("b", "Helper", "Dwidjo", "tidak"), row("c", "Helper", "Dwidjo", "ya"),
                row("d", "SPV", "TOHOMA", "ya"), row("e", "Fitter", "Dwidjo", "ragu"), row("f", "Insp Scaff", "Dwidjo", "ya"),
                row("g", "Pilot", "Dwidjo", "ya")]
        counts, doubt, unknown = T.count(rows, config.load())
        self.assertEqual(counts, {("DJK DCIP", "Foreman"): 1, ("DJK DCIP", "Commoun Labor"): 1,
                                  ("Tohoma", "Construction Manager"): 1, ("DJK DCIP", "Scaffolder"): 1})
        self.assertEqual([r["Nama"] for r in doubt], ["e"])
        self.assertEqual([r["Nama"] for r in unknown], ["g"])


if __name__ == "__main__":
    unittest.main()
