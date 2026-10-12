"""Tes mode batch (PDF sintetis). Jalankan: python3 -m unittest discover -s tests"""
import json, os, sys, tempfile, unittest
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
        batch.write_excel(os.path.join(d, "o"), res["manifest"]); self.assertTrue(os.path.exists(os.path.join(d, "o", "Rekap_Tray_Conduit_per_Area.xlsx")))
    def test_resume_menolak_file_atau_opsi_berbeda(self):
        d = tempfile.mkdtemp(); f = os.path.join(d, "t.pdf"); other = os.path.join(d, "other.pdf")
        make_pdf(f, title="PLAN AT EL+1000", scale=100, tray_mm=10000, tray_w=700)
        make_pdf(other, title="PLAN AT EL+1000", scale=100, tray_mm=12000, tray_w=700)
        out = os.path.join(d, "o"); cfg = T.load_config()
        batch.run(f, cfg, out, budget=120, px=4)
        with self.assertRaises(batch.BatchStateError):
            batch.run(other, cfg, out, budget=120, px=4)
        with self.assertRaises(batch.BatchStateError):
            batch.run(f, cfg, out, budget=120, px=5)
    def test_role_section_berdiri_sendiri(self):
        self.assertEqual(T.guess_role("SECTION-A\nSCALE - 1:150"), "section"); self.assertEqual(T.guess_role("PLAN AT EL+5800\nSCALE - 1:150"), "plan")
    def test_tray_vertikal_section_masuk_batas_atas(self):
        d = tempfile.mkdtemp(); f = os.path.join(d, "section.pdf")
        make_pdf(f, title="SECTION", scale=100, tray_v_mm=10000, tray_w_text="1000")
        res = batch.run(f, T.load_config(), os.path.join(d, "out"), budget=120, px=4)
        self.assertAlmostEqual(res["sets"][0]["tray_m"].get("1000", 0), 10.0, delta=0.7)
        self.assertAlmostEqual(res["sets"][0]["tray_vertical_upper_m"].get("1000", 0), 10.0, delta=0.7)
    def test_resume_menolak_checkpoint_model_pengukuran_lama(self):
        d = tempfile.mkdtemp(); f = os.path.join(d, "section.pdf"); out = os.path.join(d, "out")
        make_pdf(f, title="SECTION", scale=100, tray_v_mm=10000, tray_w_text="1000")
        batch.run(f, T.load_config(), out, budget=120, px=4)
        run_path = os.path.join(out, "run.json")
        with open(run_path, encoding="utf-8") as fh: manifest = json.load(fh)
        manifest["options"].pop("tray_width_model")
        with open(run_path, "w", encoding="utf-8") as fh: json.dump(manifest, fh)
        with self.assertRaises(batch.BatchStateError):
            batch.run(f, T.load_config(), out, budget=120, px=4)

if __name__ == "__main__": unittest.main()
