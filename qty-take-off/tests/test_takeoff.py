"""Jalankan: python3 -m unittest discover -s tests   (dari folder skill)
Tes memakai PDF sintetis buatan sendiri (panjang diketahui), jadi tidak butuh PDF proyek.
Regresi PDF asli: set env SD_TAKEOFF_PDF=/path/file.pdf (dilewati bila tidak ada)."""
import json, os, subprocess, sys, tempfile, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import takeoff as T
import pymupdf as fitz

MM = T.PT_MM
def pt(mm, N): return mm / (N * MM)                      # mm nyata -> pt PDF pada skala 1:N

def line(p, a, b, color):
    sh = p.new_shape(); sh.draw_line(a, b); sh.finish(color=color, width=0.3); sh.commit()


def make_pdf(path, title, scale, tray_mm=0, tray_w=700, tray_v_mm=0, tray_w_text=None, cond_h_mm=0, cond_v_mm=0):
    doc = fitz.open(); p = doc.new_page(width=1191, height=842)
    p.insert_text((100, 800), f"{title}\nSCALE - 1:{scale}", fontsize=8)
    if tray_w_text: p.insert_text((100, 780), f"CABLE TRAY {tray_w_text}(W) x 100(H)mm EL+1000", fontsize=8)
    x0, y0 = 100, 300
    if tray_mm:
        L, w = pt(tray_mm, scale), pt(tray_w, scale)
        for dy in (0, w): line(p, (x0, y0 + dy), (x0 + L, y0 + dy), (1, 0, 1))
        step = pt(300, scale); x = x0
        while x <= x0 + L: line(p, (x, y0), (x, y0 + w), (1, 0, 1)); x += step
    if tray_v_mm: line(p, (700, 200), (700, 200 + pt(tray_v_mm, scale)), (1, 0, 1))
    if cond_h_mm: line(p, (100, 500), (100 + pt(cond_h_mm, scale), 500), (0, 1, 0))
    if cond_v_mm: line(p, (600, 100), (600, 100 + pt(cond_v_mm, scale)), (0, 1, 0))
    doc.save(path)


class Teks(unittest.TestCase):
    def test_role(self):
        self.assertEqual(T.guess_role("... PLAN AT EL+7800"), "plan")
        self.assertEqual(T.guess_role("SECTION\nSCALE - 1:100 ... SECTION E"), "section")
        self.assertEqual(T.guess_role("DETAIL N1"), "detail")
        self.assertEqual(T.guess_role("CABLE LIST P1"), "list")
        self.assertEqual(T.guess_role("DRAWING INDEX\n3 OF 33 LAYOUT ... NORTH 1 SECTION A , B"), "other")
    def test_label_dan_legend_dan_support(self):
        self.assertEqual(T.label_scales("SCALE - 1:120 ... 1: 200 ... 1:1").most_common(1)[0][0] in (120, 200), True)
        self.assertEqual(T.legend_widths("A =100Wx100H\nG =700Wx100H")["G"], (700, 100))
        self.assertEqual(T.tray_callout_widths("CABLE TRAY 1000(W) x 100(H)mm EL+7800\nCABLE TRAY 200(W) x 100(H)mm"), [200, 1000])
        s = T.parse_supports("SUPPORT NO.\nSUH-42GC\nQTY\n6 EA\nSUPPORT NO.\nSUH-108BC\nQTY\n44 EA")
        self.assertEqual((s["SUH-42GC"]["qty"], s["SUH-42GC"]["letter"], s["SUH-108BC"]["qty"]), (6, "G", 44))

class Skala(unittest.TestCase):
    seq = [[6500, 6400, 6400, 6400, 6400, 6400, 6400, 6500]]
    def xs(self, N, noise=()):
        r = N * MM; x, out = 170.0, []
        out.append(x)
        for g in self.seq[0]: x += g / r; out.append(x)
        return sorted(out + list(noise))
    def test_grid_200_dengan_noise(self):
        g = T.grid_scale(self.xs(200, noise=(300.0, 512.3, 777.7)), self.seq)
        self.assertEqual(T.snap_scale(g[0]), 200)
    def test_tolak_skala_kebetulan(self):
        self.assertIsNone(T.snap_scale(88 * MM))            # 1:88 bukan skala standar
    def test_label_beda_dengan_geometri(self):
        row = {"sheet": 3, "label_scales": {120: 1}, "geometry_scale": 200, "geometry_lines": 9}
        N, st, fl = T.resolve_scale(row, T.load_config()); self.assertEqual((N, st), (200, "geometri")); self.assertIn("TIDAK cocok", fl)
        row["geometry_lines"] = 4
        N, st, fl = T.resolve_scale(row, T.load_config()); self.assertEqual((N, st), (120, "label-saja")); self.assertIn("WAJIB dicek", fl)
    def test_override_menang(self):
        cfg = T.load_config(); cfg["scales"]["3"] = 150
        self.assertEqual(T.resolve_scale({"sheet": 3, "label_scales": {120: 1}, "geometry_scale": 200, "geometry_lines": 9}, cfg)[:2], (150, "override"))

