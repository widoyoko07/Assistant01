import tempfile
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path

import openpyxl

from automation_hub.common import config
from automation_hub.proyek import dpr_me_block as B

CFG = config.load()
BASE = date.fromisoformat(CFG["me_sheet"]["base_date"])
COL = CFG["me_sheet"]["base_col"]
ROLES = ["Site Engineer", "Administration Department", "Skilled Workers", "Staff"]


def sheet():
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "ME"
    ws.cell(4, COL + 1).value = datetime.combine(BASE, datetime.min.time()) + timedelta(days=1)
    ws.cell(341, 2).value = "DJK DCIP"
    for k, (role, v) in enumerate([("Site Engineer", 1), ("Admin", 1), ("Rigger", 1), ("Fitter", 7), ("Material Control", 2), ("Total Manpower", 12)]):
        ws.cell(342 + k, 4).value = role
        ws.cell(342 + k, COL + 1).value = v
    return ws


class ManpowerTest(unittest.TestCase):
    def test_labels_are_mapped_and_summed_and_total_row_skipped(self):
        got = B.manpower(sheet(), CFG, BASE + timedelta(days=1), "DJK DCIP", ROLES, CFG["dpr_role_map"])
        self.assertEqual(got, {"Site Engineer": 1, "Administration Department": 1, "Skilled Workers": 8, "Staff": 2})

    def test_unknown_label_is_an_error_not_a_guess(self):
        with self.assertRaises(ValueError):
            B.manpower(sheet(), CFG, BASE + timedelta(days=1), "DJK DCIP", ["Site Engineer"], {})


if __name__ == "__main__":
    unittest.main()
