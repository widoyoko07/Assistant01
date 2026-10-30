import unittest

from automation_hub.common import config
from automation_hub.proyek import me_report as R

CFG = config.load()
AL = CFG["sc_aliases"]


def msg(ts, caption, i=1):
    return {"id": f"m{i}", "ts": f"{ts}+07:00", "caption": caption, "system": False}


class HeaderTest(unittest.TestCase):
    def test_header_variants(self):
        for line, want in [("24/10/26 TPE", ["TPE"]), ("Silog - 24 Oct 2026", ["SILOG"]),
                           ("TOHOMA Activity 24 Oktober 2026", ["TODJO"]), ("Dwijo - ATRN and MTLN", ["TODJO"]),
                           ("Dwidjo - X", ["TODJO"]), ("DJK Service - X", ["DJK"]), ("WME - LPS", ["WME"]),
                           ("Thm-Dwj OT Activity 28/10/2026", ["TODJO"])]:
            with self.subTest(line=line):
                self.assertEqual(R.header_scs(line, AL), want)

    def test_bullets_and_long_lines_are_not_headers(self):
        self.assertEqual(R.header_scs("- Fab. Conduit tpe", AL), [])
        self.assertEqual(R.header_scs("1. wme pipe spool", AL), [])


class SplitTest(unittest.TestCase):
    def test_multi_sc_message_with_overtime_title(self):
        m = msg("2026-10-26T21:56:17", "Overtime Oct, 26 2026\nTOHOMA\nMTRS\n- Filling water\nSILOG\nPGLN\n- Install Conduit")
        s = R.split_message(m, AL)
        self.assertEqual([(x["sc"], x["ot"]) for x in s], [("TODJO", True), ("SILOG", True)])
        self.assertEqual(s[0]["lines"], ["MTRS", "- Filling water"])

    def test_normal_report_is_not_overtime(self):
        s = R.split_message(msg("2026-10-24T17:33:16", "24/10/26 TPE\n- LPS\n1. Cutting rail gantry"), AL)
        self.assertEqual([(x["sc"], x["ot"], x["date"]) for x in s], [("TPE", False, "2026-10-24")])

    def test_overtime_title_between_sections_applies_to_following(self):
        m = msg("2026-10-29T20:52:36", "Dwijo - ATRN\nMP: 10 person\n\nOvertime 29/10/2026\nWME - LPS\nMP: 17 person")
        self.assertEqual([(x["sc"], x["ot"]) for x in R.split_message(m, AL)], [("TODJO", False), ("WME", True)])

    def test_thm_dwj_header_is_todjo(self):
        m = msg("2026-10-28T22:34:13", "Thm-Dwj OT Activity 28/10/2026\nATRN :\n- Connect")
        s = R.split_message(m, AL)
        self.assertEqual((s[0]["sc"], s[0]["ot"]), ("TODJO", True))

    def test_unregistered_combination_not_guessed(self):
        s = R.split_message(msg("2026-10-28T22:34:13", "Silog - Tpe\n- x"), AL)
        self.assertEqual((s[0]["sc"], s[0]["candidates"]), (None, ["SILOG", "TPE"]))


class HoursTest(unittest.TestCase):
    def test_hours(self):
        self.assertEqual(R.dpr_hours(False, CFG), ("08.00", "17.00", 8))
        self.assertEqual(R.dpr_hours(True, CFG), ("08.00", "21.00", 12))

    def test_collect_merges_overtime_per_day_and_sc(self):
        msgs = [msg("2026-10-27T09:00:00", "Silog - 27 Oct\n- a", 1),
                msg("2026-10-27T21:43:00", "OT Silog 27 Oct 2026\n- b", 2),
                msg("2026-10-27T10:00:00", "TPE\n- c", 3)]
        _, daily = R.collect(msgs, CFG)
        self.assertEqual([(r["sc"], r["finish"], r["total"]) for r in daily],
                         [("SILOG", "21.00", 12), ("TPE", "17.00", 8)])

    def test_overtime_items_join_work_description(self):
        msgs = [msg("2026-10-27T09:00:00", "Silog - 27 Oct\n- Install conduit\nMP: 8", 1),
                msg("2026-10-27T21:43:00", "OT Silog 27 Oct 2026\n- Install conduit\n- Termination cable", 2)]
        parts, _ = R.collect(msgs, CFG)
        self.assertEqual(R.work_description(parts, "SILOG", "2026-10-27"),
                         ["- Install conduit", "- Termination cable"])
        self.assertEqual(R.work_description(parts, "TPE", "2026-10-27"), [])

    def test_repeated_overtime_title_not_appended_to_previous_section(self):
        m = msg("2026-10-29T20:52:36", "Overtime 29/10/2026\nDwijo - ATRN\nMP: 10 person\n- Boring\n\nOvertime 29/10/2026\nWME - LPS\n- Filling")
        s = R.split_message(m, AL)
        self.assertEqual(s[0]["lines"], ["MP: 10 person", "- Boring"])
        self.assertEqual([x["sc"] for x in s], ["TODJO", "WME"])

    def test_label_only_lines_dropped_and_csv_written(self):
        import csv, tempfile
        from pathlib import Path
        cfg = {"sc_aliases": AL, "dpr": {"hours": {"normal": {"start": "08.00", "finish": "17.00", "total": 8},
                                                  "overtime": {"start": "08.00", "finish": "21.00", "total": 12}}}}
        ms = [msg("2026-10-26T10:00:00", "TOHOMA\n- Install pipe", 1),
              msg("2026-10-26T21:56:17", "Overtime 26 Oct\nTOHOMA\nActivity:\n- Filling water", 2)]
        with tempfile.TemporaryDirectory() as t:
            p = R.write_csv(ms, cfg, root=Path(t))
            with open(p, encoding="utf-8-sig") as f:
                rows = list(csv.DictReader(f))
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]["overtime"], rows[0]["finish"], rows[0]["total_hours"]), ("Y", "21.00", "12"))
        self.assertEqual(rows[0]["work_description"], "- Install pipe\n- Filling water")


if __name__ == "__main__":
    unittest.main()
