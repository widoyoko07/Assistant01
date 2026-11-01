import unittest

from automation_hub.common.money import UNCATEGORIZED
from automation_hub.pribadi.classify import build_lexicon, classify, normalize

CATS = {"Listrik": ["listrik", "token"], "BBM Motor": ["bensin"]}
REC = ([{"description": "Cemilan di kantor", "subcategory": "Jalan Makan"}] * 4
       + [{"description": "Makan batagor", "subcategory": "Jalan Makan"}] * 3
       + [{"description": "Isi ulang galon", "subcategory": "Air Minum"}] * 5
       + [{"description": "Belanja", "subcategory": "Belanja Dapur"}] * 3
       + [{"description": "Belanja", "subcategory": "Rumah Tangga"}] * 3)  # ambigu
LEX = build_lexicon(REC)


class ClassifyTest(unittest.TestCase):
    def test_normalize_drops_amount(self):
        self.assertEqual(normalize("Cemilan di kantor 15rb!"), "cemilan di kantor")

    def test_history_phrase_wins(self):
        self.assertEqual(classify("cemilan di kantor 15rb", CATS, LEX), "Jalan Makan")

    def test_config_keyword_still_works(self):
        self.assertEqual(classify("token listrik 100rb", CATS, LEX), "Listrik")

    def test_trusted_token_from_history(self):
        self.assertEqual(classify("makan batagor mang udin", CATS, LEX), "Jalan Makan")

    def test_typo_matches_history_and_keywords(self):
        self.assertEqual(classify("isi ulng galon 20rb", CATS, LEX), "Air Minum")
        self.assertEqual(classify("bensn 50rb", CATS, LEX), "BBM Motor")
        self.assertEqual(classify("lstrik 100rb", CATS, LEX), "Listrik")

    def test_ambiguous_history_is_not_guessed(self):
        self.assertEqual(classify("belanja 50rb", CATS, LEX), UNCATEGORIZED)

    def test_unknown_stays_unknown(self):
        self.assertEqual(classify("zzzxqw 10rb", CATS, LEX), UNCATEGORIZED)
        self.assertEqual(classify("zzzxqw 10rb", CATS, None), UNCATEGORIZED)

    def test_short_words_not_fuzzy_matched(self):
        self.assertEqual(classify("ban 10rb", CATS, LEX), UNCATEGORIZED)


if __name__ == "__main__":
    unittest.main()