class Ukur(unittest.TestCase):
    def run_plan(self, **kw):
        d = tempfile.mkdtemp(); f = os.path.join(d, "t.pdf"); make_pdf(f, **kw)
        return T.plan(f, T.load_config(), os.path.join(d, "out"))
    def test_tray_700_panjang_10m(self):
        r = self.run_plan(title="PLAN AT EL+1000", scale=100, tray_mm=10000, tray_w=700)
        self.assertAlmostEqual(r["tray_total_m"].get("700", 0), 10.0, delta=0.6); self.assertLess(r["tray_total_m"].get("200", 0), 1.5)
    def test_tray_200_dan_skala_200(self):
        r = self.run_plan(title="PLAN AT EL+1000", scale=200, tray_mm=20000, tray_w=200)
        self.assertAlmostEqual(r["tray_total_m"].get("200", 0), 20.0, delta=1.2)
    def test_conduit_horizontal_plan_dan_vertikal_section(self):
        r = self.run_plan(title="PLAN AT EL+1000", scale=100, cond_h_mm=5000, cond_v_mm=3000)
        self.assertAlmostEqual(r["conduit_h_total_m"], 8.0, delta=0.4)        # plan: semua garis hijau dihitung
        self.assertEqual(r["conduit_v_upper_m"], 0)                            # plan tidak menyumbang vertikal
        r = self.run_plan(title="SECTION", scale=100, cond_h_mm=5000, cond_v_mm=3000)
        self.assertAlmostEqual(r["conduit_v_upper_m"], 3.0, delta=0.3); self.assertEqual(r["conduit_h_total_m"], 0)
    def test_tray_vertikal_section_dihitung_sebagai_batas_atas(self):
        r = self.run_plan(title="SECTION", scale=100, tray_v_mm=10000, tray_w_text="1000")
        self.assertAlmostEqual(r["tray_total_m"].get("1000", 0), 10.0, delta=0.6)
        self.assertAlmostEqual(r["tray_length_total_m"], 10.0, delta=0.6)
        self.assertAlmostEqual(r["tray_vertical_upper_m"].get("1000", 0), 10.0, delta=0.6)
        self.assertTrue(any("batas atas" in f for s in r["sheets"] for f in s["flags"]))
    def test_callout_width_menggantikan_kandidat_default(self):
        r = self.run_plan(title="PLAN AT EL+1000", scale=100, tray_mm=10000, tray_w=700, tray_w_text="1000")
        self.assertGreater(r["tray_total_m"].get("1000", 0), 9.0)
        self.assertNotIn("700", r["tray_total_m"])
    def test_pdf_tanpa_vektor_berwarna_ditolak(self):
        d = tempfile.mkdtemp(); f = os.path.join(d, "t.pdf"); make_pdf(f, title="PLAN AT EL+1000", scale=100)
        with self.assertRaises(SystemExit): T.plan(f, T.load_config(), os.path.join(d, "o"))
    def test_overlay_dibuat(self):
        d = tempfile.mkdtemp(); f = os.path.join(d, "t.pdf"); make_pdf(f, title="PLAN AT EL+1000", scale=100, tray_mm=5000)
        T.plan(f, T.load_config(), os.path.join(d, "o")); self.assertTrue(any(n.endswith("_tray.png") for n in os.listdir(os.path.join(d, "o", "overlay"))))

class Gerbang(unittest.TestCase):
    def test_execute_tanpa_confirm_ditolak(self):
        d = tempfile.mkdtemp(); f = os.path.join(d, "t.pdf"); make_pdf(f, title="PLAN AT EL+1000", scale=100, tray_mm=5000)
        s = os.path.join(os.path.dirname(__file__), "..", "scripts", "takeoff.py")
        subprocess.run([sys.executable, s, "plan", f, "--out", d], check=True, capture_output=True)
        r = subprocess.run([sys.executable, s, "execute", f, "--out", d], capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0); self.assertFalse(os.path.exists(os.path.join(d, "Takeoff_Tray_Conduit.xlsx")))
        r = subprocess.run([sys.executable, s, "execute", f, "--out", d, "--confirm"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0); self.assertTrue(os.path.exists(os.path.join(d, "Takeoff_Tray_Conduit.xlsx")))

    def test_execute_menolak_dry_run_dari_file_berbeda(self):
        d = tempfile.mkdtemp(); f1 = os.path.join(d, "a.pdf"); f2 = os.path.join(d, "b.pdf")
        make_pdf(f1, title="PLAN AT EL+1000", scale=100, tray_mm=5000)
        make_pdf(f2, title="PLAN AT EL+1000", scale=100, tray_mm=9000)
        s = os.path.join(os.path.dirname(__file__), "..", "scripts", "takeoff.py")
        subprocess.run([sys.executable, s, "plan", f1, "--out", d], check=True, capture_output=True)
        r = subprocess.run([sys.executable, s, "execute", f2, "--out", d, "--confirm"], capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0); self.assertIn("tidak cocok", r.stderr)
        self.assertFalse(os.path.exists(os.path.join(d, "Takeoff_Tray_Conduit.xlsx")))

@unittest.skipUnless(os.environ.get("SD_TAKEOFF_PDF"), "set SD_TAKEOFF_PDF untuk regresi PDF asli")
class PDFAsli(unittest.TestCase):
    def test_baseline_rfs020026_06(self):
        d = tempfile.mkdtemp(); r = T.plan(os.environ["SD_TAKEOFF_PDF"], T.load_config(), d)
        self.assertAlmostEqual(r["conduit_h_total_m"], 163.7, delta=2); self.assertAlmostEqual(r["conduit_v_upper_m"], 211.8, delta=3)
        self.assertAlmostEqual(r["tray_total_m"]["700"], 82.9, delta=4); self.assertAlmostEqual(r["tray_total_m"]["200"], 194.9, delta=8)
        self.assertEqual(sum(v["qty"] for v in r["supports"].values()), 139)

if __name__ == "__main__": unittest.main()
