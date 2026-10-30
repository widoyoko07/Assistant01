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
