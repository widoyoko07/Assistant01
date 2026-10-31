import unittest

from automation_hub.proyek import translate as T

TABLE = {T._norm("Pemasangan rubber seal MCC SN-1"): "Install rubber seal, MCC SN-1"}


class TranslateTest(unittest.TestCase):
    def test_known_line_keeps_prefix(self):
        self.assertEqual(T.to_english("- Pemasangan  rubber seal MCC SN-1", TABLE), ("- Install rubber seal, MCC SN-1", "ok"))
        self.assertEqual(T.to_english("3. ‎Pemasangan rubber seal MCC SN-1", TABLE)[0], "3. Install rubber seal, MCC SN-1")

    def test_english_passes_and_unknown_indonesian_is_flagged_not_guessed(self):
        self.assertEqual(T.to_english("- Install cable tray at STB", TABLE), ("- Install cable tray at STB", "ok"))
        self.assertEqual(T.to_english("- Pemasangan kabel baru", TABLE), ("- Pemasangan kabel baru", "perlu"))


if __name__ == "__main__":
    unittest.main()
