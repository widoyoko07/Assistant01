import tempfile
import unittest
import zipfile
from pathlib import Path

from automation_hub.proyek import cek_data as C

CFG = {"groups": {"OWJJ - BCP(Engineering)": "BCP", "OWJJ-TPE Mechanical Work": "TPE"}, "tbm": {"BCP": {}, "TPE": {}, "BME": {}},
       "skip_sc": ["BME"], "me_group": "OWJJ Construction M&E"}


def make_zip(path, last_day, images=0):
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("_chat.txt", f"[{last_day} 8.00.00 AM] A: halo\n")
        for i in range(images):
            z.writestr(f"00{i}-PHOTO.jpg", b"x")


class CekDataTest(unittest.TestCase):
    def test_report_flags_missing_stale_and_no_photos(self):
        with tempfile.TemporaryDirectory() as t:
            t = Path(t)
            (t / "inbox").mkdir()
            (t / "02_mp").mkdir()
            make_zip(t / "inbox" / "WhatsApp Chat - OWJJ - BCP(Engineering).zip", "30/10/26", images=2)
            make_zip(t / "inbox" / "WhatsApp Chat - OWJJ-TPE Mechanical Work.zip", "30/10/26")
            (t / "02_mp" / "BCP TBM 20261030 Posting.txt").write_text("x")
            rows = dict(C.check(CFG, "2026-10-30", root=t))
            self.assertNotIn("BME", rows)
            self.assertEqual((rows["BCP"]["posting"], rows["BCP"]["images"], rows["BCP"]["last"]), (True, 2, "2026-10-30"))
            self.assertEqual(rows["TPE"]["last"], "2026-10-30")
            text = C.report(list(rows.items()), "2026-10-30")
            self.assertIn("ZIP tanpa foto: TPE", text)
            self.assertIn("Posting belum ada: TPE", text)

            late = C.report(C.check(CFG, "2026-10-31", root=t), "2026-10-31")
            self.assertIn("chat belum mencakup tanggal ini (ekspor ulang): BCP, TPE", late)


if __name__ == "__main__":
    unittest.main()
