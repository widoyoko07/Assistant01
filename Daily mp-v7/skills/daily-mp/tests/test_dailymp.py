"""Jalankan: python3 -m unittest discover -s tests   (dari folder skill)"""
import os, sys, unittest, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import dailymp as M, crosscheck_pdf as X

M.load_scmap()
def cls(sc, role, section=""):
    M.CUR[0] = sc; return M.classify(role, section)
def P(name, role, sec="A", cat="Skilled Workers"): return {"name": name, "role": role, "section": sec, "category": cat}

class Klasifikasi(unittest.TestCase):
    def test_silog(self):
        self.assertEqual(cls("SILOG", "SM"), "Site Engineer")
        for r in ("Admin", "DOCON", "Matecon", "Driver"): self.assertEqual(cls("SILOG", r), "Staff")
        self.assertEqual(cls("SILOG", "SI"), "Foreman")
        self.assertEqual(cls("SILOG", "Helper", "WAREHOUSE"), "Common Labor")
        self.assertEqual(cls("SILOG", "Helper", "LPS"), "Skilled Workers")
        self.assertEqual(cls("SILOG", "Helper", "Team QC"), "QA/QC Department")     # seksi Team QC memaksa QA/QC
        self.assertEqual(cls("SILOG", None, "Team Scaffolder"), "Scaffolder")
    def test_sc_lain(self):
        self.assertEqual(cls("DHJ", "PM"), "Construction Manager"); self.assertEqual(cls("DHJ", "Helper"), "Common Labor")
        self.assertEqual(cls("TPE", "HLP MECH"), "Common Labor"); self.assertEqual(cls("TPE", "FM MW"), "Foreman")
        self.assertEqual(cls("WME", "Forman"), "Foreman"); self.assertEqual(cls("WME", "SPV HR/GA"), "Staff")
        self.assertEqual(cls("WME", "SPV Piping"), "Supervisor")
    def test_team_qc_hanya_silog(self):
        self.assertNotEqual(cls("TPE", "Helper", "Team QC"), "QA/QC Department")
    def test_djk(self):
        self.assertEqual(cls("DJK", "SPV"), "Supervisor"); self.assertEqual(cls("DJK", "MEP", "Night Shift"), "Land 1")
        self.assertEqual(cls("DJK", None, "Day Shift Land ( WAREHOUSE )"), "Land 2")
    def test_role_baru(self):
        self.assertIn(M.NEW, cls("SILOG", "Koki"))

class Dedup(unittest.TestCase):
    def setUp(self): M.DEDUP_THR[0] = 0.85; M.DEDUP_SCOPE[0] = "section"
    def test_persis(self):
        f, r, _ = M.dedupe([P("Ibnu", "Teknisi"), P("Ibnu", "Teknisi")]); self.assertEqual((len(f), len(r)), (1, 1))
    def test_ejaan_seksi_sama_dihapus(self):
        f, r, _ = M.dedupe([P("Ahmd Sukoco", "Teknisi", "LPS"), P("Achmad Sukoco", "Teknisi", "LPS")]); self.assertEqual(len(f), 1)
    def test_lintas_lokasi_dipertahankan(self):
        f, r, w = M.dedupe([P("M. Rizal", "Teknisi", "ADMIN"), P("Rizal", "Skill", "PULLING")])
        self.assertEqual(len(f), 2); self.assertTrue(any("lintas lokasi" in x for x in w))
        M.DEDUP_SCOPE[0] = "category"; self.assertEqual(len(M.dedupe([P("M. Rizal", "Teknisi", "ADMIN"), P("Rizal", "Skill", "PULLING")])[0]), 1)
    def test_ambang(self):
        M.DEDUP_THR[0] = 0.99; self.assertEqual(len(M.dedupe([P("Ahmd Sukoco", "T", "LPS"), P("Achmad Sukoco", "T", "LPS")])[0]), 2)

class Validasi(unittest.TestCase):
    def test_hari_salah(self):
        w = M.check_header("DAILY REPORT\nFRIDAY, 26 SEPTEMBER 2026\nPT X", "2026-09-26"); self.assertTrue(any("Sabtu" in x for x in w))
    def test_ok(self): self.assertEqual(M.check_header("Sabtu, 26 September 2026", "2026-09-26"), [])
    def test_beda_file(self): self.assertTrue(M.check_header("Sabtu, 26 September 2026", "2026-09-27"))

class Crosscheck(unittest.TestCase):
    def test_parse(self):
        p, st = X.parse_att("ERN\nMukdi Foreman SILOG\n1 Andre FE OWJJ\nSlamet Dwi Insp Scaffolder SILOG\nTOTAL MANPOWER: 5", "SILOG")
        self.assertEqual([(x["name"], x["role"]) for x in p], [("Mukdi", "Foreman"), ("Slamet Dwi", "Insp Scaffolder")]); self.assertEqual(st, 5)
    def test_match(self):
        r = X.crosscheck([{"name": "M. Thariq Alfian", "role": None, "section": "-"}, {"name": "Abdur Rahman", "role": None, "section": "-"}, {"name": "Zzz", "role": None, "section": "-"}],
                         [{"name": "Thariq", "role": None, "section": "-"}, {"name": "Abdurahman", "role": None, "section": "-"}])
        self.assertEqual((len(r["subset"]), len(r["fuzzy"]), len(r["only_att"])), (1, 1, 1))

if __name__ == "__main__": unittest.main()
