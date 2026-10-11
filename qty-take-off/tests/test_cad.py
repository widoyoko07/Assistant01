"""Tes jalur CAD (DXF sintetis berpanjang diketahui). Jalankan: python3 -m unittest discover -s tests"""
import os, subprocess, sys, tempfile, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import ezdxf, cad, takeoff as T

def dxf(path, units=4, ladder=False, dup=True, z=True):
    d = ezdxf.new("R2018", setup=True); d.units = units
    for n in ("E-TRAY-700", "E-TRAY-200", "E-CONDUIT"): d.layers.add(n)
    m = d.modelspace()
    if ladder:
        m.add_lwpolyline([(0, 0), (10000, 0)], dxfattribs={"layer": "E-TRAY-700"}); m.add_lwpolyline([(0, 700), (10000, 700)], dxfattribs={"layer": "E-TRAY-700"})
        for x in range(0, 10001, 300): m.add_line((x, 0), (x, 700), dxfattribs={"layer": "E-TRAY-700"})
    else:
        m.add_lwpolyline([(0, 0), (6000, 0), (6000, 4000)], dxfattribs={"layer": "E-TRAY-700"})            # 10 m
        if dup: m.add_lwpolyline([(0, 0), (6000, 0), (6000, 4000)], dxfattribs={"layer": "E-TRAY-700"})   # ganda
    m.add_line((0, 100), (5000, 100), dxfattribs={"layer": "E-TRAY-200"})
    b = d.blocks.new("TRAYBLK"); b.add_line((0, 0), (1000, 0), dxfattribs={"layer": "0"})
    m.add_blockref("TRAYBLK", (0, 500), dxfattribs={"layer": "E-TRAY-200"})                                 # +1 m lewat blok
    m.add_line((0, 0, 0), (3000, 4000, 0), dxfattribs={"layer": "E-CONDUIT"})                               # 5 m horizontal
    if z: m.add_line((0, 0, 0), (0, 0, 2500), dxfattribs={"layer": "E-CONDUIT"})                            # 2.5 m vertikal
    for n, q in (("SUH-42GC", 3), ("SUH-46BC", 2)):
        d.blocks.new(n)
        for i in range(q): m.add_blockref(n, (i * 100, 900))
    d.saveas(path); return path

def cfg(): return T.load_config()

class CAD(unittest.TestCase):
    def setUp(self): self.d = tempfile.mkdtemp()
    def test_ukur_dedup_blok_3d_support(self):
        rec, sup, leg = cad.measure(dxf(os.path.join(self.d, "a.dxf")), cfg())
        self.assertEqual(rec["tray_m"], {"700": 10.0, "200": 6.0})            # garis ganda dibuang, blok ikut
        self.assertEqual((rec["conduit_h_m"], rec["conduit_v_m"]), (5.0, 2.5))
        self.assertEqual({k: v["qty"] for k, v in sup.items()}, {"SUH-42GC": 3, "SUH-46BC": 2})
        self.assertTrue(any("garis ganda" in f for f in rec["flags"]))
    def test_ladder_rel_dibagi_dua(self):
        rec, _, _ = cad.measure(dxf(os.path.join(self.d, "b.dxf"), ladder=True), cfg())
        self.assertAlmostEqual(rec["tray_m"]["700"], 10.0, delta=0.2); self.assertTrue(any("ladder" in f for f in rec["flags"]))
    def test_satuan_kosong_dan_2d(self):
        rec, _, _ = cad.measure(dxf(os.path.join(self.d, "c.dxf"), units=0, z=False), cfg())
        self.assertTrue(any("INSUNITS" in f for f in rec["flags"])); self.assertTrue(any("2D" in f for f in rec["flags"])); self.assertEqual(rec["conduit_v_m"], 0)
    def test_satuan_meter(self):
        rec, _, _ = cad.measure(dxf(os.path.join(self.d, "e.dxf"), units=6), cfg())      # 6 = meter: nilai gambar dianggap meter
        self.assertGreater(rec["tray_m"]["700"], 1000)
    def test_scan_menemukan_layer_dan_support(self):
        s = cad.scan(dxf(os.path.join(self.d, "f.dxf")), cfg()); roles = {l["layer"]: l["role_guess"] for l in s["layers"]}
        self.assertEqual((roles["E-TRAY-700"], roles["E-CONDUIT"]), ("tray", "conduit")); self.assertEqual(s["support_blocks"]["SUH-42GC"], 3); self.assertTrue(s["has_3d"])
    def test_crosscheck_spacing(self):
        d = dxf(os.path.join(self.d, "g.dxf")); out = os.path.join(self.d, "o"); os.makedirs(out)
        r = T.plan_cad(d, cfg(), out); self.assertTrue(any("700W" in c and "PERINGATAN" in c for c in r["checks"]))   # 10 m / 3 = 3.33 m
    def test_dwg_gagal_memberi_instruksi(self):
        bad = os.path.join(self.d, "x.dwg"); open(bad, "wb").write(b"AC1032" + os.urandom(5000))
        with self.assertRaises(cad.ConvertError) as cm: cad.convert_dwg(bad, os.path.join(self.d, "o"))
        self.assertIn("DXF", str(cm.exception))
    def test_cli_plan_execute_dxf(self):
        f = dxf(os.path.join(self.d, "h.dxf")); s = os.path.join(os.path.dirname(__file__), "..", "scripts", "takeoff.py")
        subprocess.run([sys.executable, s, "plan", f, "--out", self.d], check=True, capture_output=True)
        self.assertNotEqual(subprocess.run([sys.executable, s, "execute", f, "--out", self.d], capture_output=True).returncode, 0)
        subprocess.run([sys.executable, s, "execute", f, "--out", self.d, "--confirm"], check=True, capture_output=True)
        self.assertTrue(os.path.exists(os.path.join(self.d, "Takeoff_Tray_Conduit.xlsx")))

if __name__ == "__main__": unittest.main()
