"""Jalankan: python3 -m unittest discover -s tests   (dari folder skill)"""
import os, sys, unittest, tempfile, subprocess
from unittest import mock
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import dailymp as M, crosscheck_pdf as X, pdf_to_att as PDF

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
    def test_role_membantu_ambigu_dan_token(self):
        A = lambda n, r: {"name": n, "role": r, "section": "-"}
        r = X.crosscheck([A("Yanuar Muchlis", "PPC"), A("Jais", "SPV Rigg"), A("Paisal Sihalobo", "Driver")],
                         [A("Yanuar", "SDCC"), A("Yanuar", "PPC"), A("Jaiz", "SPV Rigg"), A("FAISAL", "Driver")])
        self.assertEqual(len(r["only_att"]), 0); self.assertEqual(r["subset"][0][1]["role"], "PPC")
    def test_absen_dikenali(self):
        rep = X.report("TPE", "2026-09-30", [{"name": "Junaidi", "role": "Scaffolder", "section": "-"}], None, [], None, ["JUNAIDI ABSEN"])
        self.assertIn("tercatat ABSEN", rep)
    def test_folder_attendance_belum_ada(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(X.find_attendance(os.path.join(d, "missing"), "WME", "2026-09-28"))

class SumberPDF(unittest.TestCase):
    def test_format_pipa_dan_klasifikasi_wme(self):
        p, _ = X.parse_att("Muhtarom | Site Manager | PT. WME\nAndre | FE | OWJJ\nMartin | Survey | \nBudi | Skill Matecon | PT. WME", "WME")
        self.assertEqual([x["name"] for x in p], ["Muhtarom", "Martin", "Budi"])
        self.assertEqual([cls("WME", x["role"]) for x in p], ["Construction Manager", "Surveyor", "Skilled Workers"])
    def test_pdf_source_dan_cek_posting(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "WME_20260928_Attendance.txt"), "w", encoding="utf-8") as source:
                source.write("A | Fitter | PT. WME\nB | Helper | PT. WME\nC | Docon | PT. WME\n")
            M.ATT_DIR[0] = d
            counts, notes, _ = M.pdf_source("WME", "2026-09-28", {"status": "summary", "summary": {"indirect": 1, "direct": 1, "total": 2}})
            self.assertEqual((counts["Skilled Workers"], counts["Common Labor"], counts["Staff"]), (1, 1, 1))
            self.assertIn("selisih total +1", notes[0]); M.ATT_DIR[0] = None
    def test_pdf_tanpa_baris_tidak_dihitung_nol(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "WME_20260928_Attendance.txt"), "w", encoding="utf-8"):
                pass
            M.ATT_DIR[0] = d
            try:
                res = {s: {} for s in M.SUBS}
                res["WME"]["2026-09-28"] = {"status": "summary", "summary": {"indirect": 1, "direct": 1, "total": 2}}
                table, notes, _ = M.build(res, "2026-09-28", False)
                self.assertEqual(table[0][2][M.SUBS.index("WME")], "n/a")
                self.assertTrue(any("hasil bukan 0 orang" in note for note in notes))
            finally:
                M.ATT_DIR[0] = None

class PDFExtraction(unittest.TestCase):
    def test_no_data_report_does_not_show_zero_total(self):
        date = "2026-09-29"
        res = {s: {} for s in M.SUBS}
        table, _, _ = M.build(res, date, False)
        compact = M.md_compact(table, date, res)
        self.assertIn("Belum ada data untuk seluruh subcon", compact)
        self.assertNotIn("Total Manpower", compact)
        self.assertNotIn("| 0 |", compact)
        self.assertIn("Belum ada data untuk seluruh subcon", M.md(table, date))
        self.assertIn("Belum ada data untuk seluruh subcon", M.tsv(table))

    def test_empty_range_reports_missing_dates(self):
        with tempfile.TemporaryDirectory() as d:
            result = subprocess.run(
                [sys.executable, M.__file__, "--dir", d, "--range", "2026-09-26", "2026-09-29"],
                capture_output=True, text=True, check=True,
            )
        self.assertIn("Tidak ada data tanggal dalam rentang", result.stdout)
        self.assertNotIn("| Tanggal |", result.stdout)

    def test_ocr_fallback_when_text_layer_has_no_parseable_table(self):
        text_words = [dict(t=f"word{i}", x=i, y=10, w=5, h=8, c=100) for i in range(45)]
        ocr_words = [
            dict(t="No", x=5, y=10, w=10, h=10, c=95),
            dict(t="Name", x=20, y=10, w=30, h=10, c=95),
            dict(t="Position", x=100, y=10, w=45, h=10, c=95),
            dict(t="PT/CV", x=200, y=10, w=35, h=10, c=95),
            dict(t="Signature", x=300, y=10, w=45, h=10, c=95),
            dict(t="1", x=5, y=30, w=5, h=10, c=95),
            dict(t="Alice", x=20, y=30, w=30, h=10, c=95),
            dict(t="Fitter", x=100, y=30, w=30, h=10, c=95),
            dict(t="WME", x=200, y=30, w=25, h=10, c=95),
        ]
        with mock.patch.object(PDF, "words_from_text_layer", return_value=(text_words, 400)), \
             mock.patch.object(PDF, "render_page", return_value="page.png") as render, \
             mock.patch.object(PDF, "words_from_ocr", return_value=(ocr_words, 400)):
            records, source, _ = PDF.extract_page(None, "input.pdf", 1, 300, tempfile.gettempdir())
        self.assertEqual([(row["name"], row["role"], row["pt"]) for row in records], [("Alice", "Fitter", "WME")])
        self.assertEqual(source, "ocr")
        render.assert_called_once()
    def test_valid_text_table_does_not_render_page(self):
        text_words = [
            dict(t="No", x=5, y=10, w=10, h=10, c=100),
            dict(t="Name", x=20, y=10, w=30, h=10, c=100),
            dict(t="Position", x=100, y=10, w=45, h=10, c=100),
            dict(t="PT/CV", x=200, y=10, w=35, h=10, c=100),
            dict(t="Signature", x=300, y=10, w=45, h=10, c=100),
            dict(t="1", x=5, y=30, w=5, h=10, c=100),
            dict(t="Alice", x=20, y=30, w=30, h=10, c=100),
            dict(t="Fitter", x=100, y=30, w=30, h=10, c=100),
            dict(t="WME", x=200, y=30, w=25, h=10, c=100),
        ]
        with mock.patch.object(PDF, "words_from_text_layer", return_value=(text_words, 400)), \
             mock.patch.object(PDF, "render_page") as render:
            records, source, image = PDF.extract_page(None, "input.pdf", 1, 300, tempfile.gettempdir())
        self.assertEqual(len(records), 1)
        self.assertEqual(source, "text")
        self.assertIsNone(image)
        render.assert_not_called()

if __name__ == "__main__": unittest.main()
