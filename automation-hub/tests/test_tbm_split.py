import tempfile
import unittest
from pathlib import Path

from automation_hub.common.runlog import RunLog
from automation_hub.proyek import tbm_split as T

RULE = {"header": "PT. ACME", "skip": "OVERTIME", "end": "^SITE CONDITION"}
CFG = {"tbm": {"ACME": RULE}}


def m(ts, text, i=1):
    return {"id": f"m{i}", "ts": f"{ts}+07:00", "text": text, "system": False}


BODY = "Rabu 28 Oktober 2026\nPT. ACME\nStart : 07.30\n\n1. Admin : Budi  \n2. Helper : Sari\nTotal manpower : 2 persons\n"


class PostingTest(unittest.TestCase):
    def test_cut_at_trailer_keeps_line_content(self):
        txt = T.posting_text(m("2026-10-28T10:06:57", BODY + "\nSITE CONDITION\nWeather : Cloudy\nThank you"), RULE)
        self.assertEqual(txt, BODY.rstrip() + "\n")  # spasi di tengah baris dibiarkan seperti aslinya
        self.assertNotIn("Weather", txt)

    def test_leading_media_marker_removed(self):
        txt = T.posting_text(m("2026-10-28T09:11:03", "<image omitted> DAILY REPORT\nPT. ACME"), RULE)
        self.assertTrue(txt.startswith("DAILY REPORT"))

    def test_overtime_and_other_companies_skipped(self):
        self.assertFalse(T.is_posting(m("2026-10-28T19:18:50", "TBM Overtime\nPT. ACME"), RULE))
        self.assertFalse(T.is_posting(m("2026-10-28T10:00:00", "PT. OTHER\n1. x"), RULE))
        self.assertTrue(T.is_posting(m("2026-10-28T10:00:00", BODY), RULE))

    def test_revision_uses_last_with_warning(self):
        with tempfile.TemporaryDirectory() as t:
            log = RunLog("t", root=Path(t))
            got = T.pick_postings([m("2026-10-28T10:00:00", BODY, 1), m("2026-10-28T11:00:00", BODY + "rev", 2)], RULE, log)
            self.assertEqual(got["2026-10-28"]["id"], "m2")
            self.assertEqual(len(log.warnings), 1)
            log.summary()


