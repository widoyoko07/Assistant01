import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from automation_hub.proyek import ingest_zip as iz

CFG = {"groups": {"SILOG TBM Pluit": "SILOG", "TPE Daily Report": "TPE"}}


def make_zip(path, files):
    with zipfile.ZipFile(path, "w") as z:
        for n, data in files.items():
            z.writestr(n, data)


class IngestTest(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.root = Path(self._t.name)
        self.addCleanup(self._t.cleanup)

    def test_group_names(self):
        for name in ["WhatsApp Chat - SILOG TBM Pluit.zip", "WhatsApp Chat with SILOG TBM Pluit.zip",
                     "WhatsApp Chat - SILOG TBM Pluit (1).zip"]:
            self.assertEqual(iz.group_from_filename(name), "SILOG TBM Pluit")

    def test_two_zips_extract_and_rerun_skipped(self):
        z1, z2 = self.root / "WhatsApp Chat - SILOG TBM Pluit.zip", self.root / "WhatsApp Chat - TPE Daily Report.zip"
        make_zip(z1, {"_chat.txt": "x", "IMG-1.jpg": "a", "att.pdf": "b"})
        make_zip(z2, {"_chat.txt": "y", "v.mp4": "c", "x.bin": "d"})
        processed = {}
        m1 = iz.ingest(z1, CFG, processed, "d1", root=self.root)
        m2 = iz.ingest(z2, CFG, processed, "d2", root=self.root)
        self.assertEqual(m1["sc"], "SILOG")
        self.assertEqual(m1["counts"], {"txt": 1, "jpg": 1, "pdf": 1, "video": 0, "lainnya": 0})
        self.assertEqual(m2["counts"]["video"], 1)
        self.assertEqual(m2["counts"]["lainnya"], 1)
        n_dirs = len(list((self.root / "01_extracted").iterdir()))
        self.assertIsNone(iz.ingest(z1, CFG, processed, "d1", root=self.root))
        self.assertIsNone(iz.ingest(z1, CFG, processed, "other-id", root=self.root))  # sha sama
        self.assertEqual(len(list((self.root / "01_extracted").iterdir())), n_dirs)

    def test_unknown_group_stops(self):
        z = self.root / "WhatsApp Chat - Grup Lain.zip"
        make_zip(z, {"_chat.txt": "x"})
        self.assertIsNone(iz.ingest(z, CFG, {}, root=self.root))
        self.assertFalse((self.root / "01_extracted").exists())

    def test_path_traversal_rejected(self):
        for bad in ["../evil.txt", "/abs.txt", "C:\\win.txt"]:
            z = self.root / "WhatsApp Chat - SILOG TBM Pluit.zip"
            make_zip(z, {bad: "x"})
            self.assertIsNone(iz.ingest(z, CFG, {}, root=self.root), bad)
        self.assertFalse((self.root.parent / "evil.txt").exists())

    def test_size_limit(self):
        z = self.root / "a.zip"
        make_zip(z, {"f": "x" * 100})
        with self.assertRaises(ValueError):
            iz.safe_extract(z, self.root / "out", max_bytes=10)


if __name__ == "__main__":
    unittest.main()
