import tempfile
import unittest
from pathlib import Path

from PIL import Image

from automation_hub.common import config
from automation_hub.proyek import media as M

CFG = config.load()


def msg(ts, sender, text="", att=(), omitted=False, i=[0]):
    i[0] += 1
    return {"id": f"m{i[0]}", "ts": f"{ts}+07:00", "sender": sender, "text": text, "caption": text, "attachments": list(att),
            "media_omitted": omitted, "system": False}


def jpg(d, name):
    Image.new("RGB", (20, 20), "white").save(Path(d) / name)


class AttendanceTest(unittest.TestCase):
    def test_pdf_from_photo_next_to_posting(self):
        with tempfile.TemporaryDirectory() as t:
            jpg(t, "a.jpg")
            ms = [msg("2026-10-30T08:57:00", "Pak A", att=["a.jpg"]),
                  msg("2026-10-30T08:57:01", "Pak A", "Daily report Safety Toolbox Meeting\nAktifitas kerja :\n- X\n\nTerima kasih")]
            out = M.write_attendance(ms, "BCP", CFG, t, root=Path(t) / "r")
            self.assertEqual([p.name for p in out], ["BCP TBM 20261030 Attendance.pdf"])
            self.assertTrue(out[0].read_bytes().startswith(b"%PDF"))

    def test_no_pdf_when_photo_missing(self):
        with tempfile.TemporaryDirectory() as t:
            ms = [msg("2026-10-30T08:57:01", "Pak A", "Daily report Safety Toolbox Meeting\n- X\n\nTerima kasih", omitted=True)]
            self.assertEqual(M.write_attendance(ms, "BCP", CFG, t, root=Path(t) / "r"), [])


class ReportPhotosTest(unittest.TestCase):
    def test_burst_after_header_goes_to_sc_and_omitted_counted(self):
        with tempfile.TemporaryDirectory() as t:
            for n in ("1.jpg", "2.jpg", "3.jpg"):
                jpg(t, n)
            ms = [msg("2026-10-24T17:33:16", "F", "24/10/26 TPE\n- LPS", att=["1.jpg"]),
                  msg("2026-10-24T17:33:19", "F", att=["2.jpg"]),
                  msg("2026-10-24T17:33:21", "F", omitted=True),
                  msg("2026-10-24T17:40:00", "F", att=["3.jpg"]),   # selang terlalu jauh: bukan milik TPE
                  ]
            rows = M.report_photos(ms, CFG, t)
            self.assertEqual([(r["sc"], r["file"] is not None) for r in rows], [("TPE", True), ("TPE", True), ("TPE", False)])
            out = M.write_photos(ms, CFG, t, root=Path(t) / "r")
            self.assertEqual(len(out), 2)
            self.assertTrue((Path(t) / "r" / "04_photos" / "20261024" / "TPE" / "01_1.jpg").exists())

    def test_other_sender_breaks_burst(self):
        with tempfile.TemporaryDirectory() as t:
            jpg(t, "1.jpg")
            ms = [msg("2026-10-24T17:33:16", "F", "24/10/26 TPE\n- LPS"), msg("2026-10-24T17:33:17", "G", att=["1.jpg"])]
            self.assertEqual(M.report_photos(ms, CFG, t), [])



class ScPhotosTest(unittest.TestCase):
    def test_progress_photos_exclude_attendance_form(self):
        with tempfile.TemporaryDirectory() as t:
            for n in ("form.jpg", "work.jpg"):
                jpg(t, n)
            cfg = {"tbm": {"WME": {"header": "WASA MITRA ENGINEERING"}}}
            msgs = [msg("2026-10-10T07:00:00", "A", "WASA MITRA ENGINEERING\nPLAN", att=["form.jpg"]),
                    msg("2026-10-10T15:00:00", "B", "", att=["work.jpg"])]
            got = M.sc_photos(msgs, "WME", cfg, t)
            self.assertEqual([(r["date"], r["file"].name) for r in got], [("2026-10-10", "work.jpg")])


if __name__ == "__main__":
    unittest.main()