class WriteTest(unittest.TestCase):
    def test_write_names_idempotent_and_unknown_sc(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            msgs = [m("2026-10-28T10:00:00", BODY), m("2026-10-29T10:00:00", BODY)]
            log = RunLog("t", root=root)
            files = T.split_all(msgs, "ACME", CFG, root=root, log=log)
            self.assertEqual([f.name for f in files], ["ACME TBM 20261028 Posting.txt", "ACME TBM 20261029 Posting.txt"])
            first = files[0].read_text(encoding="utf-8")
            T.split_all(msgs, "ACME", CFG, root=root, log=log)
            self.assertEqual(files[0].read_text(encoding="utf-8"), first)
            self.assertEqual(T.split_all(msgs, "ZZZ", CFG, root=root, log=log), [])
            self.assertTrue(any("ZZZ" in w for w in log.warnings))
            log.summary()


if __name__ == "__main__":
    unittest.main()


class RealConfigRulesTest(unittest.TestCase):
    """Aturan di config.yaml untuk SC yang sudah diverifikasi terhadap Posting.txt asli (data sintetis di sini)."""

    @classmethod
    def setUpClass(cls):
        from automation_hub.common import config as cfgmod
        cls.rules = cfgmod.load()["tbm"]

    def test_all_verified_sc_have_rules(self):
        self.assertEqual(set(self.rules), {"SILOG", "WME", "TPE", "DHJ", "WKP", "TODJO", "BCP"})

    def test_tpe_today_kept_tomorrow_skipped_weather_cut(self):
        r = self.rules["TPE"]
        today = "Work Planning Today\n26 October 2026 PT. TIGA PILAR ENERGI\n1. A\nTotal All: 1 Person\n\nWeather Condition: sunny\nThankyou."
        self.assertTrue(T.is_posting(m("2026-10-26T09:00:00", today), r))
        self.assertFalse(T.is_posting(m("2026-10-26T13:00:00", "<document omitted> Work Planning tomorrow \n27 October 2026 PT. TIGA PILAR ENERGI\n1. A"), r))
        self.assertTrue(T.posting_text(m("2026-10-26T09:00:00", today), r).endswith("Total All: 1 Person\n"))

    def test_bcp_safety_toolbox_post_cut_before_thanks(self):
        txt = "Daily report Safety Toolbox Meeting\nInternal team BCP\nJumat,30-10-2026\n\nAktifitas kerja :\n- Pemasangan X\n\nUpdate pekerja :\n13 orang\n\nTerima kasih\nSalam K3"
        r = self.rules["BCP"]
        self.assertTrue(T.is_posting(m("2026-10-30T08:57:00", txt), r))
        self.assertFalse(T.is_posting(m("2026-10-30T09:00:00", "Koordinasi meeting HSE"), r))
        self.assertTrue(T.posting_text(m("2026-10-30T08:57:00", txt), r).endswith("13 orang\n"))

    def test_dhj_cut_before_kondisi(self):
        txt = "<image omitted> DAILY REPORT\nPT. DUTA HITA JAYA\nTotal manpower = 1 orang\n\nKondisi lokasi : Baik\nCuaca : Cerah"
        self.assertEqual(T.posting_text(m("2026-10-26T10:00:00", txt), self.rules["DHJ"]),
                         "DAILY REPORT\nPT. DUTA HITA JAYA\nTotal manpower = 1 orang\n")

    def test_wkp_cut_before_activity_hse(self):
        txt = "HSE DAILY REPORT PT. WKP \nTotal mp: 37 persons \n\nActivity HSE\nHSE Concern :"
        self.assertEqual(T.posting_text(m("2026-10-27T09:00:00", txt), self.rules["WKP"]), "HSE DAILY REPORT PT. WKP \nTotal mp: 37 persons\n")

    def test_todjo_workplan_spellings_and_text_date(self):
        r = self.rules["TODJO"]
        for spell in ("workplant", "workpalne", "workpalnt", "Workplann", "workplan"):
            self.assertTrue(T.is_posting(m("2026-10-28T15:27:51", f"<image omitted> Thursday 27-10-2026 {spell}\nWASEFLOW"), r), spell)
        self.assertFalse(T.is_posting(m("2026-10-09T14:53:22", "ROAD CLOSURE NOTIFICATION\nDear all"), r))
        late = m("2026-10-28T15:27:51", "Thursday 27-10-2026 workpalnt\nWASEFLOW")
        self.assertIn("2026-10-27", T.pick_postings([late], r))

    def test_text_date_formats(self):
        self.assertEqual(T.text_date("Selasa, 27 Okt 2026"), "2026-10-27")
        self.assertEqual(T.text_date("Rabu 28Oktober 2026"), "2026-10-28")
        self.assertEqual(T.text_date("Workplann : 14-October-2026"), "2026-10-14")
        self.assertEqual(T.text_date("Monday 12 -10-2026 workpalne"), "2026-10-12")
        self.assertIsNone(T.text_date("ZONE 1 PLUIT JAKARTA"))

    def test_typo_date_warns_and_uses_sent_date(self):
        with tempfile.TemporaryDirectory() as t:
            log = RunLog("t", root=Path(t))
            got = T.pick_postings([m("2026-10-28T10:38:22", "DAILY REPORT\nRABU, 26 OKTOBER 2026\nPT. DUTA HITA JAYA")], self.rules["DHJ"], log)
            self.assertEqual(list(got), ["2026-10-28"])
            self.assertEqual(len(log.warnings), 1)
            log.summary()
