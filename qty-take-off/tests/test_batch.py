"""Tes mode batch (PDF sintetis). Jalankan: python3 -m unittest discover -s tests"""
import os, sys, tempfile, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
sys.path.insert(0, os.path.dirname(__file__))
import batch, takeoff as T
from test_takeoff import make_pdf

class Batch(unittest.TestCase):
    def test_label_area_dan_andal(self):
        self.assertEqual(batch.area_label("A2O BIOREACTOR TANKS (NORTH)"), "A2O North")
        self.assertEqual(batch.area_label("MBR TANKS (SOUTH)"), "MBR South")
        self.assertEqual(batch.area_label("WAS FLOWMETER CHAMBER"), "WAS Flowmeter Chamber")
        s = {"flags": [], "checks": ["tray 200W: 9 m / 1 support = 9.00 m per support  PERINGATAN: di luar 1.0-3.0 m"], "support_total": 1, "tray_m": {"200": 9}, "conduit_h_m": 1, "conduit_v_upper_m": 0}
        self.assertIn("TIDAK andal", batch.reliability(s))
    def test_run_resume_dan_excel(self):
        d = tempfile.mkdtemp(); f = os.path.join(d, "t.pdf"); make_pdf(f, title="PLAN AT EL+1000", scale=100, tray_mm=10000, tray_w=700, cond_h_mm=5000)
        cfg = T.load_config(); res = batch.run(f, cfg, os.path.join(d, "o"), budget=120, px=4)
        self.assertEqual(len(res["sets"]), 1); self.assertAlmostEqual(res["sets"][0]["tray_m"].get("700", 0), 10.0, delta=1.0)
        n1 = len(open(os.path.join(d, "o", "pages.jsonl")).readlines()); batch.run(f, cfg, os.path.join(d, "o"), budget=120, px=4)
        self.assertEqual(n1, len(open(os.path.join(d, "o", "pages.jsonl")).readlines()))     # resume: tidak mengulang halaman
        batch.write_excel(os.path.join(d, "o")); self.assertTrue(os.path.exists(os.path.join(d, "o", "Rekap_Tray_Conduit_per_Area.xlsx")))
    def test_role_section_berdiri_sendiri(self):
        self.assertEqual(T.guess_role("SECTION-A\nSCALE - 1:150"), "section"); self.assertEqual(T.guess_role("PLAN AT EL+5800\nSCALE - 1:150"), "plan")

if __name__ == "__main__": unittest.main()
